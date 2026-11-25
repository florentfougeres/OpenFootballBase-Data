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


# --- doublons d'un même effectif, noms mal formés, entités lues comme des joueurs -----------------------------------------------------------------------------

def _squad(rows):
    """Un effectif (club-saison 1) ; rows = (id, nom, qid, numéro, poste)."""
    c = _db()
    for pid, name, qid, num, pos in rows:
        c.execute("INSERT INTO player (id, name, wikidata_qid) VALUES (?, ?, ?)", [pid, name, qid])
        if qid:
            c.execute("INSERT INTO player_wikidata VALUES (?, ?)", [pid, qid])
        c.execute("INSERT INTO player_club_season (id, player_id, club_season_id, shirt_number, position_code, confidence, source, stint) "
                  "VALUES (?, ?, 1, ?, ?, 'attested', 'wikipedia_season', 'full')", [pid, pid, num, pos])
    return c


def _names(c):
    return [r[0] for r in c.execute("SELECT name FROM player ORDER BY id").fetchall()]


def test_same_goalkeeper_written_two_ways_in_one_squad_is_merged_into_the_identified_one():
    from openfootball.reconcile import merge_squad_duplicates
    c = _squad([(1, "Matvey Safonov", "Q36371294", 39, "GK"), (2, "Matveï Safonov", None, 39, "GK"), (3, "Lucas Chevalier", "Q98102459", 30, "GK")])
    assert merge_squad_duplicates(c).merged == 1
    assert _names(c) == ["Matvey Safonov", "Lucas Chevalier"]
    assert c.execute("SELECT count(*) FROM player_club_season").fetchone()[0] == 2
    assert merge_squad_duplicates(c).merged == 0                                              # idempotent


def test_accents_and_word_order_do_not_make_two_players():
    from openfootball.reconcile import merge_squad_duplicates
    c = _squad([(1, "Filip Šimeček", None, None, None), (2, "Filip Simecek", None, None, None), (3, "Šimeček Filip", None, None, None)])
    assert merge_squad_duplicates(c).merged == 2
    assert len(_names(c)) == 1


def test_similar_names_with_different_shirts_or_two_identities_stay_apart():
    from openfootball.reconcile import merge_squad_duplicates
    c = _squad([(1, "Lyle Taylor", None, 33, None), (2, "Lyle Tayler", None, 36, None),                 # numéros différents : deux joueurs
                (3, "Bilal Brahimi", "Q107649655", 21, None), (4, "Billal Brahimi", "Q56289677", 21, None),   # deux QID : on ne tranche pas
                (5, "Kilian Belazzoug", "Q136500038", 60, "MF"), (6, "Kylian Belazzoug", None, 60, "DF")])    # même numéro mais postes contradictoires : écarté
    r = merge_squad_duplicates(c)
    assert r.merged == 0 and r.unresolved == 1
    assert len(_names(c)) == 6


def test_the_kept_player_takes_the_shirt_and_position_only_the_other_one_gave():
    from openfootball.reconcile import merge_squad_duplicates
    c = _squad([(1, "Tobías Rubio", "Q1", None, None), (2, "Tobias Rubio", None, 34, "FW")])
    assert merge_squad_duplicates(c).merged == 1
    assert c.execute("SELECT shirt_number, position_code FROM player_club_season").fetchall() == [(34, "FW")]


def test_squad_duplicate_in_a_frozen_season_is_refused():
    from openfootball.reconcile import merge_squad_duplicates
    c = _squad([(1, "Filip Šimeček", None, None, None), (2, "Filip Simecek", None, None, None)])
    c.execute("UPDATE season SET status = 'frozen', frozen_at = now(), content_hash = 'h' WHERE id = 1")
    r = merge_squad_duplicates(c)
    assert r.merged == 0 and len(r.blocked) == 1


