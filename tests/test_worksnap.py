"""Instantané de travail : mouvements, joueurs prêtés, libellés, alias et corrections survivent à une reconstruction (numéros internes différents)."""
import duckdb

from openfootball.db import migrate
from openfootball.worksnap import apply_work, export_work, recover_work


def _base(c, shift: int) -> None:
    """Un petit monde ; `shift` décale tous les numéros internes (une base reconstruite les régénère)."""
    migrate(c)
    c.execute("INSERT INTO country VALUES ('FRA', 'France', 'France')")
    c.execute("INSERT INTO competition (id, code, name_en, name_fr, country_code, level) VALUES (?, 'FRA-L2', 'L2', 'L2', 'FRA', 2)", [1 + shift])
    c.execute("INSERT INTO season (id, start_year, label) VALUES (?, 2026, '2026/27')", [1 + shift])
    for cid, title, qid in ((1, "AS Nancy", "Q100"), (2, "Lille OSC", "Q200")):
        c.execute("INSERT INTO club (id, name_en, country_code, wikipedia_title, wikidata_qid) VALUES (?, ?, 'FRA', ?, ?)", [cid + shift, title, title, qid])
        c.execute("INSERT INTO club_season (id, club_id, season_id, competition_id) VALUES (?, ?, ?, ?)", [cid + shift, cid + shift, 1 + shift, 1 + shift])
    c.execute("INSERT INTO player (id, name, link_lang, link_title, wikidata_qid) VALUES (?, 'Ilyes Housni', 'en', 'Ilyes Housni', 'Q1')", [1 + shift])
    c.execute("INSERT INTO player_wikidata VALUES (?, 'Q1')", [1 + shift])
    c.execute("INSERT INTO player_link VALUES ('en', 'Ilyes Housni', ?)", [1 + shift])
    c.execute("INSERT INTO player (id, name) VALUES (?, 'Another Loose')", [4 + shift])
    for rid, pid, cs in ((1, 1, 1), (2, 4, 1)):
        c.execute("INSERT INTO player_club_season (id, player_id, club_season_id, confidence, source, stint) VALUES (?, ?, ?, 'attested', 'wikipedia_season', 'full')",
                  [rid + shift, pid + shift, cs + shift])


def _rich(c) -> None:
    """Ce que la source a en plus : deux joueurs prêtés ailleurs (un identifié, un sans QID), mouvements, libellés, alias, correction."""
    c.execute("INSERT INTO player (id, name, link_lang, link_title, wikidata_qid) VALUES (2, 'Loaned Guy', 'en', 'Loaned Guy', 'Q2')")
    c.execute("INSERT INTO player_wikidata VALUES (2, 'Q2')")
    c.execute("INSERT INTO player_link VALUES ('en', 'Loaned Guy', 2)")
    c.execute("INSERT INTO player (id, name) VALUES (3, 'Loose Name')")
    for rid, pid in ((3, 2), (4, 3)):
        c.execute("INSERT INTO player_club_season (id, player_id, club_season_id, shirt_number, confidence, source, stint) VALUES (?, ?, 2, 7, 'attested', 'wikipedia_season', 'loan_out')", [rid, pid])
    c.execute("INSERT INTO squad_row_source VALUES (2, 2, 'fr'), (2, 3, 'en')")
    c.execute("""INSERT INTO squad_movement (club_season_id, player_id, direction, kind, moved_on, transfer_window, other_club, mid_season, source_title)
                 VALUES (1, 1, 'in', 'loan', '2026-08-30', 'summer', 'Lille OSC', false, 'Saison 2026-2027'),
                        (2, 2, 'out', 'loan', '2026-08-30', 'summer', 'AS Nancy', false, 'Saison 2026-2027')""")
    c.execute("UPDATE club SET city_qid = 'Q50', stadium_qid = 'Q51' WHERE id = 1")
    c.execute("INSERT INTO entity_label VALUES ('Q50', 'en', 'Nancy'), ('Q51', 'en', 'Stade Marcel-Picot')")
    c.execute("INSERT INTO player_alias VALUES ('Joseph Layousse', 'fr', 'Layousse Samb')")
    c.execute("INSERT INTO amendment_log (id, season_id, club_season_id, description, reason, amended_at) VALUES (1, 1, 1, 'X retiré de AS Nancy', 'carrière terminée', '2026-11-12 20:52:53')")
    c.execute("INSERT INTO competition_wikidata VALUES (1, 'Q9')")


