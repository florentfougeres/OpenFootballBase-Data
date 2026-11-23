"""Classement des buteurs : lecture du tableau de la page de saison, rang recalculé, import."""
import duckdb

from openfootball.db import migrate
from openfootball.topscorers import import_top_scorers, parse_top_scorers, rank_by_goals

EN = """
==Season statistics==
===Top goalscorers===
{| class="wikitable" style="text-align:center"
|-
! Rank
! Player
! Club
! Goals<ref name="g" />
|-
|1
|align="left"|{{flagicon|URU}} [[Edinson Cavani]]
|align="left"|[[Paris Saint-Germain F.C.|Paris Saint-Germain]]
|28
|-
|2
|align="left"|{{flagicon|FRA}} [[Florian Thauvin]]
|align="left"|Marseille
|22
|-
|rowspan="2"|3
|align="left"|{{flagicon|NED}} [[Memphis Depay]]
|align="left"|Lyon
|rowspan="2"|19
|-
|align="left"|{{flagicon|BRA}} [[Neymar]]
|align="left"|Paris Saint-Germain
|}
"""

ES = """
{| class="wikitable"
|-
! Pos.
! Jugador
! {{abreviación|G.|Goles}}
! Part.
! Club
|-
! 1
| {{bandera|ARG}} '''[[Lionel Messi]]
| '''34
| '''36
| [[Fútbol Club Barcelona|F. C. Barcelona]]
|-
| 2
| {{bandera|POR}} [[Cristiano Ronaldo]]
| '''26
| 27
| [[Real Madrid Club de Fútbol|Real Madrid]]
|-
| 3
| {{bandera|URU}} [[Luis Suárez]]
| 25
| 30
| [[Fútbol Club Barcelona|F. C. Barcelona]]
|}
"""

DE_SORTKEY = """
{| class="wikitable"
! Rank !! Player !! Club !! Goals
|-
| 1 || {{flagicon|POL}} {{SortKeyName|Robert|Lewandowski}} || [[Borussia Dortmund]] || 20
|-
| 2 || {{flagicon|CRO}} {{SortKeyName|Mario|Mandžukić}} || [[FC Bayern Munich|Bayern Munich]] || 18
|-
| 3 || {{flagicon|SUI}} {{SortKeyName|Josip|Drmić}} || [[1. FC Nürnberg]] || 17
|}
"""


def test_english_table_with_tied_rows_is_read_and_ranked_by_goals():
    rows = rank_by_goals(parse_top_scorers(EN))
    assert [(r["rank"], r["player"], r["goals"]) for r in rows] == [(1, "Edinson Cavani", 28), (2, "Florian Thauvin", 22), (3, "Memphis Depay", 19), (3, "Neymar", 19)]
    assert rows[0]["player_link"] == "Edinson Cavani" and rows[0]["club"] == "Paris Saint-Germain"


def test_spanish_table_with_an_abbreviated_goals_header_and_bold_cells():
    rows = parse_top_scorers(ES)
    assert [(r["player"], r["goals"]) for r in rows] == [("Lionel Messi", 34), ("Cristiano Ronaldo", 26), ("Luis Suárez", 25)]


def test_player_name_written_only_in_a_sort_key_template_is_still_read():
    assert [r["player"] for r in parse_top_scorers(DE_SORTKEY)] == ["Robert Lewandowski", "Mario Mandžukić", "Josip Drmić"]


def test_a_page_without_a_scorers_table_gives_nothing():
    assert parse_top_scorers("== Results ==\n{| class=\"wikitable\"\n! Team !! Pts\n|-\n| A || 3\n|}") == []


class _Page:
    def __init__(self, text):
        self.exists, self.wikitext = bool(text), text


class _Wp:
    def __init__(self, pages):
        self.pages = pages

    def get_pages(self, titles):
        return [_Page(self.pages.get(t)) for t in titles]

    def _call(self, params):                                   # pageprops.wikibase_item des liens que la base ne connaît pas
        qids = {"Neymar": "Q142794"}
        titles = params["titles"].split("|")
        return {"query": {"pages": [{"title": x, "pageprops": ({"wikibase_item": qids[x]} if x in qids else {})} for x in titles]}}


def test_import_writes_rank_qid_and_club_and_is_idempotent():
    c = duckdb.connect(":memory:")
    migrate(c)
    c.execute("INSERT INTO country VALUES ('FRA', 'France', 'France')")
    c.execute("INSERT INTO competition (id, code, name_en, name_fr, country_code, level) VALUES (1, 'FRA-L1', 'Ligue 1', 'Ligue 1', 'FRA', 1)")
    c.execute("INSERT INTO season (id, start_year, label) VALUES (1, 2017, '2017/18')")
    c.execute("INSERT INTO club (id, name_en, country_code, wikipedia_title, wikidata_qid) VALUES (1, 'Paris Saint-Germain', 'FRA', 'Paris Saint-Germain F.C.', 'Q483020')")
    c.execute("INSERT INTO club_season (id, club_id, season_id, competition_id) VALUES (1, 1, 1, 1)")
    c.execute("INSERT INTO player (id, name, wikidata_qid) VALUES (1, 'Edinson Cavani', 'Q1')")
    c.execute("INSERT INTO player_wikidata VALUES (1, 'Q1')")
    c.execute("INSERT INTO player_link VALUES ('fr', 'Edinson Cavani', 1)")
    wps = {"fr": _Wp({"Championnat de France de football 2017-2018": EN.replace("Goals<ref name=\"g\" />", "Buts").replace("Player", "Joueur")})}
    for _ in range(2):
        assert import_top_scorers(c, wps, leagues={"FRA-L1": [("fr", "Championnat de France de football {y}-{Y}")]}, years=[2017], log=lambda m: None) == 4
    rows = c.execute("SELECT rank, player_name, player_qid, club_id, goals FROM top_scorer ORDER BY rank, player_name").fetchall()
    assert rows[0] == (1, "Edinson Cavani", "Q1", 1, 28)                        # joueur relié par son lien, club par son nom
    assert [r[0] for r in rows] == [1, 2, 3, 3] and len(rows) == 4              # deux passages : pas de doublon
    assert c.execute("SELECT player_qid FROM top_scorer WHERE player_name = 'Neymar'").fetchone()[0] == "Q142794"      # QID par la page Wikipedia du joueur


GOALKEEPERS = """
{| class="wikitable"
! Pos. !! Jugador !! Goles encajados !! Club
|-
| 1 || [[Portero Uno]] || 20 || [[A]]
|-
| 2 || [[Portero Dos]] || 25 || [[B]]
|-
| 3 || [[Portero Tres]] || 30 || [[C]]
|}
""" + ES


def test_the_goalkeepers_goals_conceded_table_is_not_the_scorers_table():
    assert [r["player"] for r in parse_top_scorers(GOALKEEPERS)] == ["Lionel Messi", "Cristiano Ronaldo", "Luis Suárez"]


ASCENDING = """
{| class="wikitable"
! Rank !! Player !! Club !! Goals
|-
| 1 || [[A Un]] || [[X]] || 5
|-
| 2 || [[B Deux]] || [[Y]] || 9
|-
| 3 || [[C Trois]] || [[Z]] || 12
|}
"""


def test_a_table_that_does_not_go_from_most_to_fewest_goals_is_not_a_scorers_ranking():
    assert parse_top_scorers(ASCENDING) == []