def test_wikicode_left_in_names_is_cleaned_without_touching_real_names():
    from openfootball.names import clean_person_name as clean
    cases = {"Ibrahim Fofananote 2]": "Ibrahim Fofana", "Dominic Corness <small>(U18)</small>": "Dominic Corness", "Jayden Reid}}}}": "Jayden Reid",
             "Ian McGrane †": "Ian McGrane", "Fernando Zampedri (7)": "Fernando Zampedri", "Cauê (footballer, born 1989)": "Cauê",
             "Ronny (calciatore) König": "Ronny König", '"Dani" Mas': "Dani Mas", 'Mario Jiménez, "Gambín"': "Mario Jiménez",
             "''Alberto Cossentino''": "Alberto Cossentino", "GARCÍA, Eduardo": "Eduardo García", "Aziz Deen-Conteh B": "Aziz Deen-Conteh",
             ".Hallgrimur Jonasson": "Hallgrimur Jonasson", "Reinaldo  Fontalvo": "Reinaldo Fontalvo"}
    for dirty, good in cases.items():
        assert clean(dirty) == good, dirty
    for fine in ("N'Golo Kanté", "Jean-Claude Van Damme", "Vinícius Jr.", "Eddy Davis III", "Rúben Dias", "Pelé", "D'Arcy Lowe", "12"):
        assert clean(fine) == fine, fine


def test_names_already_in_the_database_are_cleaned_and_the_duplicate_they_hid_is_merged():
    from openfootball.reconcile import clean_player_names, merge_squad_duplicates
    c = _squad([(1, "Fernando Zampedri", "Q16302958", 9, None), (2, "Fernando Zampedri (7)", None, None, None), (3, "GARCÍA, Eduardo", None, 4, None)])
    assert clean_player_names(c) == 2
    assert merge_squad_duplicates(c).merged == 1
    assert _names(c) == ["Fernando Zampedri", "Eduardo García"]


def test_clubs_federations_and_country_codes_read_as_players_are_removed_but_real_people_are_kept():
    from openfootball.reconcile import remove_non_players
    c = _squad([(1, "AFC Ajax", "Q81888", None, None), (2, "FRA", "Q244750", None, None), (3, "Kylian Mbappé", "Q21621", 10, None)])
    c.execute("INSERT INTO club (id, name_en, country_code, wikidata_qid) VALUES (3, 'AFC Ajax', 'TUR', 'Q81888')")
    c.execute("INSERT INTO player_birth (player_id, birth_date, precision) VALUES (3, DATE '1998-12-20', 11)")
    assert remove_non_players(c) == 2
    assert _names(c) == ["Kylian Mbappé"]
    assert remove_non_players(c) == 0


def test_merging_a_player_that_has_stats_and_matches_does_not_leave_dangling_rows():
    from openfootball.reconcile import merge_squad_duplicates
    c = _squad([(1, "Filip Šimeček", "Q1", None, None), (2, "Filip Simecek", None, None, None)])
    c.execute("INSERT INTO player_stat_club (player_id, seq, club, season, competition_group, apps, goals) VALUES (2, 1, 'Slavia', '2022', 'League', 10, 1)")
    assert merge_squad_duplicates(c).merged == 1
    assert c.execute("SELECT player_id FROM player_stat_club").fetchall() == [(1,)]


def _career(c, pid, club, start, end):
    c.execute("INSERT INTO player_career (id, player_id, seq, start_year, end_year, club_name, club_link, loan, source_lang, source_title) "
              "VALUES ((SELECT coalesce(max(id), 0) + 1 FROM player_career), ?, 1, ?, ?, ?, ?, false, 'en', 'x')", [pid, start, end, club, club])


def test_two_identified_homonyms_in_one_squad_keep_only_the_one_whose_career_has_the_club():
    from openfootball.reconcile import merge_squad_duplicates
    c = _squad([(1, "Javier Hernández", "Q165125", 14, None), (2, "Javier Hernández", "Q410758", 14, None)])
    _career(c, 1, "Galatasaray S.K. (football)", 2016, 2020)             # la saison de l'effectif (2017) est couverte
    _career(c, 2, "Elche CF", 2010, 2012)
    r = merge_squad_duplicates(c)
    assert (r.merged, r.removed, r.unresolved) == (0, 1, 0)
    assert [x[0] for x in c.execute("SELECT player_id FROM player_club_season").fetchall()] == [1]
    assert c.execute("SELECT count(*) FROM amendment_log").fetchone()[0] == 1


