"""Deux défauts relevés par l'audit : un vainqueur rattaché au club omnisports (sans effectif), et une année lue comme un nombre de matches."""
import duckdb

from openfootball.db import migrate
from openfootball.honours import relink_winner_clubs
from openfootball.stats import clean_implausible_apps


def _db():
    c = duckdb.connect(":memory:")
    migrate(c)
    c.execute("INSERT INTO country VALUES ('TUR', 'Turkey', 'Turquie')")
    c.execute("INSERT INTO competition (id, code, name_en, name_fr, country_code, level) VALUES (1, 'TUR-SL', 'Süper Lig', 'Süper Lig', 'TUR', 1)")
    c.execute("INSERT INTO season (id, start_year, label) VALUES (1, 2017, '2017/18')")
    # le club omnisports (QID du palmarès, aucun effectif) et sa section football (effectifs)
    c.execute("INSERT INTO club (id, name_en, country_code, wikipedia_title, wikidata_qid) VALUES (1, 'Galatasaray S.K.', NULL, 'Galatasaray S.K.', 'Q43134')")
    c.execute("INSERT INTO club (id, name_en, country_code, wikipedia_title, wikidata_qid) VALUES (2, 'Galatasaray S.K.', 'TUR', 'Galatasaray S.K. (football)', 'Q495299')")
    c.execute("INSERT INTO club_season (id, club_id, season_id, competition_id) VALUES (1, 2, 1, 1)")
    return c


def test_winner_is_relinked_to_the_club_that_has_squads():
    c = _db()
    c.execute("INSERT INTO competition_winner (competition_id, season_start, winner_qid, winner_name, club_id, season_qid) VALUES (1, 2017, 'Q43134', 'Galatasaray', 1, 'x')")
    assert relink_winner_clubs(c) == 1
    assert c.execute("SELECT club_id FROM competition_winner").fetchone()[0] == 2
    assert relink_winner_clubs(c) == 0                                                  # idempotent


def test_winner_already_on_a_club_with_squads_is_left_alone():
    c = _db()
    c.execute("INSERT INTO competition_winner (competition_id, season_start, winner_qid, winner_name, club_id, season_qid) VALUES (1, 2017, 'Q495299', 'Galatasaray', 2, 'x')")
    assert relink_winner_clubs(c) == 0


def test_season_year_read_as_appearances_is_cleared_but_real_totals_are_kept():
    c = duckdb.connect(":memory:")
    migrate(c)
    c.execute("INSERT INTO player (id, name) VALUES (1, 'Nukri Revishvili')")
    rows = [("2010", "Anzhi", "League", 2010, 14),          # l'année lue comme un nombre de matches
            ("2006", "Rubin", "League", 2006, 4),
            ("1998–04", "Zagreb", "League", 124, 28),       # plusieurs saisons : un total possible
            ("2010–11", "Club", "League", 34, 5),           # saison normale
            ("2010–11", "Club", "League", 101, 5),          # plus de matches de championnat qu'une saison n'en compte
            ("2010", "Autre", "Cup", 90, 2)]
    for seq, (season, club, group, apps, goals) in enumerate(rows, 1):
        c.execute("INSERT INTO player_stat_club (player_id, seq, club, season, competition_group, apps, goals) VALUES (1, ?, ?, ?, ?, ?, ?)", [seq, club, season, group, apps, goals])
    assert clean_implausible_apps(c) == 3
    assert [r[0] for r in c.execute("SELECT apps FROM player_stat_club ORDER BY seq").fetchall()] == [None, None, 124, 34, None, 90]


def test_dates_and_table_values_are_not_player_names():
    from openfootball.parse.squad import is_excluded_section, looks_like_non_player
    for name in ("14 February", "3 May", "26 April", "3 May 2014", "1er mars", "Loan", "loaned", "Total", "12", "", "—"):
        assert looks_like_non_player(name), name
    for name in ("Kylian Mbappé", "Jean-Claude Van Damme", "Alex", "Seydou Doumbia", "Rúben Dias"):
        assert not looks_like_non_player(name), name
    assert is_excluded_section("Suspensions") and is_excluded_section("Sanctions")        # un tableau de suspensions n'est pas un effectif


