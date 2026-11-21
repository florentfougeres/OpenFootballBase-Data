"""Enrichissement Wikidata/Wikipedia : liens par langue, noms français, dates de naissance, logos.

Tout est idempotent (on ne retraite pas ce qui est déjà en base) et tolère l'absence de donnée : un club
sans logo, un joueur sans date de naissance ou sans page française restent simplement vides.
"""
from __future__ import annotations

import re
import zlib
from urllib.parse import unquote
from datetime import date
from typing import Callable

import duckdb

SITES = {"en": "enwiki", "fr": "frwiki", "it": "itwiki", "de": "dewiki", "es": "eswiki", "nl": "nlwiki", "tr": "trwiki",
         "pt": "ptwiki"}
BATCH = 50
BIRTH_BATCH = 300


def _chunks(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def enrich_wiki_links(con: duckdb.DuckDBPyConnection, wd, qids: list[str], langs: tuple[str, ...],
                      *, labels: tuple[str, ...] = (), log: Callable[[str], None] = print) -> int:
    """Pages Wikipedia (sitelinks) et libellés des entités `qids`, pour les QID pas encore traités."""
    done = {r[0] for r in con.execute("SELECT DISTINCT qid FROM entity_wiki").fetchall()}
    todo = [q for q in dict.fromkeys(qids) if q not in done]
    written = 0
    for chunk in _chunks(todo, BATCH):
        ents = wd.entities(chunk, props="sitelinks|labels" if labels else "sitelinks",
                           languages="|".join(labels) or None, sitefilter="|".join(SITES[l] for l in langs))
        con.execute("BEGIN")
        for qid in chunk:
            e = ents.get(qid, {})
            for lang in langs:
                title = (e.get("sitelinks", {}).get(SITES[lang]) or {}).get("title")
                if title:
                    con.execute("INSERT INTO entity_wiki VALUES (?, ?, ?) ON CONFLICT DO NOTHING", [qid, lang, title])
                    written += 1
            for lang in labels:
                label = (e.get("labels", {}).get(lang) or {}).get("value")
                if label:
                    con.execute("INSERT INTO entity_label VALUES (?, ?, ?) ON CONFLICT DO NOTHING", [qid, lang, label])
        con.execute("COMMIT")
    log(f"  liens wiki : {len(todo)} entités lues, {written} liens écrits")
    return written


NON_LATIN = r"[^\p{Latin}\p{Common}\p{Inherited}]"       # RE2 : une lettre hors alphabet latin (cyrillique, arabe, CJK…)


def enrich_context_labels(con: duckdb.DuckDBPyConnection, wd, *, log: Callable[[str], None] = print) -> int:
    """Libellé ANGLAIS (Wikidata) du stade, du championnat et de la ville des clubs dont le nom publié est en
    alphabet non latin : le site affiche l'anglais plutôt que du russe, de l'arabe ou du chinois."""
    qids: list[str] = []
    for text, qid in (("stadium", "stadium_qid"), ("league", "league_qid"), ("city", "city_qid")):
        qids += [r[0] for r in con.execute(
            f"SELECT DISTINCT {qid} FROM club WHERE {qid} IS NOT NULL AND regexp_matches({text}, '{NON_LATIN}')").fetchall()]
    done = {r[0] for r in con.execute("SELECT qid FROM entity_label WHERE lang = 'en'").fetchall()}
    todo = [q for q in dict.fromkeys(qids) if q not in done]
    written = 0
    for chunk in _chunks(todo, BATCH):
        ents = wd.entities(chunk, props="labels", languages="en")
        con.execute("BEGIN")
        for qid in chunk:
            label = (ents.get(qid, {}).get("labels", {}).get("en") or {}).get("value")
            if label:
                con.execute("INSERT INTO entity_label VALUES (?, 'en', ?) ON CONFLICT DO NOTHING", [qid, label])
                written += 1
        con.execute("COMMIT")
    log(f"  libellés anglais (stades, championnats, villes) : {len(todo)} entités lues, {written} libellés écrits")
    return written


def enrich_career_clubs(con: duckdb.DuckDBPyConnection, wp, *, log: Callable[[str], None] = print) -> int:
    """Résout en QID les titres de clubs cités dans les carrières (redirections comprises) qui ne sont pas déjà
    le titre d'un club connu : la ligne de carrière retrouve alors la fiche et le logo du club."""
    from openfootball.sources.wikidata import club_qids
    todo = [r[0] for r in con.execute("""SELECT DISTINCT club_link FROM player_career
        WHERE club_link IS NOT NULL
          AND club_link NOT IN (SELECT wikipedia_title FROM club WHERE wikipedia_title IS NOT NULL)
          AND club_link NOT IN (SELECT link_title FROM club_link_qid) ORDER BY club_link""").fetchall()]
    found = 0
    for chunk in _chunks(todo, BATCH):
        qids = club_qids(wp, chunk)
        con.execute("BEGIN")
        for title in chunk:
            con.execute("INSERT INTO club_link_qid VALUES (?, ?) ON CONFLICT DO NOTHING", [title, qids.get(title)])
            found += 1 if qids.get(title) else 0
        con.execute("COMMIT")
    log(f"  clubs des carrières : {len(todo)} titres résolus, {found} avec un QID")
    return found


def add_career_clubs(con: duckdb.DuckDBPyConnection, wd, *, log: Callable[[str], None] = print) -> int:
    """Ajoute à `club` les clubs cités dans les carrières dont le QID n'est pas dans l'import mondial (Boca Juniors, équipes
    réserves…), pour que la ligne de carrière mène à une fiche. Nom, pays, logo viennent de Wikidata ; aucun effectif."""
    qids = [r[0] for r in con.execute("""SELECT DISTINCT m.qid FROM player_career c JOIN club_link_qid m ON m.link_title = c.club_link
        WHERE m.qid IS NOT NULL AND m.qid NOT IN (SELECT wikidata_qid FROM club WHERE wikidata_qid IS NOT NULL) ORDER BY m.qid""").fetchall()]
    iso_of = dict(con.execute("SELECT DISTINCT country_qid, country_iso FROM club WHERE country_qid IS NOT NULL AND country_iso IS NOT NULL").fetchall())
    added = 0
    for chunk in _chunks(qids, BATCH):
        ents = wd.entities(chunk, props="labels|claims|sitelinks", languages="en|fr", sitefilter="enwiki")
        con.execute("BEGIN")
        for qid in chunk:
            e = ents.get(qid) or {}
            en = (e.get("labels", {}).get("en") or {}).get("value")
            fr = (e.get("labels", {}).get("fr") or {}).get("value")
            if not (en or fr):
                continue
            claims = e.get("claims", {})

            def first(prop: str):
                for c in claims.get(prop, []):
                    v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                    if v:
                        return v
                return None
            country = first("P17")
            cq = country.get("id") if isinstance(country, dict) else None
            logo = first("P154")
            title = (e.get("sitelinks", {}).get("enwiki") or {}).get("title")
            if title and con.execute("SELECT 1 FROM club WHERE wikipedia_title = ?", [title]).fetchone():
                title = None                                              # UNIQUE : le titre est déjà pris
            new_id = con.execute("SELECT coalesce(max(id), 0) + 1 FROM club").fetchone()[0]
            con.execute("""INSERT INTO club (id, wikidata_qid, wikipedia_title, name_local, name_en, country_qid, country_iso, logo_commons_url)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        [new_id, qid, title, fr or en, en or fr, cq, iso_of.get(cq),
                         f"https://commons.wikimedia.org/wiki/Special:FilePath/{str(logo).replace(' ', '_')}" if logo else None])
            if fr:
                con.execute("INSERT INTO entity_label VALUES (?, 'fr', ?) ON CONFLICT DO NOTHING", [qid, fr])
            if en:
                con.execute("INSERT INTO entity_label VALUES (?, 'en', ?) ON CONFLICT DO NOTHING", [qid, en])
            added += 1
        con.execute("COMMIT")
    log(f"  clubs des carrières absents de l'import mondial : {len(qids)} lus, {added} ajoutés")
    return added


def _file_title(name: str) -> str:
    return "File:" + name.replace("_", " ")


def parse_imageinfo(q: dict, wanted: list[str]) -> dict[str, dict]:
    """Réponse `prop=imageinfo` -> {nom de fichier demandé: {url, page, license, author, free}}. Fichier absent : pas d'entrée."""
    to_title: dict[str, str] = {}
    for key in ("normalized", "redirects"):
        for m in q.get(key, []):
            to_title[m["from"]] = m["to"]
    by_title = {pg["title"]: pg for pg in q.get("pages", []) if pg.get("imageinfo")}
    out: dict[str, dict] = {}
    for name in wanted:
        t = _file_title(name)
        for _ in range(3):                           # normalisation puis redirection éventuelle
            t = to_title.get(t, t)
        pg = by_title.get(t)
        if not pg:
            continue
        ii = pg["imageinfo"][0]
        meta = ii.get("extmetadata", {})
        license_ = (meta.get("LicenseShortName") or {}).get("value")
        author = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value") or "")).strip() or None
        nonfree = str((meta.get("NonFree") or {}).get("value", "")).lower() == "true" or bool(re.search(r"fair use|non-free", license_ or "", re.I))
        out[name] = {"url": ii.get("thumburl") or ii.get("url"), "page": ii.get("descriptionurl"), "license": license_,
                     "author": author, "free": bool(license_) and not nonfree}
    return out


def enrich_player_photos(con: duckdb.DuckDBPyConnection, wp, *, limit: int | None = None, only: set[str] | None = None, log: Callable[[str], None] = print) -> int:
    """Adresse (miniature 300 px), page du fichier, licence et auteur des photos d'infobox, pour les profils qui n'ont pas encore
    ces informations. Un fichier introuvable est marqué `image_free = false` (jamais publié) pour ne pas être redemandé."""
    todo = [r[0] for r in con.execute("""SELECT DISTINCT image_file FROM player_profile
        WHERE image_file IS NOT NULL AND image_free IS NULL ORDER BY image_file""").fetchall()]
    if only is not None:                                 # seulement ces fichiers (une base restaurée n'a plus `image_free` : tout le reste serait relu)
        todo = [f for f in todo if f in only]
    if limit:
        todo = todo[:limit]
    done = 0
    for chunk in _chunks(todo, BATCH):
        data = wp._call({"action": "query", "titles": "|".join(_file_title(n) for n in chunk), "prop": "imageinfo",
                         "iiurlwidth": 300, "iiextmetadatafilter": "LicenseShortName|Artist|NonFree", "iiprop": "url|extmetadata",
                         "redirects": 1})
        info = parse_imageinfo(data.get("query", {}), chunk)
        con.execute("BEGIN")
        for name in chunk:
            r = info.get(name)
            con.execute("UPDATE player_profile SET image_url = ?, image_page = ?, image_license = ?, image_author = ?, image_free = ? "
                        "WHERE image_file = ?",
                        [r["url"], r["page"], r["license"], r["author"], r["free"], name] if r else [None, None, None, None, False, name])
            done += 1
        con.execute("COMMIT")
        if done % 1000 < BATCH:
            log(f"  photos : {done}/{len(todo)} fichiers")
    log(f"  photos : {done} fichiers lus")
    return done


_THUMB_FILE = re.compile(r"/(?:thumb/)?[0-9a-f]/[0-9a-f]{2}/([^/]+?)(?:/\d+px-[^/]+)?$")


def file_of_url(url: str | None) -> str | None:
    """Nom du fichier Wikimedia d'une adresse (miniature `…/thumb/4/47/Nom.svg/250px-Nom.svg.png`, original ou `Special:FilePath/Nom.jpg?width=300`), sans « File: »."""
    if not url:
        return None
    if "Special:FilePath/" in url:
        return unquote(url.split("Special:FilePath/", 1)[1].split("?", 1)[0])
    m = _THUMB_FILE.search(url.split("?", 1)[0])
    return unquote(m.group(1)) if m else None


def missing_files(wp, names: list[str]) -> set[str]:
    """Les fichiers de `names` (sans « File: ») qui n'existent plus, ni sur Wikipedia ni sur Commons (supprimés depuis la lecture)."""
    missing: set[str] = set()
    todo = sorted(set(names))
    for chunk in _chunks(todo, BATCH):
        data = wp._call({"action": "query", "titles": "|".join(_file_title(n) for n in chunk), "prop": "imageinfo", "iiprop": "url", "redirects": 1})
        missing |= set(chunk) - set(parse_imageinfo(data.get("query", {}), chunk))
    return missing


def check_images(con: duckdb.DuckDBPyConnection, wp, wd=None, *, part: tuple[int, int] | None = None, log: Callable[[str], None] = print) -> dict[str, int]:
    """Retire les images publiées dont le fichier a été supprimé de Wikimedia depuis leur lecture : elles s'afficheraient cassées sur le site.
    Une photo de joueur est remplacée par l'image actuelle de sa page Wikipedia anglaise (`pageimages`), à défaut par l'image (P18) de son élément Wikidata (`wd`), puis résolue comme les autres ;
    sinon le joueur n'a plus de photo. Un logo de club supprimé est retiré (le site dessine alors un écusson). Rend {photos, remplacées, logos}.
    `part` = (k, n) : ne contrôle que les fichiers du k-ième quart (par empreinte du nom), pour borner le temps d'un passage ; en tournant sur la semaine, tout est vu en n passages."""
    photos = {r[0] for r in con.execute("SELECT DISTINCT image_file FROM player_profile WHERE image_file IS NOT NULL AND image_url IS NOT NULL").fetchall()}
    logos: dict[str, list[int]] = {}
    for cid, url in con.execute("SELECT id, logo_url FROM club WHERE logo_url IS NOT NULL").fetchall():
        if (f := file_of_url(url)):
            logos.setdefault(f, []).append(cid)
    files = [f for f in photos | set(logos) if part is None or zlib.crc32(f.encode()) % part[1] == part[0]]
    gone = missing_files(wp, files)
    out = {"photos": 0, "remplacées": 0, "logos": 0}
    for name in gone & set(logos):
        con.execute("UPDATE club SET logo_url = NULL, logo_license = NULL, logo_commons_url = NULL WHERE id IN (SELECT unnest(?))", [logos[name]])
        out["logos"] += len(logos[name])
    lost = sorted(gone & photos)
    lost_ids = [r[0] for r in con.execute("SELECT player_id FROM player_profile WHERE image_file IN (SELECT unnest(?))", [lost]).fetchall()] if lost else []
    for name in lost:
        con.execute("UPDATE player_profile SET image_file = NULL, image_caption = NULL, image_url = NULL, image_page = NULL, image_license = NULL, image_author = NULL, "
                    "image_free = NULL WHERE image_file = ?", [name])
    out["photos"] = len(lost)
    # L'image actuelle de la page du joueur : la plus fréquente raison d'une suppression est un remplacement par une meilleure photo.
    by_title: dict[str, list[int]] = {}
    for pid, t in con.execute("""SELECT p.id, p.link_title FROM player p JOIN player_profile pr ON pr.player_id = p.id
                                 WHERE p.id IN (SELECT unnest(?)) AND p.link_lang = 'en' AND p.link_title IS NOT NULL""", [lost_ids]).fetchall():
        by_title.setdefault(t, []).append(pid)
    replaced: set[str] = set()
    got: set[int] = set()
    for chunk in _chunks(sorted(by_title), BATCH):
        data = wp._call({"action": "query", "titles": "|".join(chunk), "prop": "pageimages", "piprop": "name", "redirects": 1})
        q = data.get("query", {})
        moved = {m["to"]: m["from"] for key in ("normalized", "redirects") for m in q.get(key, [])}
        for pg in q.get("pages", []):
            new, title = pg.get("pageimage"), pg.get("title")
            if not new or new in gone:
                continue
            for t in {title, moved.get(title), moved.get(moved.get(title, ""), "")}:
                for pid in by_title.get(t, []):
                    con.execute("UPDATE player_profile SET image_file = ? WHERE player_id = ?", [new, pid])
                    out["remplacées"] += 1
                    replaced.add(new)
                    got.add(pid)
    if wd is not None:                                   # à défaut, l'image de l'élément Wikidata (souvent déjà remplacée là, avant la page)
        qid_of = dict(con.execute("SELECT player_id, qid FROM player_wikidata WHERE player_id IN (SELECT unnest(?))", [sorted(set(lost_ids) - got)]).fetchall())
        pids_of: dict[str, list[int]] = {}
        for pid, qid in qid_of.items():
            pids_of.setdefault(qid, []).append(pid)
        for chunk in _chunks(sorted(pids_of), BATCH):
            for qid, ent in wd.entities(chunk, props="claims").items():
                claim = ((ent.get("claims") or {}).get("P18") or [{}])[0]
                new = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                if new and new not in gone:
                    for pid in pids_of.get(qid, []):
                        con.execute("UPDATE player_profile SET image_file = ? WHERE player_id = ?", [new, pid])
                        out["remplacées"] += 1
                        replaced.add(new)
    enrich_player_photos(con, wp, only=replaced, log=log)              # résout l'adresse, la licence et l'auteur des images qui n'ont pas encore ces informations
    log(f"  images : {out['photos']} photos supprimées de Wikimedia retirées ({out['remplacées']} remplacées par l'image actuelle de la page), {out['logos']} logos de clubs retirés")
    return out


def parse_birth(rows: list[dict]) -> dict[str, tuple[date, int]]:
    """Lignes SPARQL (?p ?dob ?prec) -> {qid: (date, précision)} ; si plusieurs, la plus précise."""
    best: dict[str, tuple[date, int]] = {}
    for r in rows:
        qid = r["p"].rsplit("/", 1)[-1]
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", r["dob"])
        if not m:
            continue                                   # année négative ou format inattendu : on ignore
        prec = int(float(r["prec"]))
        try:
            d = date(int(m.group(1)), max(int(m.group(2)), 1), max(int(m.group(3)), 1))
        except ValueError:
            continue
        if not MIN_BIRTH_YEAR <= d.year <= date.today().year - MIN_PLAYER_AGE:
            continue                                   # « né en 1515 » (un saint homonyme) ou « en 2100 » : une date impossible vaut moins qu'une date inconnue
        if qid not in best or prec > best[qid][1]:
            best[qid] = (d, prec)
    return best


MIN_BIRTH_YEAR, MIN_PLAYER_AGE = 1870, 10          # un joueur d'un effectif est né après 1870 et a plus de 10 ans


# Éléments Wikidata dont la date de naissance est celle d'un homonyme ou une erreur (carrière ou statistiques bien avant la naissance : Jefté Betancor « né en 2026 »,
# Mike Flynn né en 1980 pour une carrière dès 1987…). On préfère une date inconnue à une date fausse ; `audit` signale les nouveaux cas.
UNRELIABLE_BIRTH = ("Q3822716", "Q113459658", "Q6176406", "Q529244", "Q2529972", "Q93969423", "Q16586609", "Q111547565", "Q1337570", "Q669575", "Q6846866", "Q1375717")


def enrich_birth_dates(con: duckdb.DuckDBPyConnection, wd, *, log: Callable[[str], None] = print) -> int:
    """Date de naissance (P569) des joueurs avec QID qui n'en ont pas encore."""
    marks = ",".join("?" for _ in UNRELIABLE_BIRTH)
    con.execute(f"DELETE FROM player_birth WHERE player_id IN (SELECT player_id FROM player_wikidata WHERE qid IN ({marks}))", list(UNRELIABLE_BIRTH))
    rows = con.execute(f"""SELECT p.id, w.qid FROM player p JOIN player_wikidata w ON w.player_id = p.id
                          WHERE NOT EXISTS (SELECT 1 FROM player_birth b WHERE b.player_id = p.id) AND w.qid NOT IN ({marks}) ORDER BY p.id""",
                      list(UNRELIABLE_BIRTH)).fetchall()
    by_qid = {q: pid for pid, q in rows}
    written = 0
    for chunk in _chunks(list(by_qid), BIRTH_BATCH):
        sparql = ("SELECT ?p ?dob ?prec WHERE { VALUES ?p { " + " ".join(f"wd:{q}" for q in chunk) + " } "
                  "?p p:P569 ?s . ?s psv:P569 ?v . ?v wikibase:timeValue ?dob ; wikibase:timePrecision ?prec . }")
        got = parse_birth(wd.query(sparql))
        con.execute("BEGIN")
        for qid, (d, prec) in got.items():
            con.execute("INSERT INTO player_birth VALUES (?, ?, ?) ON CONFLICT DO NOTHING", [by_qid[qid], d, prec])
            written += 1
        con.execute("COMMIT")
    log(f"  dates de naissance : {len(by_qid)} joueurs interrogés, {written} dates écrites")
    return written


def enrich_logos(con: duckdb.DuckDBPyConnection, wp, *, refresh: bool = False, all_clubs: bool = False,
                 limit: int | None = None, log: Callable[[str], None] = print) -> int:
    """Logo de chaque club = le champ `image` de l'infobox de sa page Wikipedia anglaise, avec sa licence.

    On n'utilise PAS « l'image principale de la page » : c'est souvent un montage (« X through the ages »),
    une photo de stade ou une personne, pas le logo. Sans champ `image` dans l'infobox, le club n'a pas de logo.
    Beaucoup de logos sont « non libres » (usage loyal) : la licence est stockée pour pouvoir les masquer."""
    scope = _logo_scope(all_clubs)
    if refresh:
        con.execute(f"UPDATE club SET logo_url = NULL, logo_license = NULL WHERE {scope}")
    todo = con.execute(f"SELECT count(*) FROM club WHERE logo_url IS NULL AND {scope}").fetchone()[0]
    found = _infobox_logos(con, wp, scope, limit)
    log(f"  logos : {todo} clubs interrogés, {found} logos trouvés (infobox)")
    return found


_IMAGE_FIELD = re.compile(r"\|\s*(?:image|logo)\s*=\s*([^\n|]+)", re.I)


def _logo_scope(all_clubs: bool) -> str:
    """Par défaut : nos clubs à effectifs. `all_clubs` : tout club ayant une page anglaise (des milliers de requêtes)."""
    base = "wikipedia_title IS NOT NULL"
    return base if all_clubs else base + " AND EXISTS (SELECT 1 FROM club_season cs WHERE cs.club_id = club.id)"


def _infobox_logos(con: duckdb.DuckDBPyConnection, wp, scope: str, limit: int | None = None) -> int:
    """Les logos non libres sont ignorés par l'API « image de page » : on lit le champ `image` de l'infobox
    du club (introduction de la page), puis la miniature et la licence du fichier."""
    # Les plus notoires d'abord (nombre de versions Wikipedia) : un passage partiel couvre déjà les clubs consultés.
    clubs = con.execute(f"SELECT id, wikipedia_title FROM club WHERE logo_url IS NULL AND {scope} "
                        f"ORDER BY coalesce(wikipedia_count, 0) DESC, id" + (f" LIMIT {int(limit)}" if limit else "")).fetchall()
    found = 0
    for chunk in _chunks(clubs, BATCH):
        for cid, (url, lic) in _logos_of_pages(wp, chunk).items():
            con.execute("UPDATE club SET logo_url = ?, logo_license = ? WHERE id = ?", [url, lic, cid])
            found += 1
    return found


def _logos_of_pages(wp, chunk: list[tuple[int, str]]) -> dict[int, tuple[str, str]]:
    """Pour (id, titre de page) : {id: (miniature, licence)} d'après le champ `image` de l'infobox (introduction de la page)."""
    data = wp._call({"action": "query", "titles": "|".join(t for _, t in chunk), "redirects": 1,
                     "prop": "revisions", "rvprop": "content", "rvslots": "main", "rvsection": 0})["query"]
    step1 = {n["from"]: n["to"] for n in data.get("normalized", [])}
    step2 = {r["from"]: r["to"] for r in data.get("redirects", [])}
    lead = {p["title"]: p["revisions"][0]["slots"]["main"]["content"]
            for p in data.get("pages", []) if p.get("revisions")}
    files: dict[int, str] = {}
    for cid, t in chunk:
        m = _IMAGE_FIELD.search(lead.get(step2.get(step1.get(t, t), step1.get(t, t)), ""))
        raw = re.split(r"\{\{!\}\}|\|", m.group(1))[0] if m else ""        # « x.svg{{!}}class=… » : options d'affichage
        name = unquote(re.sub(r"^(?:\[\[)?(?:File|Image):", "", raw.strip(), flags=re.I).rstrip("]").strip())      # « Logo de la Conmebol Copa Am%C3%A9rica.svg »
        if name:
            files[cid] = "File:" + name
    out: dict[int, tuple[str, str]] = {}
    if not files:
        return out
    info = wp._call({"action": "query", "titles": "|".join(sorted(set(files.values()))), "prop": "imageinfo",
                     "iiprop": "url|extmetadata", "iiurlwidth": 200})["query"]
    norm = {n["from"]: n["to"] for n in info.get("normalized", [])}
    by_file = {p["title"]: (p.get("imageinfo") or [{}])[0] for p in info.get("pages", [])}
    for cid, f in files.items():
        ii = by_file.get(norm.get(f, f)) or {}
        url = (ii.get("thumburl") or "").split("?")[0]
        if not url:
            continue
        meta = ii.get("extmetadata", {})
        lic = (meta.get("LicenseShortName") or {}).get("value") or (
            "non-free" if (meta.get("NonFree") or {}).get("value") else "unknown")
        out[cid] = (url, lic)
    return out


def enrich_league_logos(con: duckdb.DuckDBPyConnection, wp, *, log=print) -> int:
    """Logo de chaque championnat (page anglaise, infobox), dans `competition_info`. Le titre de page est le nom anglais
    du championnat, sauf exception dans `LEAGUE_PAGES`."""
    rows = con.execute("SELECT id, name_en FROM competition ORDER BY id").fetchall()
    chunk = [(cid, LEAGUE_PAGES.get(name, name)) for cid, name in rows]
    found: dict[int, tuple[str, str]] = {}
    for part in _chunks(chunk, BATCH):               # l'API refuse plus de 50 titres par requête
        found.update(_logos_of_pages(wp, part))
    for cid, title in chunk:
        code = con.execute("SELECT code FROM competition WHERE id = ?", [cid]).fetchone()[0]
        url, lic = found.get(cid, (None, None))
        con.execute("DELETE FROM competition_info WHERE code = ?", [code])
        con.execute("INSERT INTO competition_info (code, wikipedia_title, logo_url, logo_license) VALUES (?, ?, ?, ?)", [code, title, url, lic])
    log(f"  logos de championnats : {len(found)}/{len(rows)}")
    return len(found)


LEAGUE_PAGES: dict[str, str] = {}      # nom anglais du championnat -> titre de page, quand ils diffèrent

# Page Wikipedia anglaise de chaque compétition `OF:*` de `match` (celles que nous n'avons pas comme championnat). Les qualifications reprennent la page (et donc le logo)
# du tournoi qu'elles préparent ; les matchs amicaux n'ont pas de page.
_WORLD_CUP, _EURO, _COPA, _AFCON, _ASIAN, _GOLD, _OFC, _CNL = ("FIFA World Cup", "UEFA European Championship", "Copa América", "Africa Cup of Nations", "AFC Asian Cup",
                                                              "CONCACAF Gold Cup", "OFC Nations Cup", "CONCACAF Nations League")
OF_PAGES: dict[str, str] = {
    "OF:worldcup": _WORLD_CUP, "OF:fifa_world_cup_qualification": _WORLD_CUP, "OF:euro": _EURO, "OF:uefa_euro_qualification": _EURO,
    "OF:copa_america": _COPA, "OF:copa_america_qualification": _COPA, "OF:african_cup_of_nations": _AFCON, "OF:african_cup_of_nations_qualification": _AFCON,
    "OF:afc_asian_cup": _ASIAN, "OF:afc_asian_cup_qualification": _ASIAN, "OF:gold_cup": _GOLD, "OF:gold_cup_qualification": _GOLD,
    "OF:oceania_nations_cup": _OFC, "OF:oceania_nations_cup_qualification": _OFC, "OF:uefa_nations_league": "UEFA Nations League",
    "OF:concacaf_nations_league": _CNL, "OF:concacaf_nations_league_qualification": _CNL,
    "OF:afl": "African Football League", "OF:at.2": "2. Liga (Austria)", "OF:concacafcl": "CONCACAF Champions Cup", "OF:copa-sudamericana": "Copa Sudamericana",
    "OF:cr1": "Liga FPD", "OF:en.3": "EFL League One", "OF:en.4": "EFL League Two", "OF:il2": "Liga Leumit", "OF:ilcup": "Israel State Cup",
    "OF:ke1": "Kenyan Premier League", "OF:mw1": "Super League of Malawi", "OF:mx2ascenso": "Ascenso MX", "OF:mx2expansion": "Liga de Expansión MX",
    "OF:ng2": "Nigeria National League", "OF:rw1": "Rwanda Premier League",
}


def enrich_match_competition_logos(con: duckdb.DuckDBPyConnection, wp, *, log=print) -> int:
    """Titre de page Wikipedia et logo (infobox) de chaque compétition `OF:*`, dans `competition_info` (même table que nos championnats).
    Une compétition sans page connue (matchs amicaux) n'a ni lien ni logo."""
    chunk = [(code, OF_PAGES[code]) for (code,) in con.execute("SELECT code FROM match_competition ORDER BY code").fetchall() if code in OF_PAGES]
    found: dict[str, tuple[str, str]] = {}
    for part in _chunks(chunk, BATCH):
        found.update(_logos_of_pages(wp, part))
    for code, title in chunk:
        url, lic = found.get(code, (None, None))
        con.execute("DELETE FROM competition_info WHERE code = ?", [code])
        con.execute("INSERT INTO competition_info (code, wikipedia_title, logo_url, logo_license) VALUES (?, ?, ?, ?)", [code, title, url, lic])
    log(f"  logos des compétitions de matchs : {len(found)}/{len(chunk)}")
    return len(found)
