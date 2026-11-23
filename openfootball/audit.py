"""Contrôles de cohérence sur l'ensemble de la base (palmarès, statistiques, carrières), à lancer avant chaque publication.

`checks.py` vérifie une saison avant son gel ; ici on cherche les incohérences qui traversent les saisons : un titre attribué à un club qui n'a pas joué
la compétition, un joueur qui a des statistiques avant ses 14 ans (deux homonymes fusionnés, le plus souvent), un titre vacant revenu après un import.
Un problème `blocking` doit empêcher la publication ; un `warning` est à relire (le détail dit quoi regarder).
"""
from __future__ import annotations

import duckdb

from openfootball.checks import Problem
from openfootball.honours import VACANT
from openfootball.matches import STANDINGS_SQL
from datetime import date

from openfootball.enrich import MIN_BIRTH_YEAR, MIN_PLAYER_AGE
from openfootball.names import clean_person_name
from openfootball.reconcile import _distinct, _identity, implausible_stays, non_players, orphan_player_ids, slot_support, squad_duplicate_pairs, unproven_variant

MIN_FIELD = 10            # une compétition-saison n'est « connue en entier » qu'avec au moins ce nombre de clubs inscrits
MIN_AGE_STATS = 13        # âge minimal pour une ligne de statistiques (Falcao joue à 13 ans) ; la carrière commence avec les équipes de jeunes, dès 7 ans
MIN_AGE_CAREER = 7
MAX_LEAGUE_APPS = 80      # plus de matches de championnat dans une saison : lecture erronée
MIN_NATIONAL_SQUAD, MAX_NATIONAL_SQUAD = 11, 40
LIMIT = 25                # cas listés par contrôle (le total est toujours donné)


def _scan(con: duckdb.DuckDBPyConnection, check: str, severity: str, sql: str, what: str, args: list | None = None) -> list[Problem]:
    """Une requête `SELECT scope, detail …` : un problème par ligne (au plus LIMIT), plus une ligne de total si elle en retourne davantage."""
    rows = con.execute(sql, args or []).fetchall()
    out = [Problem(check, severity, str(scope), str(detail)) for scope, detail in rows[:LIMIT]]
    if len(rows) > LIMIT:
        out.append(Problem(check, severity, f"{len(rows)} cas", f"{what} (les {LIMIT} premiers sont listés)"))
    return out


def _listed(check: str, severity: str, items: list[tuple[str, str]], what: str) -> list[Problem]:
    """Comme `_scan`, pour des cas calculés en Python : (portée, détail) ; au plus LIMIT listés, plus le total."""
    out = [Problem(check, severity, scope, detail) for scope, detail in items[:LIMIT]]
    if len(items) > LIMIT:
        out.append(Problem(check, severity, f"{len(items)} cas", f"{what} (les {LIMIT} premiers sont listés)"))
    return out