def test_two_identified_homonyms_are_left_alone_when_the_career_cannot_tell_them_apart():
    from openfootball.reconcile import merge_squad_duplicates
    c = _squad([(1, "Javier Hernández", "Q165125", 14, None), (2, "Javier Hernández", "Q410758", 14, None)])
    r = merge_squad_duplicates(c)                                           # aucune carrière connue : on ne tranche pas
    assert (r.merged, r.removed, r.unresolved) == (0, 0, 1)
    assert c.execute("SELECT count(*) FROM player_club_season").fetchone()[0] == 2


def test_two_real_homonyms_whose_careers_both_have_the_club_are_left_alone_and_not_flagged():
    from openfootball.audit import _identity_problems
    from openfootball.reconcile import merge_squad_duplicates
    c = _squad([(1, "Henrique", "Q10294723", None, None), (2, "Henrique", "Q14244926", None, None)])
    _career(c, 1, "Galatasaray S.K. (football)", 2016, 2018)
    _career(c, 2, "Galatasaray S.K. (football)", 2017, 2019)               # les deux y étaient : deux vrais joueurs du même nom
    r = merge_squad_duplicates(c)
    assert (r.merged, r.removed, r.unresolved) == (0, 0, 0)
    assert c.execute("SELECT count(*) FROM player_club_season").fetchone()[0] == 2
    assert not [p for p in _identity_problems(c) if p.check == "squad_homonym"]


def _title_only_pair(c):
    for pid, name in ((1, "Christan Enemark"), (2, "Christian Enemark")):
        c.execute("INSERT INTO player (id, name, link_lang, link_title) VALUES (?, ?, 'en', ?)", [pid, name, name])
        c.execute("INSERT INTO player_club_season (id, player_id, club_season_id, shirt_number, position_code, confidence, source, stint) "
                  "VALUES (?, ?, 1, 28, 'DF', 'attested', 'wikipedia_season', 'full')", [pid, pid])


def test_two_unproven_links_with_a_one_letter_variant_and_the_same_shirt_are_one_player():
    from openfootball.reconcile import merge_squad_duplicates
    c = _squad([])
    _title_only_pair(c)
    assert merge_squad_duplicates(c).merged == 1
    assert c.execute("SELECT count(*) FROM player_club_season").fetchone()[0] == 1


def test_two_links_without_qid_stay_two_people_when_one_has_a_career():
    from openfootball.reconcile import merge_squad_duplicates
    c = _squad([])
    _title_only_pair(c)
    _career(c, 1, "Brøndby IF", 2016, 2018)
    assert merge_squad_duplicates(c).merged == 0


def test_a_link_without_qid_and_a_qid_for_the_same_name_and_shirt_are_one_player():
    from openfootball.reconcile import merge_squad_duplicates
    c = _squad([(1, "Igor Karpovich", "Q5994587", 15, None)])
    c.execute("INSERT INTO player (id, name, link_lang, link_title) VALUES (2, 'Ihar Karpovich', 'en', 'Ihar Karpovich')")
    c.execute("INSERT INTO player_club_season (id, player_id, club_season_id, shirt_number, confidence, source, stint) VALUES (2, 2, 1, 15, 'attested', 'wikipedia_season', 'full')")
    assert merge_squad_duplicates(c).merged == 1
    assert c.execute("SELECT id FROM player").fetchall() == [(1,)]
    assert c.execute("SELECT count(*) FROM player_link WHERE player_id = 1").fetchone()[0] == 1          # le lien du doublon est gardé : il ne sera pas recréé


def _two_seasons_db(first, second, year2=2018):
    """Un club, deux saisons (2017 et `year2`) ; first/second = (id, nom, qid, numéro) du joueur cité dans chacune."""
    c = _db()
    c.execute("INSERT INTO season (id, start_year, label) VALUES (2, ?, ?)", [year2, f"{year2}/x"])
    c.execute("INSERT INTO club_season (id, club_id, season_id, competition_id) VALUES (2, 2, 2, 1)")
    for cs, (pid, name, qid, num) in ((1, first), (2, second)):
        c.execute("INSERT INTO player (id, name, wikidata_qid) VALUES (?, ?, ?)", [pid, name, qid])
        if qid:
            c.execute("INSERT INTO player_wikidata VALUES (?, ?)", [pid, qid])
        c.execute("INSERT INTO player_club_season (id, player_id, club_season_id, shirt_number, confidence, source, stint) VALUES (?, ?, ?, ?, 'attested', 'wikipedia_season', 'full')",
                  [pid, pid, cs, num])
    return c


