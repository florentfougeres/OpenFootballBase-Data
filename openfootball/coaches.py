"""Entraîneurs des clubs : les mandats de la propriété Wikidata « entraîneur » (P286), avec leurs dates de début (P580) et de fin (P582).

Un mandat sans date de début n'est pas gardé (on ne saurait pas le placer dans le temps) ; deux déclarations identiques (même club, même
entraîneur, même début) n'en font qu'un. Les libellés sont ceux de Wikidata, en anglais puis en français.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Callable

import duckdb

from openfootball.countries import flag_code

BATCH = 80


def _date(raw: str | None) -> date | None:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw or "")
    if not m:
        return None                                    # absent, année négative ou format inattendu
    try:
        return date(int(m.group(1)), max(int(m.group(2)), 1), max(int(m.group(3)), 1))
    except ValueError:
        return None


def parse_coaches(rows: list[dict]) -> dict[tuple[str, str, date], tuple[str, date | None]]:
    """Lignes SPARQL (?club ?coach ?coachLabel ?start ?end) -> {(club_qid, coach_qid, début): (nom, fin)}."""
    out: dict[tuple[str, str, date], tuple[str, date | None]] = {}
    for r in rows:
        start = _date(r.get("start"))
        label = r.get("coachLabel", "")
        if start is None or not label or re.fullmatch(r"Q\d+", label):          # sans libellé, le service renvoie le QID lui-même
            continue
        end = _date(r.get("end"))
        if end is not None and end < start:
            end = None                                  # fin antérieure au début : fin ignorée, le mandat reste daté
        key = (r["club"].rsplit("/", 1)[-1], r["coach"].rsplit("/", 1)[-1], start)
        if key in out:
            old = out[key][1]
            end = None if old is None or end is None else max(old, end)             # deux déclarations : on ne ferme le mandat que si les deux le font
        out[key] = (label, end)
    return out


def parse_flags(rows: list[dict]) -> dict[str, str]:
    """Lignes SPARQL (?coach ?sportLabel ?citLabel) -> {coach_qid: code de drapeau} : le pays pour le sport (P1532, « England ») d'abord, la citoyenneté (P27) à défaut."""
    sport: dict[str, str] = {}
    citizen: dict[str, str] = {}
    for r in rows:
        qid = r["coach"].rsplit("/", 1)[-1]
        for label, into in ((r.get("sportLabel"), sport), (r.get("citLabel"), citizen)):
            code = flag_code(label) if label and not re.fullmatch(r"Q\d+", label) else None
            if code and qid not in into:
                into[qid] = code
    return {**citizen, **sport}


def parse_profiles(rows: list[dict]) -> dict[str, tuple]:
    """Lignes SPARQL (?c ?birth ?prec ?placeLabel ?en ?fr) -> {coach_qid: (jour, année, lieu, titre en, titre fr)} ; une valeur déjà lue n'est pas remplacée."""
    out: dict[str, list] = {}
    for r in rows:
        qid = r["c"].rsplit("/", 1)[-1]
        cur = out.setdefault(qid, [None, None, None, None, None])
        d = _date(r.get("birth"))
        try:
            prec = int(float(r.get("prec") or 0))
        except ValueError:
            prec = 0
        if d is not None and cur[0] is None and cur[1] is None:
            if prec >= 11:
                cur[0] = d
            elif prec >= 9:
                cur[1] = d.year
        place = r.get("placeLabel")
        if place and not re.fullmatch(r"Q\d+", place) and cur[2] is None:
            cur[2] = place
        for i, k in ((3, "en"), (4, "fr")):
            if r.get(k) and cur[i] is None:
                cur[i] = r[k]
    return {q: tuple(v) for q, v in out.items()}


def import_coaches(con: duckdb.DuckDBPyConnection, wd, *, log: Callable[[str], None] = print) -> int:
    """Remplace `club_coach` : les mandats de tous les clubs ayant des effectifs et un QID."""
    clubs = {q: cid for cid, q in con.execute("""SELECT c.id, c.wikidata_qid FROM club c WHERE c.wikidata_qid IS NOT NULL
                                                  AND EXISTS (SELECT 1 FROM club_season cs WHERE cs.club_id = c.id) ORDER BY c.id""").fetchall()}
    qids = list(clubs)
    found: dict[tuple[str, str, date], tuple[str, date | None]] = {}
    flags: dict[str, str] = {}
    for i in range(0, len(qids), BATCH):
        chunk = qids[i:i + BATCH]
        sparql = ("SELECT ?club ?coach ?coachLabel ?start ?end ?sportLabel ?citLabel WHERE { VALUES ?club { " + " ".join(f"wd:{q}" for q in chunk) + " } "
                  "?club p:P286 ?st . ?st ps:P286 ?coach . OPTIONAL { ?st pq:P580 ?start } OPTIONAL { ?st pq:P582 ?end } "
                  "OPTIONAL { ?coach wdt:P1532 ?sport } OPTIONAL { ?coach wdt:P27 ?cit } "
                  'SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr". } }')
        rows = wd.query(sparql)
        found.update(parse_coaches(rows))
        flags.update({q: f for q, f in parse_flags(rows).items() if q not in flags})
    if not found:
        log("  entraîneurs : aucun mandat reçu, table inchangée")
        return 0
    coach_qids = sorted({coach for (_, coach, _) in found})
    profiles: dict[str, tuple] = {}
    for i in range(0, len(coach_qids), BATCH):
        chunk = coach_qids[i:i + BATCH]
        sparql = ("SELECT ?c ?birth ?prec ?placeLabel ?en ?fr WHERE { VALUES ?c { " + " ".join(f"wd:{q}" for q in chunk) + " } "
                  "OPTIONAL { ?c p:P569/psv:P569 ?bv . ?bv wikibase:timeValue ?birth ; wikibase:timePrecision ?prec } OPTIONAL { ?c wdt:P19 ?place } "
                  "OPTIONAL { ?ea schema:about ?c ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?en } "
                  "OPTIONAL { ?fa schema:about ?c ; schema:isPartOf <https://fr.wikipedia.org/> ; schema:name ?fr } "
                  'SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }')
        try:
            profiles.update(parse_profiles(wd.query(sparql)))
        except Exception as exc:                        # la fiche est un plus : un échec Wikidata ne doit pas faire perdre les mandats
            log(f"  fiches d'entraîneurs : lot ignoré ({exc})")
    con.execute("BEGIN")
    try:
        con.execute("DELETE FROM club_coach")
        con.executemany("INSERT INTO club_coach (club_id, coach_qid, coach_name, start_date, end_date, flag) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                        [(clubs[club], coach, name, start, end, flags.get(coach)) for (club, coach, start), (name, end) in found.items() if club in clubs])
        if profiles:
            con.execute("DELETE FROM coach_profile")
            con.executemany("INSERT INTO coach_profile VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                            [(q, *v) for q, v in profiles.items() if q in {c for (_, c, _) in found}])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    n = con.execute("SELECT count(*) FROM club_coach").fetchone()[0]
    log(f"  entraîneurs : {n} mandats, {con.execute('SELECT count(DISTINCT club_id) FROM club_coach').fetchone()[0]} clubs sur {len(clubs)}")
    return n
