"""Instantané de travail : ce que le Parquet « site » ne porte pas et qu'une reconstruction depuis une release perdait.

Une base reconstruite depuis une release n'avait NI le détail des mouvements (`squad_movement` : date, fenêtre, club d'origine des transferts
et prêts), NI les joueurs prêtés ailleurs (`loan_out`), NI les libellés de villes, stades et championnats (`entity_label`, `club.*_qid`), NI
l'historique des corrections ni les alias. Le script hebdomadaire repart d'une reconstruction à chaque passage : ces données disparaissaient des
releases suivantes (les colonnes `stint_*` du fichier d'effectif restaient vides, les clubs perdaient leur ville et leur stade).

L'export écrit donc ces tables à part (clé `work` du manifeste, fichiers `work_*/…`, jamais lus par le site) avec des CLÉS NATURELLES : titre du club,
libellé de saison, QID du joueur ou à défaut son nom. Jamais un numéro interne : ils sont régénérés à chaque reconstruction.
`apply_work` les relit dans une base reconstruite ; la même fonction sert à récupérer ces données depuis une ancienne base de travail
(`openfootball recover-work`). Idempotent : relancer n'ajoute rien de plus.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

import duckdb

WORK_SQL: dict[str, str] = {
    "squad_movement": """
        SELECT s.label AS season, cl.wikipedia_title AS club, p.name AS player, w.qid AS player_qid, p.link_lang, p.link_title,
               m.direction, m.kind, strftime(m.moved_on, '%Y-%m-%d') AS moved_on, m.transfer_window, m.other_club, m.other_club_link,
               m.mid_season, m.source_title
        FROM squad_movement m JOIN club_season cs ON cs.id = m.club_season_id JOIN season s ON s.id = cs.season_id
        JOIN club cl ON cl.id = cs.club_id JOIN player p ON p.id = m.player_id LEFT JOIN player_wikidata w ON w.player_id = p.id
        ORDER BY s.start_year, cl.wikipedia_title, p.name, m.direction""",
    "loan_out": """
        SELECT s.label AS season, cl.wikipedia_title AS club, p.name AS player, w.qid AS player_qid, p.link_lang, p.link_title,
               pcs.shirt_number, pcs.position_code, pcs.position_raw, pcs.nationality_raw, pcs.confidence, pcs.source, pcs.source_section,
               (SELECT string_agg(r.source_lang, ',' ORDER BY r.source_lang) FROM squad_row_source r
                 WHERE r.club_season_id = pcs.club_season_id AND r.player_id = pcs.player_id) AS listed_in
        FROM player_club_season pcs JOIN club_season cs ON cs.id = pcs.club_season_id JOIN season s ON s.id = cs.season_id
        JOIN club cl ON cl.id = cs.club_id JOIN player p ON p.id = pcs.player_id LEFT JOIN player_wikidata w ON w.player_id = p.id
        WHERE pcs.stint = 'loan_out' ORDER BY s.start_year, cl.wikipedia_title, p.name""",
    "entity_label": "SELECT qid, lang, label FROM entity_label ORDER BY qid, lang",
    "player_alias": "SELECT name, link_lang, link_title FROM player_alias ORDER BY name",
    "amendment_log": """
        SELECT s.label AS season, cl.wikipedia_title AS club, a.description, a.reason, strftime(a.amended_at, '%Y-%m-%d %H:%M:%S') AS amended_at
        FROM amendment_log a LEFT JOIN season s ON s.id = a.season_id LEFT JOIN club_season cs ON cs.id = a.club_season_id
        LEFT JOIN club cl ON cl.id = cs.club_id ORDER BY a.id""",
    "competition_wikidata": "SELECT co.code AS competition, w.qid FROM competition_wikidata w JOIN competition co ON co.id = w.competition_id ORDER BY co.code",
    "club_work": """
        SELECT wikipedia_title AS club, wikidata_qid, country_qid, city_qid, stadium_qid, league_qid, coord_source, soccerway_id FROM club
        WHERE coalesce(country_qid, city_qid, stadium_qid, league_qid, coord_source, soccerway_id) IS NOT NULL ORDER BY coalesce(wikidata_qid, wikipedia_title)""",
}


def export_work(con: duckdb.DuckDBPyConnection, out: Path) -> dict[str, dict]:
    """Écrit chaque table de travail en Parquet sous `out` et rend leurs entrées de manifeste ({path, sha256, rows, …})."""
    from openfootball.export import _write
    return {name: _write(con, sql, out, f"work_{name}", f"work_{name}") for name, sql in WORK_SQL.items()}


def _stage(con: duckdb.DuckDBPyConnection, data: Path, work: dict[str, dict]) -> None:
    for name in WORK_SQL:
        if name in work:
            con.execute(f"CREATE OR REPLACE TEMP TABLE w_{name} AS SELECT * FROM read_parquet('{(data / work[name]['path']).as_posix()}')")


def _count(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    return len(con.execute(sql).fetchall())


def apply_work(con: duckdb.DuckDBPyConnection, data: Path, work: dict[str, dict], *, log: Callable[[str], None] = print) -> dict[str, int]:
    """Relit l'instantané dans `con` : libellés, QID des clubs, alias, corrections, joueurs prêtés ailleurs puis mouvements.
    Rend le nombre de lignes écrites par table ; ce qui ne se rattache à aucun club-saison ou joueur est compté dans `<table>_ignores`."""
    _stage(con, Path(data), work)
    done: dict[str, int] = {}
    con.execute("BEGIN")
    try:
        if "entity_label" in work:
            done["entity_label"] = _count(con, "INSERT INTO entity_label SELECT qid, lang, label FROM w_entity_label ON CONFLICT DO NOTHING RETURNING 1")
        if "club_work" in work:
            for cond in ("club.wikidata_qid = x.wikidata_qid", "club.wikidata_qid IS NULL AND club.wikipedia_title = x.club"):
                con.execute(f"""UPDATE club SET country_qid = coalesce(club.country_qid, x.country_qid), city_qid = coalesce(club.city_qid, x.city_qid),
                    stadium_qid = coalesce(club.stadium_qid, x.stadium_qid), league_qid = coalesce(club.league_qid, x.league_qid),
                    coord_source = coalesce(club.coord_source, x.coord_source), soccerway_id = coalesce(club.soccerway_id, x.soccerway_id)
                    FROM w_club_work x WHERE {cond}""")
            done["club_work"] = con.execute("SELECT count(*) FROM w_club_work").fetchone()[0]
        if "player_alias" in work:
            done["player_alias"] = _count(con, "INSERT INTO player_alias SELECT name, link_lang, link_title FROM w_player_alias ON CONFLICT DO NOTHING RETURNING 1")
        if "competition_wikidata" in work:
            done["competition_wikidata"] = _count(con, """INSERT INTO competition_wikidata SELECT co.id, x.qid FROM w_competition_wikidata x
                                                         JOIN competition co ON co.code = x.competition ON CONFLICT DO NOTHING RETURNING 1""")
        if "amendment_log" in work:
            n0 = con.execute("SELECT count(*) FROM amendment_log").fetchone()[0]
            con.execute("""INSERT INTO amendment_log (id, season_id, club_season_id, description, reason, amended_at)
                           SELECT (SELECT coalesce(max(id), 0) FROM amendment_log) + row_number() OVER (ORDER BY x.amended_at, x.description), s.id, cs.id,
                                  x.description, x.reason, CAST(x.amended_at AS TIMESTAMP)
                           FROM w_amendment_log x LEFT JOIN season s ON s.label = x.season LEFT JOIN club c ON c.wikipedia_title = x.club
                           LEFT JOIN club_season cs ON cs.club_id = c.id AND cs.season_id = s.id
                           WHERE NOT EXISTS (SELECT 1 FROM amendment_log a WHERE a.description = x.description AND a.reason IS NOT DISTINCT FROM x.reason)""")
            done["amendment_log"] = con.execute("SELECT count(*) FROM amendment_log").fetchone()[0] - n0
        if "loan_out" in work:
            done.update(_apply_loan_out(con))
        if "squad_movement" in work:
            done.update(_apply_movements(con))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    log("  instantané de travail : " + ", ".join(f"{k} {v}" for k, v in done.items()))
    return done


def _resolve_players(con: duckdb.DuckDBPyConnection, table: str) -> None:
    """Ajoute `player_id` (ou NULL) à la table d'étape : QID, puis page liée, puis nom dans le même club-saison (un seul joueur de ce nom)."""
    con.execute(f"ALTER TABLE {table} ADD COLUMN player_id INTEGER")
    con.execute(f"UPDATE {table} SET player_id = w.player_id FROM player_wikidata w WHERE {table}.player_qid = w.qid")
    con.execute(f"""UPDATE {table} SET player_id = l.player_id FROM player_link l
                    WHERE {table}.player_id IS NULL AND {table}.link_title IS NOT NULL AND l.link_lang = {table}.link_lang AND l.link_title = {table}.link_title""")
    con.execute(f"""UPDATE {table} SET player_id = q.player_id FROM
                      (SELECT t.rowid AS rid, any_value(p.id) AS player_id FROM {table} t JOIN club c ON c.wikipedia_title = t.club JOIN season s ON s.label = t.season
                       JOIN club_season cs ON cs.club_id = c.id AND cs.season_id = s.id JOIN player_club_season pcs ON pcs.club_season_id = cs.id
                       JOIN player p ON p.id = pcs.player_id AND p.name = t.player WHERE t.player_id IS NULL GROUP BY t.rowid HAVING count(DISTINCT p.id) = 1) q
                    WHERE {table}.rowid = q.rid""")