def _source(tmp_path):
    path = tmp_path / "source.duckdb"
    c = duckdb.connect(str(path))
    _base(c, 0)
    _rich(c)
    c.close()
    return path


def _target():
    c = duckdb.connect(":memory:")
    _base(c, 100)                                   # mêmes données de base, numéros internes différents, rien de ce que la source a en plus
    return c


def _count(c, sql):
    return c.execute(sql).fetchone()[0]


def test_work_data_is_recovered_with_different_internal_ids(tmp_path):
    t = _target()
    done = recover_work(t, _source(tmp_path), log=lambda *_: None)
    assert done["loan_out"] == 2 and done["loan_out_joueurs_crees"] == 2 and done["squad_movement"] == 2
    assert _count(t, "SELECT count(*) FROM player_club_season WHERE stint = 'loan_out'") == 2
    # les mouvements se rattachent à la bonne personne (par QID), pas à un numéro
    assert t.execute("""SELECT m.direction, p.name, c.wikipedia_title, m.other_club FROM squad_movement m JOIN player p ON p.id = m.player_id
                        JOIN club_season cs ON cs.id = m.club_season_id JOIN club c ON c.id = cs.club_id ORDER BY m.direction""").fetchall() == [
        ("in", "Ilyes Housni", "AS Nancy", "Lille OSC"), ("out", "Loaned Guy", "Lille OSC", "AS Nancy")]
    assert _count(t, "SELECT count(*) FROM player WHERE name = 'Loose Name'") == 1
    assert _count(t, "SELECT count(*) FROM squad_row_source WHERE player_id IN (SELECT id FROM player WHERE name IN ('Loaned Guy', 'Loose Name'))") == 2
    assert _count(t, "SELECT count(*) FROM entity_label") == 2
    assert t.execute("SELECT city_qid, stadium_qid FROM club WHERE wikipedia_title = 'AS Nancy'").fetchone() == ("Q50", "Q51")
    assert _count(t, "SELECT count(*) FROM player_alias") == 1 and _count(t, "SELECT count(*) FROM competition_wikidata") == 1
    assert t.execute("SELECT description FROM amendment_log").fetchall() == [("X retiré de AS Nancy",)]
    assert _count(t, "SELECT count(*) FROM player WHERE name = 'Ilyes Housni'") == 1          # aucun doublon de la personne déjà là


def test_recovery_is_idempotent(tmp_path):
    t = _target()
    src = _source(tmp_path)
    recover_work(t, src, log=lambda *_: None)
    tables = ("player", "player_club_season", "squad_movement", "entity_label", "amendment_log", "squad_row_source")
    before = {tbl: _count(t, f"SELECT count(*) FROM {tbl}") for tbl in tables}
    again = recover_work(t, src, log=lambda *_: None)
    assert {tbl: _count(t, f"SELECT count(*) FROM {tbl}") for tbl in tables} == before
    assert again["loan_out"] == 0 and again["squad_movement"] == 0


def test_export_writes_work_tables_with_natural_keys_and_apply_reads_them(tmp_path):
    src = duckdb.connect(str(_source(tmp_path)), read_only=True)
    out = tmp_path / "release"
    work = export_work(src, out)
    assert set(work) == {"squad_movement", "loan_out", "entity_label", "player_alias", "amendment_log", "competition_wikidata", "club_work"}
    assert work["squad_movement"]["rows"] == 2 and work["loan_out"]["rows"] == 2
    cols = [r[0] for r in duckdb.connect().execute(f"DESCRIBE SELECT * FROM read_parquet('{out / work['squad_movement']['path']}')").fetchall()]
    assert {"club", "season", "player_qid"} <= set(cols) and not {"club_season_id", "player_id"} & set(cols)     # clés naturelles, aucun numéro interne
    done = apply_work(_target(), out, work, log=lambda *_: None)
    assert done["squad_movement"] == 2 and done["loan_out"] == 2