def _identity_problems(con: duckdb.DuckDBPyConnection) -> list[Problem]:
    """Qualité des fiches de joueurs : un nom propre, un vrai joueur, une seule fiche par personne dans un effectif."""
    out: list[Problem] = []
    names = dict(con.execute("SELECT id, name FROM player").fetchall())
    out += _listed("name_artifact", "blocking", [(n, f"devrait s'écrire « {clean_person_name(n)} » : reste de wikicode ou annotation dans le nom")
                                                 for n in names.values() if clean_person_name(n) != n],
                   "noms de joueurs avec des restes de wikicode (`openfootball reconcile` les nettoie)")
    out += _listed("not_a_player", "blocking", [(name, why) for _, name, why in non_players(con)],
                   "« joueurs » qui n'en sont pas (club, fédération, code pays, date lus dans un effectif ; `openfootball reconcile` les retire)")
    out += _scan(con, "birth_impossible", "blocking", """
        SELECT p.name || ' (' || b.birth_date || ')', 'date de naissance impossible pour un joueur : homonyme historique ou erreur Wikidata'
        FROM player_birth b JOIN player p ON p.id = b.player_id WHERE year(b.birth_date) < ? OR year(b.birth_date) > ?""",
                 "dates de naissance impossibles (`openfootball reconcile` les efface)", [MIN_BIRTH_YEAR, date.today().year - MIN_PLAYER_AGE])
    orphans = orphan_player_ids(con)
    out += _listed("orphan_player", "warning", [(names[p], "plus rien ne le référence : fiche vide") for p in orphans],
                   "fiches de joueurs sans effectif, carrière, statistiques ni match (`openfootball reconcile` les retire)")
    ident = {pid: _identity(qid, title) for pid, qid, title in con.execute(
        "SELECT p.id, coalesce(p.wikidata_qid, w.qid), p.link_title FROM player p LEFT JOIN player_wikidata w ON w.player_id = p.id").fetchall()}
    club = {cs: f"{c} {s}" for cs, c, s in con.execute(
        "SELECT x.id, cl.name_en, s.label FROM club_season x JOIN club cl ON cl.id = x.club_id JOIN season s ON s.id = x.season_id").fetchall()}
    twice, homonyms = [], []
    careers = dict(con.execute("SELECT player_id, count(*) FROM player_career GROUP BY 1").fetchall())
    all_pairs = squad_duplicate_pairs(con)
    distinct = [(a, b, cs) for a, b, cs in all_pairs
                if _distinct(ident[a], ident[b]) and not unproven_variant(ident[a], ident[b], careers.get(a, 0), careers.get(b, 0), names[a], names[b])]
    support = slot_support(con, distinct)
    for a, b, cs in all_pairs:
        if (a, b, cs) in support:
            if not all(support[(a, b, cs)]):                     # carrières des deux prouvées : deux vrais joueurs du même nom, pas un problème
                homonyms.append((f"{names[a]} / {names[b]} — {club[cs]}", ""))
        else:
            twice.append((f"{names[a]} / {names[b]} — {club[cs]}", ""))
    out += _listed("squad_duplicate", "blocking", [(s, "même joueur cité deux fois dans l'effectif (`openfootball reconcile` les fusionne)") for s, _ in twice],
                   "joueurs cités deux fois dans un même effectif")
    out += _listed("squad_homonym", "warning", [(s, "deux identités différentes pour la même place : l'une est un homonyme lié à tort, la carrière ne tranche pas") for s, _ in homonyms],
                   "places d'effectif revendiquées par deux identités")
    return out


BIG_COMPETITIONS = ("ENG-PL", "ESP-LL", "ITA-SA", "DEU-BL", "FRA-L1", "UEFA-CL")      # les cinq premières divisions et la Ligue des champions : exigence maximale
CHAMPIONS_LEAGUE_MATCHES = {"2019/20": 119}          # 125 matchs par saison (96 de poules + 29 de phase finale) ; 119 en 2019/20 (phase finale à partir des huitièmes en match unique) ; 189 depuis 2024/25
CHAMPIONS_LEAGUE_NEW_FORMAT = 2024