def test_non_players_are_removed_with_their_squad_rows_and_the_removal_is_logged():
    from openfootball.reconcile import remove_non_players
    c = _db()
    for pid, name in ((10, "3 May"), (11, "Real Player"), (12, "Loan")):
        c.execute("INSERT INTO player (id, name) VALUES (?, ?)", [pid, name])
        c.execute("INSERT INTO player_club_season (id, player_id, club_season_id, confidence, source, stint) VALUES (?, ?, 1, 'attested', 'wikipedia_season', 'full')", [pid, pid])
    assert remove_non_players(c) == 2
    assert [r[0] for r in c.execute("SELECT name FROM player ORDER BY id").fetchall()] == ["Real Player"]
    assert c.execute("SELECT count(*) FROM player_club_season").fetchone()[0] == 1
    assert c.execute("SELECT count(*) FROM amendment_log").fetchone()[0] == 2
    assert remove_non_players(c) == 0                                                       # idempotent


def test_a_player_with_a_wikipedia_page_is_never_removed_even_with_an_odd_name():
    from openfootball.reconcile import remove_non_players
    c = _db()
    c.execute("INSERT INTO player (id, name, link_lang, link_title) VALUES (20, '3 May', 'en', '3 May (footballer)')")
    assert remove_non_players(c) == 0


def _squad_db():
    c = duckdb.connect(":memory:")
    migrate(c)
    c.execute("INSERT INTO country VALUES ('JPN', 'Japan', 'Japon')")
    c.execute("INSERT INTO competition (id, code, name_en, name_fr, country_code, level) VALUES (1, 'JPN-L1', 'J1', 'J1', 'JPN', 1)")
    for sid, y, st in ((1, 2011, 'backfill'), (2, 2026, 'open')):
        c.execute("INSERT INTO season (id, start_year, label, status) VALUES (?, ?, ?, ?)", [sid, y, f"{y}/x", st])
    c.execute("INSERT INTO season (id, start_year, label, status, frozen_at, content_hash) VALUES (3, 2000, '2000/x', 'frozen', now(), 'h')")
    c.execute("INSERT INTO club (id, name_en, country_code, wikipedia_title) VALUES (1, 'Cerezo Osaka', 'JPN', 'Cerezo Osaka')")
    # 2011 : source = page du CLUB (effectif actuel) ; 2026 : page du club aussi mais saison en cours ; 2000 : figée, page du club
    for csid, sid, src in ((1, 1, "Cerezo Osaka"), (2, 2, "Cerezo Osaka"), (3, 3, "Cerezo Osaka")):
        c.execute("INSERT INTO club_season (id, club_id, season_id, competition_id, source_title) VALUES (?, 1, ?, 1, ?)", [csid, sid, src])
    rows = [(1, 1, "Young Player", "First-team squad"), (2, 2, "Current Player", "First-team squad"),
            (3, 2, "Old Legend", "Most appearances"), (4, 2, "Retired Shirt", "Retired numbers"), (5, 3, "Frozen Player", "First-team squad")]
    for i, (pid, csid, name, section) in enumerate(rows, 1):
        c.execute("INSERT INTO player (id, name) VALUES (?, ?)", [pid, name])
        c.execute("INSERT INTO player_club_season (id, player_id, club_season_id, confidence, source, source_section, stint) "
                  "VALUES (?, ?, ?, 'attested', 'wikipedia_season', ?, 'full')", [i, pid, csid, section])
    return c


def test_record_tables_and_current_squads_read_for_a_past_season_are_purged():
    from openfootball.parse.squad import is_excluded_section
    from openfootball.reconcile import purge_misplaced_squads
    assert is_excluded_section("Most appearances") and is_excluded_section("Top 10 scorers of all time") and is_excluded_section("Retired numbers")
    assert not is_excluded_section("First-team squad") and not is_excluded_section("Squad")
    c = _squad_db()
    done = purge_misplaced_squads(c, log=lambda *_: None)
    assert done == {"records": 2, "page_du_club": 1}
    left = [r[0] for r in c.execute("SELECT p.name FROM player_club_season pcs JOIN player p ON p.id = pcs.player_id ORDER BY p.id").fetchall()]
    assert left == ["Current Player", "Frozen Player"]             # la saison en cours et la saison figée gardent leurs lignes (hors tableaux de records)
    assert c.execute("SELECT count(*) FROM known_gap WHERE club_season_id = 1").fetchone()[0] == 1          # le club-saison passé devient un trou connu
    assert c.execute("SELECT count(*) FROM amendment_log").fetchone()[0] == 3
    assert purge_misplaced_squads(c, log=lambda *_: None) == {"records": 0, "page_du_club": 0}              # idempotent
