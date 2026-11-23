"""Entraîneurs : lecture des mandats Wikidata (début, fin, doublons) et écriture de `club_coach`."""
import duckdb

from openfootball.coaches import import_coach_careers, import_coaches, parse_coaches, parse_flags, parse_profiles
from openfootball.db import migrate

CLUB = "http://www.wikidata.org/entity/Q1893"


def _row(coach="Q923088", label="Stefano Pioli", start="2011-10-04T00:00:00Z", end="2014-01-07T00:00:00Z"):
    r = {"club": CLUB, "coach": f"http://www.wikidata.org/entity/{coach}", "coachLabel": label}
    if start:
        r["start"] = start
    if end:
        r["end"] = end
    return r


def test_mandat_lu_avec_dates():
    got = parse_coaches([_row()])
    ((key, (name, end)),) = got.items()
    assert key[:2] == ("Q1893", "Q923088") and str(key[2]) == "2011-10-04" and name == "Stefano Pioli" and str(end) == "2014-01-07"


def test_sans_debut_ou_sans_libelle_ignore():
    assert parse_coaches([_row(start=None), _row(label="Q923088")]) == {}


def test_fin_avant_debut_ignoree_et_doublon_fusionne():
    got = parse_coaches([_row(end="2010-01-01T00:00:00Z")])
    assert list(got.values())[0][1] is None                                       # fin impossible : mandat gardé, fin vide
    dup = parse_coaches([_row(end="2012-01-01T00:00:00Z"), _row(end="2013-01-01T00:00:00Z")])
    assert len(dup) == 1 and str(list(dup.values())[0][1]) == "2013-01-01"
    ouvert = parse_coaches([_row(end=None), _row(end="2013-01-01T00:00:00Z")])
    assert list(ouvert.values())[0][1] is None                                    # une déclaration sans fin : le mandat reste ouvert


def test_import_remplace_la_table():
    con = duckdb.connect(":memory:")
    migrate(con)
    con.execute("INSERT INTO country VALUES ('ITA', 'Italie', 'Italy')")
    con.execute("INSERT INTO competition (id, code, name_en, name_fr, country_code, level) VALUES (1, 'ITA-SA', 'Serie A', 'Serie A', 'ITA', 1)")
    con.execute("INSERT INTO season (id, start_year, label, status) VALUES (1, 2011, '2011/12', 'backfill')")
    con.execute("INSERT INTO club (id, wikidata_qid, wikipedia_title, name_en) VALUES (1, 'Q1893', 'Bologna F.C. 1909', 'Bologna'), (2, 'Q2', 'Sans effectif', 'X')")
    con.execute("INSERT INTO club_season (id, club_id, season_id, competition_id) VALUES (1, 1, 1, 1)")
    asked = []

    class Wd:
        def query(self, sparql):
            asked.append(sparql)
            return [_row(), _row(coach="Q294351", label="Siniša Mihajlović", start="2019-01-28T00:00:00Z", end=None)]
    assert import_coaches(con, Wd(), log=lambda _: None) == 2
    assert "wd:Q1893" in asked[0] and "wd:Q2 " not in asked[0]                    # seuls les clubs à effectifs sont interrogés
    assert con.execute("SELECT coach_name, end_date IS NULL FROM club_coach ORDER BY start_date").fetchall() == [("Stefano Pioli", False), ("Siniša Mihajlović", True)]
    assert import_coaches(con, Wd(), log=lambda _: None) == 2                      # idempotent


def test_drapeau_pays_pour_le_sport_avant_la_citoyennete():
    rows = [{"coach": "http://www.wikidata.org/entity/Q1", "sportLabel": "England", "citLabel": "United Kingdom"},
            {"coach": "http://www.wikidata.org/entity/Q2", "citLabel": "France"},
            {"coach": "http://www.wikidata.org/entity/Q3", "citLabel": "Q42"}]                          # libellé absent : le service renvoie le QID
    got = parse_flags(rows)
    assert got["Q1"] == "gb-eng" and got["Q2"] == "fr" and "Q3" not in got