def _match_problems(con: duckdb.DuckDBPyConnection) -> list[Problem]:
    """Qualité des résultats : un club pour un seul nom d'équipe, des scores partout, le bon nombre de matchs, des buts qui font le score."""
    out: list[Problem] = []
    names = con.execute("""WITH t AS (SELECT competition_code c, season_label s, home_club_id cid, home_name n FROM match WHERE home_club_id IS NOT NULL
                           UNION SELECT competition_code, season_label, away_club_id, away_name FROM match WHERE away_club_id IS NOT NULL)
                           SELECT c, s, cid, list(DISTINCT n) FROM t GROUP BY ALL""").fetchall()
    from openfootball.matches import norm
    clash = [(f"{c} {s}", " | ".join(sorted(ns)) + " : un seul club pour plusieurs équipes") for c, s, _, ns in names if len({norm(n) for n in ns}) > 1]
    out += _listed("club_name_collision", "blocking", [x for x in clash if x[0].split()[0] in BIG_COMPETITIONS], "équipes distinctes rattachées au même club")
    out += _listed("club_name_collision", "warning", [x for x in clash if x[0].split()[0] not in BIG_COMPETITIONS], "équipes distinctes rattachées au même club (autres compétitions)")

    big = ",".join(f"'{c}'" for c in BIG_COMPETITIONS)
    out += _scan(con, "match_unscored", "warning", f"""
        SELECT competition_code || ' ' || season_label || ' ' || match_date, home_name || ' – ' || away_name || ' : match passé sans score'
        FROM match WHERE ft_home IS NULL AND match_date < current_date - 1 AND competition_code IN ({big}) ORDER BY match_date""",
                 "matchs passés sans score (les compléter, ou les retirer si la saison a été arrêtée)")

    d1 = con.execute(f"""SELECT competition_code, season_label, count(*) n, count(DISTINCT home_club_id) teams FROM match
                         WHERE competition_code IN ({big}) AND competition_code <> 'UEFA-CL' AND home_club_id IS NOT NULL GROUP BY ALL""").fetchall()
    this_season = date.today().year if date.today().month >= 7 else date.today().year - 1
    wrong = [(f"{c} {s}", f"{n} matchs pour {t} clubs : {t * (t - 1)} attendus") for c, s, n, t in d1
             if int(s[:4]) < this_season and n != t * (t - 1) and not (c == "FRA-L1" and s == "2019/20")]
    out += _listed("season_match_count", "warning", wrong, "saisons dont le nombre de matchs n'est pas celui d'un championnat complet")
    ucl = con.execute("SELECT season_label, count(*) FROM match WHERE competition_code = 'UEFA-CL' GROUP BY 1").fetchall()
    expected = lambda s: CHAMPIONS_LEAGUE_MATCHES.get(s, 189 if int(s[:4]) >= CHAMPIONS_LEAGUE_NEW_FORMAT else 125)
    out += _listed("season_match_count", "warning", [(f"UEFA-CL {s}", f"{n} matchs : {expected(s)} attendus") for s, n in ucl if int(s[:4]) < this_season and n != expected(s)],
                   "éditions de la Ligue des champions dont le nombre de matchs n'est pas le bon")

    out += _scan(con, "match_goals_vs_score", "blocking", f"""
        WITH g AS (SELECT match_id, sum((side = 'home')::INT) gh, sum((side = 'away')::INT) ga FROM match_goal GROUP BY 1)
        SELECT m.competition_code || ' ' || m.season_label || ' ' || m.match_date, m.home_name || ' ' || m.ft_home || '-' || m.ft_away || ' ' || m.away_name || ' : ' || g.gh || '-' || g.ga || ' buts détaillés'
        FROM match m JOIN g ON g.match_id = m.id WHERE m.ft_home IS NOT NULL AND (g.gh <> m.ft_home OR g.ga <> m.ft_away) AND m.competition_code IN ({big})""",
                 "matchs dont les buts détaillés ne font pas le score")
    return out


