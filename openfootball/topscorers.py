"""Classement des buteurs de chaque championnat et de chaque saison, lu dans le tableau « Top scorers » de la page Wikipedia de la saison.

Le tableau varie d'une page et d'une langue à l'autre (rang | joueur | club | buts, avec des cellules fusionnées pour les ex æquo) : les colonnes sont repérées par leur
titre, dans cinq langues. Le rang n'est pas celui de la page : il est recalculé sur les buts (compétition standard : 1, 2, 2, 4), ce qui donne le même résultat sans dépendre
des cellules fusionnées. Un joueur sans lien garde son nom ; un club que la saison ne connaît pas garde son nom sans identifiant.
"""
from __future__ import annotations

import re
from typing import Callable

import duckdb

from openfootball.matches import _club_index, resolve_club, season_label
from openfootball.parse.squad import _name_and_link, clean
from openfootball.parse.stats import _TABLE, _grid, _headers, _int, _link, _text
from openfootball.sources.wikidata import club_qids
from openfootball.wikiresults import FALLBACK, LEAGUES

_PLAYER = ("player", "scorer", "joueur", "jugador", "nombre", "giocatore", "calciatore", "spieler", "name")
_GOALS = ("goals", "buts", "goles", "gol", "g", "reti", "tore", "goal")
_CLUB = ("club", "team", "équipe", "equipo", "squadra", "verein", "mannschaft")
_ABBR = re.compile(r"\{\{\s*(?:abreviaci[oó]n|abbr)\s*\|([^|}]*)\|([^|}]*)", re.I)
_SORTKEY = re.compile(r"\{\{\s*SortKeyName\s*\|([^|}]*)\|([^|}]*)", re.I)
MIN_ROWS = 3             # un tableau de moins de trois lignes n'est pas le classement des buteurs (une légende, un récapitulatif)


def _player(raw: str) -> tuple[str | None, str | None]:
    """(nom, lien) de la cellule du joueur : le lien Wikipedia, ou à défaut le nom écrit dans `{{SortKeyName|Prénom|Nom}}`."""
    name, link = _name_and_link(raw, full=True)
    if name:
        return name, link
    m = _SORTKEY.search(raw)
    return (f"{m.group(1).strip()} {m.group(2).strip()}".strip() or None, None) if m else (None, None)


_AGAINST = re.compile(r"against|conceded|encaiss|encajad|recibid|subi|concede|gegentore|incassat", re.I)      # le tableau des gardiens (buts encaissés) n'est pas celui des buteurs


def _is_goals(label: str) -> bool:
    n = label.lower().strip().rstrip(".")
    return not _AGAINST.search(n) and (n in _GOALS or n.startswith(("goals", "buts", "goles")))


def parse_top_scorers(wikitext: str) -> list[dict]:
    """Lignes {player, player_link, club, club_link, goals} du premier tableau « joueur | buts » de la page, trié du plus au moins de buts ; [] s'il n'y en a pas."""
    for tbl in _TABLE.findall(clean(wikitext)):
        rows = _grid(tbl)
        for h in range(min(4, len(rows))):                       # la ligne de titres : la première, ou la suivante quand une ligne de style la précède
            names = [(c.text or (m.group(2) if (m := _ABBR.search(c.raw)) else "")).lower().strip() for c in rows[h]]
            pi = next((i for i, n in enumerate(names) if n in _PLAYER), None)
            gi = next((i for i, n in enumerate(names) if _is_goals(n)), None)
            if pi is not None and gi is not None:
                break
        else:
            continue
        start = h + 1
        ci = next((i for i, n in enumerate(names) if n in _CLUB), None)
        out = []
        for cells in rows[start:]:
            if len(cells) <= max(pi, gi):
                continue
            name, link = _player(cells[pi].raw)
            goals = _int(cells[gi].raw)
            if not name or goals is None or goals <= 0:
                continue
            club = cells[ci] if ci is not None and ci < len(cells) else None
            out.append({"player": name, "player_link": link, "goals": goals,
                        "club": _text(club.raw.split("<br")[0]) if club else None, "club_link": _link(club.raw) if club else None})
        if len(out) >= MIN_ROWS and all(a["goals"] >= b["goals"] for a, b in zip(out, out[1:])):      # un classement des buteurs va du plus au moins
            return out
    return []


def rank_by_goals(rows: list[dict]) -> list[dict]:
    """Ajoute `rank` : classement standard sur les buts (1, 2, 2, 4), dans l'ordre de la page à buts égaux."""
    rows = sorted(rows, key=lambda r: -r["goals"])
    for i, r in enumerate(rows):
        r["rank"] = 1 if i == 0 else (rows[i - 1]["rank"] if r["goals"] == rows[i - 1]["goals"] else i + 1)
    return rows


def import_top_scorers(con: duckdb.DuckDBPyConnection, wps: dict, *, leagues: dict[str, list[tuple[str, str]]] | None = None,
                       years: list[int], log: Callable[[str], None] = print) -> int:
    """Lit le classement des buteurs de chaque (championnat, saison de `years`) et remplace les lignes de ce championnat et de cette saison. Une page absente ou sans tableau est
    signalée, jamais fatale. `wps` : {langue: WikipediaClient}. Rend le nombre de lignes écrites."""
    total = 0
    links_by_lang = {lang: dict(con.execute("SELECT link_title, player_id FROM player_link WHERE link_lang = ?", [lang]).fetchall()) for lang in wps}
    qid_of = dict(con.execute("SELECT player_id, qid FROM player_wikidata").fetchall())
    for code, pages in (leagues or LEAGUES).items():
        for year in years:
            label = season_label(year)
            got: list[dict] = []
            src = lang0 = None
            for lang, p in pages + FALLBACK.get(code, []):
                if lang not in wps:
                    continue
                title = p.format(y=year, yy=str(year + 1)[2:], Y=year + 1)
                (page,) = wps[lang].get_pages([title])
                if page.exists and page.wikitext:
                    got = parse_top_scorers(page.wikitext)
                    if got:
                        src, lang0 = f"wikipedia:{lang}:{title}", lang
                        break
            if not got:
                log(f"  {code} {label} : aucun classement des buteurs lu")
                continue
            links = sorted({r["player_link"] for r in got if r["player_link"] and r["player_link"] not in links_by_lang.get(lang0, {})})
            page_qid = club_qids(wps[lang0], links) if links else {}                      # un joueur que la base ne connaît pas par son lien : son QID par la page Wikipedia
            index = _club_index(con, code, label)
            by_title = dict(con.execute("SELECT wikipedia_title, id FROM club WHERE wikipedia_title IS NOT NULL").fetchall()) if lang0 == "en" else {}
            con.execute("BEGIN")
            con.execute("DELETE FROM top_scorer WHERE competition_code = ? AND season_label = ?", [code, label])
            for r in rank_by_goals(got):
                pid = links_by_lang.get(lang0, {}).get(r["player_link"]) if r["player_link"] else None
                club_id = (by_title.get(r["club_link"]) if r["club_link"] else None) or (resolve_club(index, r["club"]) if r["club"] else None)
                qid = qid_of.get(pid) if pid else page_qid.get(r["player_link"])
                con.execute("INSERT INTO top_scorer VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            [code, label, r["rank"], r["player"], r["player_link"], qid, r["club"], club_id, r["goals"], src])
            con.execute("COMMIT")
            total += len(got)
    log(f"  classements des buteurs : {total} lignes")
    return total