def _apply_loan_out(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Les joueurs prêtés ailleurs retrouvent leur ligne d'effectif (`stint = 'loan_out'`, absente de l'export du site) ; un joueur inconnu est créé."""
    _resolve_players(con, "w_loan_out")
    # un joueur absent de la base reconstruite (il n'était QUE prêté) est créé, une fois par QID ou, à défaut, par nom (même clé que le site)
    con.execute("""CREATE OR REPLACE TEMP TABLE w_new AS
                   SELECT row_number() OVER (ORDER BY k) + (SELECT coalesce(max(id), 0) FROM player) AS id, k, name, qid, link_lang, link_title FROM
                     (SELECT coalesce(player_qid, 'name:' || player) AS k, any_value(player) AS name, any_value(player_qid) AS qid,
                             any_value(link_lang) AS link_lang, any_value(link_title) AS link_title
                      FROM w_loan_out WHERE player_id IS NULL GROUP BY 1)""")
    con.execute("""INSERT INTO player (id, name, link_lang, link_title, wikidata_qid)
                   SELECT n.id, n.name, CASE WHEN l.link_title IS NULL THEN n.link_lang END, CASE WHEN l.link_title IS NULL THEN n.link_title END, n.qid
                   FROM w_new n LEFT JOIN player_link l ON l.link_lang = n.link_lang AND l.link_title = n.link_title""")
    con.execute("INSERT INTO player_wikidata SELECT id, qid FROM w_new WHERE qid IS NOT NULL ON CONFLICT DO NOTHING")
    con.execute("""INSERT INTO player_link SELECT n.link_lang, n.link_title, n.id FROM w_new n JOIN player p ON p.id = n.id
                   WHERE p.link_title IS NOT NULL ON CONFLICT DO NOTHING""")
    created = con.execute("SELECT count(*) FROM w_new").fetchone()[0]
    con.execute("""UPDATE w_loan_out SET player_id = n.id FROM w_new n
                   WHERE w_loan_out.player_id IS NULL AND coalesce(w_loan_out.player_qid, 'name:' || w_loan_out.player) = n.k""")
    n0 = con.execute("SELECT count(*) FROM player_club_season WHERE stint = 'loan_out'").fetchone()[0]
    con.execute("""INSERT INTO player_club_season (id, player_id, club_season_id, shirt_number, position_code, position_raw, nationality_raw, stint, confidence, source, source_section)
                   SELECT (SELECT coalesce(max(id), 0) FROM player_club_season) + row_number() OVER (ORDER BY cs.id, x.player_id), x.player_id, cs.id, x.shirt_number,
                          x.position_code, x.position_raw, x.nationality_raw, 'loan_out', x.confidence, x.source, x.source_section
                   FROM (SELECT DISTINCT ON (season, club, player_id) * FROM w_loan_out WHERE player_id IS NOT NULL) x
                   JOIN season s ON s.label = x.season JOIN club c ON c.wikipedia_title = x.club JOIN club_season cs ON cs.club_id = c.id AND cs.season_id = s.id
                   ON CONFLICT DO NOTHING""")
    written = con.execute("SELECT count(*) FROM player_club_season WHERE stint = 'loan_out'").fetchone()[0] - n0
    con.execute("""INSERT INTO squad_row_source (club_season_id, player_id, source_lang)
                   SELECT DISTINCT cs.id, l.player_id, trim(l.lang) FROM (SELECT season, club, player_id, unnest(string_split(listed_in, ',')) AS lang
                                                                           FROM w_loan_out WHERE player_id IS NOT NULL AND listed_in IS NOT NULL) l
                   JOIN season s ON s.label = l.season JOIN club c ON c.wikipedia_title = l.club JOIN club_season cs ON cs.club_id = c.id AND cs.season_id = s.id
                   WHERE EXISTS (SELECT 1 FROM player_club_season pcs WHERE pcs.club_season_id = cs.id AND pcs.player_id = l.player_id)
                   ON CONFLICT DO NOTHING""")
    total = con.execute("SELECT count(*) FROM w_loan_out").fetchone()[0]
    return {"loan_out": written, "loan_out_joueurs_crees": created, "loan_out_ignores": total - written}


def _apply_movements(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    _resolve_players(con, "w_squad_movement")
    n0 = con.execute("SELECT count(*) FROM squad_movement").fetchone()[0]
    con.execute("""INSERT INTO squad_movement (club_season_id, player_id, direction, kind, moved_on, transfer_window, other_club, other_club_link, mid_season, source_title)
                   SELECT cs.id, x.player_id, x.direction, x.kind, CAST(x.moved_on AS DATE), x.transfer_window, x.other_club, x.other_club_link, x.mid_season, x.source_title
                   FROM w_squad_movement x JOIN season s ON s.label = x.season JOIN club c ON c.wikipedia_title = x.club JOIN club_season cs ON cs.club_id = c.id AND cs.season_id = s.id
                   WHERE x.player_id IS NOT NULL ON CONFLICT DO NOTHING""")
    written = con.execute("SELECT count(*) FROM squad_movement").fetchone()[0] - n0
    total = con.execute("SELECT count(*) FROM w_squad_movement").fetchone()[0]
    return {"squad_movement": written, "squad_movement_ignores": total - written}


def recover_work(target: duckdb.DuckDBPyConnection, source_db: str | Path, *, log: Callable[[str], None] = print) -> dict[str, int]:
    """Récupère l'instantané de travail depuis une ancienne base de travail (`source_db`, ouverte en lecture seule) vers `target`."""
    src = duckdb.connect(str(source_db), read_only=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            work = export_work(src, Path(tmp))
            return apply_work(target, Path(tmp), work, log=log)
    finally:
        src.close()