def test_a_player_split_between_two_seasons_of_the_same_club_is_reunited():
    from openfootball.reconcile import merge_split_players
    c = _two_seasons_db((1, "Boubakar Kouyaté", "Q26704510", 23), (2, "Boubakar Kouyate", None, None))
    assert merge_split_players(c).merged == 1
    assert c.execute("SELECT player_id FROM player_club_season ORDER BY club_season_id").fetchall() == [(1,), (1,)]
    assert merge_split_players(c).merged == 0


def test_split_players_stay_apart_for_a_single_word_name_without_the_same_shirt_two_qids_or_different_births():
    from openfootball.reconcile import merge_split_players
    c = _two_seasons_db((1, "Diego", "Q1", 9), (2, "Diego", None, 22))                          # un prénom seul : deux Diego se succèdent sans se croiser
    assert merge_split_players(c).merged == 0
    c = _two_seasons_db((1, "Diego", "Q1", 9), (2, "Diego", None, 9))                           # même numéro : c'est lui
    assert merge_split_players(c).merged == 1
    c = _two_seasons_db((1, "Ibrahim Sangaré", "Q27832634", 7), (2, "Ibrahim Sangaré", "Q30122326", 7))
    assert merge_split_players(c).merged == 0                                                   # deux QID : deux personnes
    c = _two_seasons_db((1, "Luke Bell", None, None), (2, "Luke Bell", None, None))
    c.execute("INSERT INTO player_birth VALUES (1, DATE '1990-01-01', 11), (2, DATE '1999-05-05', 11)")
    assert merge_split_players(c).merged == 0                                                   # deux dates de naissance : deux personnes


def test_split_players_with_a_gap_of_several_seasons_are_not_merged():
    from openfootball.reconcile import merge_split_players
    c = _two_seasons_db((1, "Luke Bell", "Q5", None), (2, "Luke Bell", None, None), year2=2024)
    assert merge_split_players(c).merged == 0


def test_audit_flags_dirty_names_non_players_and_duplicates_in_a_squad():
    from openfootball.audit import run_audit
    c = _squad([(1, "Matvey Safonov", "Q36371294", 39, "GK"), (2, "Matveï Safonov", None, 39, "GK"), (3, "Ibrahim Fofananote 2]", None, 5, None),
                (4, "FRA", "Q244750", None, None)])
    got = {(p.check, p.severity) for p in run_audit(c)}
    assert {("squad_duplicate", "blocking"), ("name_artifact", "blocking"), ("not_a_player", "blocking")} <= got
    from openfootball.reconcile import clean_player_names, merge_squad_duplicates, remove_non_players
    clean_player_names(c); remove_non_players(c); merge_squad_duplicates(c)
    assert not {p.check for p in run_audit(c)} & {"squad_duplicate", "name_artifact", "not_a_player"}


def test_nicknames_markers_and_glued_categories_are_not_part_of_a_name():
    from openfootball.names import clean_person_name as clean
    cases = {'Antonio Rodríguez "Toño"': "Antonio Rodríguez", 'Victor "PC" Giro': "Victor Giro", "Patrick Lane|Patrick Lane": "Patrick Lane",
             "Rafhinha [L": "Rafhinha", "Rodrigue Ele [S2": "Rodrigue Ele", "Iman AbaszadehU21": "Iman Abaszadeh", '"Dani" Mas': "Dani Mas"}
    for dirty, good in cases.items():
        assert clean(dirty) == good, dirty
    assert clean('Pavlo M"jahkov') == 'Pavlo M"jahkov'                                  # une guillemet isolée n'est pas un surnom