def test_import_ecrit_le_drapeau():
    con = duckdb.connect(":memory:")
    migrate(con)
    con.execute("INSERT INTO country VALUES ('ITA', 'Italie', 'Italy')")
    con.execute("INSERT INTO competition (id, code, name_en, name_fr, country_code, level) VALUES (1, 'ITA-SA', 'Serie A', 'Serie A', 'ITA', 1)")
    con.execute("INSERT INTO season (id, start_year, label, status) VALUES (1, 2011, '2011/12', 'backfill')")
    con.execute("INSERT INTO club (id, wikidata_qid, wikipedia_title, name_en) VALUES (1, 'Q1893', 'Bologna F.C. 1909', 'Bologna')")
    con.execute("INSERT INTO club_season (id, club_id, season_id, competition_id) VALUES (1, 1, 1, 1)")

    class Wd:
        def query(self, sparql):
            assert "P1532" in sparql and "P27" in sparql
            return [{**_row(), "citLabel": "Italy"}]
    import_coaches(con, Wd(), log=lambda _: None)
    assert con.execute("SELECT flag FROM club_coach").fetchall() == [("it",)]


def test_fiche_naissance_jour_ou_annee_lieu_et_pages():
    rows = [{"c": "http://www.wikidata.org/entity/Q1", "birth": "1970-05-08T00:00:00Z", "prec": "11", "placeLabel": "Gijón", "en": "Luis Enrique", "fr": "Luis Enrique Martínez"},
            {"c": "http://www.wikidata.org/entity/Q2", "birth": "1955-01-01T00:00:00Z", "prec": "9", "placeLabel": "Q42"},          # année seule ; lieu sans libellé
            {"c": "http://www.wikidata.org/entity/Q3"}]
    got = parse_profiles(rows)
    assert str(got["Q1"][0]) == "1970-05-08" and got["Q1"][1] is None and got["Q1"][2] == "Gijón" and got["Q1"][3:] == ("Luis Enrique", "Luis Enrique Martínez")
    assert got["Q2"] == (None, 1955, None, None, None) and got["Q3"] == (None, None, None, None, None)


def test_carriere_d_entraineur_lue_dans_l_infobox():
    from openfootball.parse.infobox import parse_managerial
    wt = ("{{Infobox football biography | name = Hansi Flick | years1 = 1983–1985 | clubs1 = [[SV Sandhausen]] "
          "| manager_years1 = 2006–2014 | manager_clubs1 = [[Germany national football team|Germany]] (assistant) "
          "| manageryears2 = 2019–2021 | managerclubs2 = [[FC Bayern Munich]] | manageryears3 = 2024– | managerclubs3 = [[FC Barcelona]] }}")
    got = parse_managerial(wt)
    assert [(s.seq, s.start_year, s.end_year, s.team_name, s.team_link) for s in got] == [
        (1, 2006, 2014, "Germany", "Germany national football team"), (2, 2019, 2021, "FC Bayern Munich", "FC Bayern Munich"), (3, 2024, None, "FC Barcelona", "FC Barcelona")]


def test_import_carrieres_ecrit_la_table():
    from types import SimpleNamespace
    con = duckdb.connect(":memory:")
    migrate(con)
    con.execute("INSERT INTO coach_profile (coach_qid, wikipedia_en) VALUES ('Q577384', 'Hansi Flick')")

    class Wp:
        def get_pages(self, titles):
            return [SimpleNamespace(title="Hansi Flick", exists=True, wikitext="{{Infobox football biography | manageryears1 = 2019–2021 | managerclubs1 = [[FC Bayern Munich]] }}")]
    assert import_coach_careers(con, Wp(), log=lambda _: None) == 1
    assert con.execute("SELECT coach_qid, team_name FROM coach_career").fetchall() == [("Q577384", "FC Bayern Munich")]
