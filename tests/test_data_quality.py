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