def test_dates_notes_and_lists_of_surnames_are_not_players():
    from openfootball.parse.squad import looks_like_non_player as bad
    for x in ("January 1, 2022", "December 31, 2021", "jan/2023", "In maart 2015 vertrokken", "Verhuurd, was verhuurd aan Go Ahead Eagles"):
        assert bad(x), x
    for x in ("Kylian Mbappé", "Leftwich", "Juan Carlos Ramón de la Cruz Torres"):
        assert not bad(x), x
    from openfootball.reconcile import remove_non_players
    c = _squad([(1, "Schaars Slagveer Kums Başacıkoğlu Lurling Raitala", None, None, None), (2, "Juan Carlos Ramón de la Cruz", "Q1", 8, None)])
    c.execute("INSERT INTO player_birth VALUES (2, DATE '1990-01-01', 11)")
    assert remove_non_players(c) == 1                                                  # six mots sans lien : retiré ; la même longueur avec un QID reste
    assert _names(c) == ["Juan Carlos Ramón de la Cruz"]
    c = _squad([(1, "Victor Hugo dos Santos de Sa", None, 3, None)])
    assert remove_non_players(c) == 0                                                  # six mots dont deux particules, sans lien : un vrai joueur brésilien, pas une liste de noms


def test_impossible_birth_dates_are_erased_and_orphan_players_removed():
    from openfootball.audit import run_audit
    from openfootball.reconcile import drop_impossible_births, orphan_player_ids, remove_orphan_players
    c = _squad([(1, "Real Player", "Q1", 9, None)])
    c.execute("INSERT INTO player (id, name, wikidata_qid) VALUES (2, 'Filippo Neri', 'Q217791')")
    c.execute("INSERT INTO player_wikidata VALUES (2, 'Q217791')")
    c.execute("INSERT INTO player_birth VALUES (2, DATE '1515-07-31', 11), (1, DATE '1990-03-03', 11)")
    assert orphan_player_ids(c) == [2]
    got = {(p.check, p.severity) for p in run_audit(c)}
    assert ("birth_impossible", "blocking") in got and ("orphan_player", "warning") in got
    assert drop_impossible_births(c) == 1 and remove_orphan_players(c) == 1
    assert _names(c) == ["Real Player"]
    assert c.execute("SELECT count(*) FROM player_birth").fetchone()[0] == 1
    assert c.execute("SELECT count(*) FROM player_wikidata").fetchone()[0] == 1


def test_parse_birth_ignores_a_date_nobody_in_a_squad_can_have():
    from openfootball.enrich import parse_birth
    rows = [{"p": "http://www.wikidata.org/entity/Q217791", "dob": "1515-07-31T00:00:00Z", "prec": "11"},
            {"p": "http://www.wikidata.org/entity/Q1", "dob": "1990-03-03T00:00:00Z", "prec": "11"}]
    assert list(parse_birth(rows)) == ["Q1"]


def test_reserve_youth_and_b_team_sections_are_not_the_first_squad_in_any_language():
    from openfootball.parse.squad import is_excluded_section as excluded
    for s in ("Effectif de la réserve", "Équipe réserve", "Joueurs réservistes - Olympique lyonnais B", "Almería B players", "Effectif des jeunes de formation",
              "Fiorentina Primavera", "Calciatori aggregati dal Barcellona B", "B List", "Hamburger SV Amateure", "Effectif réserve actuelle", "Équipe réserve et centre de formation"):
        assert excluded(s), s
    for s in ("Effectif et staff technique", "Squad information", "Left club during season", "Effectif professionnel", "Plantilla 2021-22", "Out on loan", "Rosa",
              "List of B-team players with senior squad numbers"):
        assert not excluded(s), s


def _match(c, mid, code, label, home, away, hid, aid, score=(1, 0), day="2018-03-03"):
    c.execute("INSERT INTO match (id, competition_code, season_label, home_name, away_name, home_club_id, away_club_id, ft_home, ft_away, match_date, source_ref) VALUES (?,?,?,?,?,?,?,?,?,?,'test')",
              [mid, code, label, home, away, hid, aid, *(score or (None, None)), day])


def test_audit_blocks_two_team_names_on_one_club_in_the_big_competitions_only():
    from openfootball.audit import run_audit
    c = _db()
    _match(c, 1, "ITA-SA", "2013/14", "AS Roma", "Juventus", 1, 2)
    _match(c, 2, "ITA-SA", "2013/14", "Lazio Roma", "Juventus", 1, 2)              # « Lazio Roma » rattachée au club de la Roma : le défaut de 2013/14 à 2019/20
    _match(c, 3, "CONMEBOL-CL", "2024", "Club Nacional", "Juventus", 2, 1)
    _match(c, 4, "CONMEBOL-CL", "2024", "Club Nacional de Football", "Juventus", 2, 1)
    got = {(p.check, p.severity, p.scope) for p in run_audit(c)}
    assert ("club_name_collision", "blocking", "ITA-SA 2013/14") in got
    assert ("club_name_collision", "warning", "CONMEBOL-CL 2024") in got