def run_audit(con: duckdb.DuckDBPyConnection) -> list[Problem]:
    out: list[Problem] = _identity_problems(con) + _match_problems(con)
    for code, year in VACANT:
        out += _scan(con, "vacant_title", "blocking", """
            SELECT co.code || ' ' || w.season_start, 'titre vacant présent : ' || w.winner_name
            FROM competition_winner w JOIN competition co ON co.id = w.competition_id WHERE co.code = ? AND w.season_start = ?""",
                     "titres vacants revenus dans le palmarès", [code, year])

    out += _scan(con, "winner_not_in_field", "warning", f"""
        SELECT co.code || ' ' || w.season_start, w.winner_name || ' sans effectif cette saison (' || f.n || ' clubs inscrits dans la compétition)'
        FROM competition_winner w JOIN competition co ON co.id = w.competition_id
        JOIN (SELECT cs.competition_id, s.start_year, count(DISTINCT cs.club_id) n, list(DISTINCT cs.club_id) clubs
              FROM club_season cs JOIN season s ON s.id = cs.season_id GROUP BY ALL HAVING count(DISTINCT cs.club_id) >= {MIN_FIELD}) f
          ON f.competition_id = w.competition_id AND f.start_year = w.season_start
        WHERE w.club_id IS NOT NULL AND NOT list_contains(f.clubs, w.club_id)
          AND NOT EXISTS (SELECT 1 FROM club_season x JOIN season sx ON sx.id = x.season_id WHERE x.club_id = w.club_id AND sx.start_year = w.season_start)
        ORDER BY co.code, w.season_start""", "vainqueurs sans aucun effectif cette saison alors que la compétition est connue en entier")

    if con.execute("SELECT count(*) FROM top_scorer").fetchone()[0]:         # classements des buteurs (lus par `topscorers`) : chaque saison passée des cinq premières divisions a le sien, du plus au moins de buts
        out += _scan(con, "top_scorer_missing", "warning", f"""
            SELECT co.code || ' ' || s.label, 'saison terminée sans classement des buteurs'
            FROM competition co CROSS JOIN season s
            WHERE co.code IN ('ENG-PL', 'ESP-LL', 'ITA-SA', 'DEU-BL', 'FRA-L1') AND s.start_year BETWEEN 2010 AND {date.today().year - 1 - (0 if date.today().month >= 8 else 1)}
              AND EXISTS (SELECT 1 FROM club_season cs WHERE cs.competition_id = co.id AND cs.season_id = s.id)
              AND NOT EXISTS (SELECT 1 FROM top_scorer t WHERE t.competition_code = co.code AND t.season_label = s.label)
            ORDER BY co.code, s.label""", "saisons terminées sans classement des buteurs")
        out += _scan(con, "top_scorer_order", "blocking", """
            SELECT competition_code || ' ' || season_label || ' ' || player_name, 'rang incohérent avec les buts : ' || goals || ' buts, rang ' || rank
            FROM top_scorer t WHERE EXISTS (SELECT 1 FROM top_scorer u WHERE u.competition_code = t.competition_code AND u.season_label = t.season_label
                                            AND ((u.goals > t.goals AND u.rank >= t.rank) OR (u.goals = t.goals AND u.rank <> t.rank)))""",
                     "classements de buteurs dont le rang ne suit pas les buts")

    out += _scan(con, "stats_before_birth", "warning", f"""
        SELECT p.name || ' (né en ' || year(b.birth_date) || ')', 'statistiques dès ' || min(s.season) || ' : homonymes fusionnés ou date de naissance fausse ?'
        FROM player_stat_club s JOIN player_birth b ON b.player_id = s.player_id JOIN player p ON p.id = s.player_id
        WHERE b.precision >= 9 AND try_cast(left(s.season, 4) AS INTEGER) < year(b.birth_date) + {MIN_AGE_STATS}
        GROUP BY p.name, b.birth_date ORDER BY p.name""", "joueurs avec des statistiques avant leurs 13 ans")

    out += _scan(con, "career_before_birth", "warning", f"""
        SELECT p.name || ' (né en ' || year(b.birth_date) || ')', 'carrière dès ' || min(c.start_year) || ' : homonymes fusionnés ou date de naissance fausse ?'
        FROM player_career c JOIN player_birth b ON b.player_id = c.player_id JOIN player p ON p.id = c.player_id
        WHERE b.precision >= 9 AND c.start_year < year(b.birth_date) + {MIN_AGE_CAREER}
        GROUP BY p.name, b.birth_date ORDER BY p.name""", "joueurs avec une carrière avant leurs 7 ans")

    # Champion calculé d'après les scores (3 points la victoire) contre le vainqueur du palmarès : seulement pour les championnats complets
    # (chaque équipe a joué 2 × (n − 1) matchs) dont la tête est sans ex æquo — sinon le départage (confrontations directes…) nous échappe.
    out += _scan(con, "champion_mismatch", "warning", f"""
        WITH st AS ({STANDINGS_SQL}),
        sized AS (SELECT *, count(*) OVER (PARTITION BY competition_code, season_label) n,
                  rank() OVER (PARTITION BY competition_code, season_label ORDER BY points DESC) r FROM st),
        full_season AS (SELECT competition_code, season_label FROM sized GROUP BY ALL HAVING min(played) = 2 * (max(n) - 1) AND max(played) = min(played)),
        top AS (SELECT s.* FROM sized s JOIN full_season f USING (competition_code, season_label) WHERE s.r = 1 AND s.club_id IS NOT NULL
                AND (SELECT count(*) FROM sized x WHERE x.competition_code = s.competition_code AND x.season_label = s.season_label AND x.r = 1) = 1)
        SELECT t.competition_code || ' ' || t.season_label,
               'scores : ' || t.team || ' (' || t.points || ' pts) ; palmarès : ' || w.winner_name
        FROM top t JOIN competition co ON co.code = t.competition_code
        JOIN competition_winner w ON w.competition_id = co.id AND w.season_start = try_cast(left(t.season_label, 4) AS INTEGER)
        WHERE w.club_id IS NOT NULL AND w.club_id <> t.club_id
        ORDER BY t.competition_code, t.season_label""", "championnats dont le champion calculé d'après les scores n'est pas le vainqueur du palmarès")

    stays = implausible_stays(con)
    out += [Problem("homonym_stay", "warning", f"{name} — {club} {label}",
                    (f"carrière terminée en {last_end}" if last_end and last_end < 9999 else f"né en {born}")
                    + " : homonyme lié à tort ? (`openfootball reconcile` le détache)")
            for _, _, _, name, _, label, club, _, born, last_end in stays[:LIMIT]]
    if len(stays) > LIMIT:
        out.append(Problem("homonym_stay", "warning", f"{len(stays)} cas",
                           f"lignes d'effectif tenues par un joueur dont l'âge ou la carrière l'interdit (les {LIMIT} premières sont listées)"))

    out += _scan(con, "stats_implausible", "warning", f"""
        SELECT p.name || ' — ' || s.club || ' ' || s.season, s.apps || ' matches, ' || s.goals || ' buts (' || coalesce(s.competition_group, '?') || ')'
        FROM player_stat_club s JOIN player p ON p.id = s.player_id
        WHERE (s.apps > 0 AND s.goals >= 10 AND s.goals > 3 * s.apps) OR (s.competition_group = 'League' AND s.apps > {MAX_LEAGUE_APPS}
               AND NOT (s.season LIKE '%–%' AND (try_cast(right(s.season, 2) AS INTEGER) - try_cast(substr(s.season, 3, 2) AS INTEGER) + 100) % 100 > 1))
        ORDER BY s.goals DESC""", "lignes de statistiques invraisemblables (plus de 3 buts par match, ou trop de matches de championnat)")

    out += _scan(con, "national_squad_size", "warning", f"""
        SELECT competition || ' ' || year, n || ' joueurs'
        FROM (SELECT competition, year, count(*) n FROM national_title GROUP BY ALL)
        WHERE n < {MIN_NATIONAL_SQUAD} OR n > {MAX_NATIONAL_SQUAD}""", "éditions dont la liste est trop courte ou trop longue")

    out += _scan(con, "national_two_champions", "warning", """
        SELECT competition || ' ' || year, string_agg(DISTINCT team, ' / ')
        FROM national_title GROUP BY competition, year HAVING count(DISTINCT team) > 1""", "éditions avec plusieurs équipes victorieuses")
    return out