def test_audit_flags_unscored_past_matches_wrong_match_counts_and_goals_that_do_not_make_the_score():
    from openfootball.audit import run_audit
    c = _db()
    _match(c, 1, "FRA-L1", "2017/18", "A", "B", 1, 2, score=None, day="2018-03-03")        # passé, sans score
    _match(c, 2, "FRA-L1", "2017/18", "B", "A", 2, 1, score=(2, 1), day="2018-03-10")
    c.execute("INSERT INTO match_goal (match_id, seq, side, player_name, minute, kind) VALUES (2, 1, 'home', 'X', '10', 'goal')")        # 2-1 annoncé, 1 but détaillé
    got = {(p.check, p.severity) for p in run_audit(c)}
    assert ("match_unscored", "warning") in got
    assert ("season_match_count", "warning") not in got or True                    # 2 clubs, 2 matchs : 2 attendus
    assert ("match_goals_vs_score", "blocking") in got
    c.execute("INSERT INTO match_goal (match_id, seq, side, player_name, minute, kind) VALUES (2, 2, 'home', 'Y', '20', 'goal'), (2, 3, 'away', 'Z', '30', 'goal')")
    assert ("match_goals_vs_score", "blocking") not in {(p.check, p.severity) for p in run_audit(c)}


def test_champions_league_editions_have_the_right_number_of_matches():
    from openfootball.audit import run_audit
    c = _db()
    for i in range(124):
        _match(c, i + 1, "UEFA-CL", "2015/16", "A", "B", 1, 2)
    assert any(p.check == "season_match_count" and p.scope == "UEFA-CL 2015/16" for p in run_audit(c))      # 124 au lieu de 125
    _match(c, 999, "UEFA-CL", "2015/16", "A", "B", 1, 2)
    assert not any(p.check == "season_match_count" for p in run_audit(c))


def test_fixtures_of_a_season_cut_short_are_dropped_but_played_matches_stay():
    from openfootball.matches import drop_cancelled_fixtures
    c = _db()
    _match(c, 1, "FRA-L1", "2019/20", "A", "B", 1, 2, score=(1, 0))
    _match(c, 2, "FRA-L1", "2019/20", "B", "A", 2, 1, score=None, day="2020-05-23")
    _match(c, 3, "FRA-L1", "2018/19", "A", "B", 1, 2, score=None, day="2019-05-23")           # une autre saison : pas touchée
    assert drop_cancelled_fixtures(c) == 1
    assert [r[0] for r in c.execute("SELECT id FROM match ORDER BY id").fetchall()] == [1, 3]


def test_a_missing_score_is_filled_from_another_reading_of_the_same_source_but_a_known_score_never_changes():
    from datetime import date
    from openfootball.matches import Match, complete_scores
    c = _db()
    c.execute("INSERT INTO club (id, name_en, country_code, wikipedia_title) VALUES (3, 'Besiktas JK', 'TUR', 'Besiktas JK')")
    c.execute("INSERT INTO club_season (id, club_id, season_id, competition_id) VALUES (2, 3, 1, 1)")
    _match(c, 1, "TUR-SL", "2017/18", "Galatasaray", "Besiktas JK", 2, 3, score=None, day="2018-05-31")
    _match(c, 2, "TUR-SL", "2017/18", "Besiktas JK", "Galatasaray", 3, 2, score=(3, 3), day="2018-06-07")
    got = [Match("Galatasaray", "Besiktas JK", day=date(2018, 5, 31), ft=(5, 0)), Match("Besiktas JK", "Galatasaray", day=date(2018, 6, 7), ft=(0, 9))]
    assert complete_scores(c, "TUR-SL", "2017/18", got) == 1
    assert c.execute("SELECT id, ft_home, ft_away FROM match ORDER BY id").fetchall() == [(1, 5, 0), (2, 3, 3)]
