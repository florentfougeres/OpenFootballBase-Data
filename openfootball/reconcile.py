"""Un joueur = un QID Wikidata, quelle que soit la langue de la page qui le cite.

Sans ça, le même joueur lu en anglais puis en italien donne deux lignes, et deux homonymes sont
confondus si l'on regroupe par nom. On résout chaque lien Wikipedia en QID, puis on fusionne les
doublons. Une fusion qui toucherait une saison figée est refusée (SPEC L9) et rapportée.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

import duckdb

from openfootball.names import clean_person_name, fold, full_name, name_tokens, same_name_variant
from openfootball.sources.wikidata import club_qids   # titre Wikipedia -> QID (valable pour tout titre)


@dataclass
class ReconcileReport:
    resolved: int = 0                 # joueurs dont on a appris le QID
    unresolved: int = 0               # lien sans QID (page supprimée, sans élément Wikidata)
    merged: int = 0                   # doublons fusionnés
    blocked: list[str] = field(default_factory=list)   # fusions refusées (saison figée)
    removed: int = 0                  # lignes d'effectif retirées à un homonyme lié à tort
    blocked_pairs: list[tuple[int, int, int]] = field(default_factory=list)   # (joueur, joueur, club-saison) : deux identités distinctes pour un même rôle dans l'effectif


def _frozen_rows(con, player_id: int) -> int:
    return con.execute("""SELECT count(*) FROM player_club_season pcs
        JOIN club_season cs ON cs.id = pcs.club_season_id JOIN season s ON s.id = cs.season_id
        WHERE pcs.player_id = ? AND s.status = 'frozen'""", [player_id]).fetchone()[0]


def _merge(con, keep: int, dup: int) -> None:
    """Rattache les lignes de `dup` à `keep` ; si les deux ont déjà une ligne pour le même club-saison,
    on garde celle de `keep` (même personne, même effectif). Les liens de `dup` sont mémorisés pour que
    les prochains backfills retombent sur `keep` (sinon le doublon serait recréé)."""
    con.execute("""DELETE FROM player_club_season WHERE player_id = ? AND club_season_id IN
                   (SELECT club_season_id FROM player_club_season WHERE player_id = ?)""", [dup, keep])
    con.execute("UPDATE player_club_season SET player_id = ? WHERE player_id = ?", [keep, dup])
    if con.execute("SELECT count(*) FROM player_career WHERE player_id = ?", [keep]).fetchone()[0]:
        con.execute("DELETE FROM player_career WHERE player_id = ?", [dup])           # on garde la carrière du joueur conservé
    else:
        con.execute("UPDATE player_career SET player_id = ? WHERE player_id = ?", [keep, dup])
    for table in ("player_national", "player_birth"):        # même règle que la carrière : on garde celles du joueur conservé
        if con.execute(f"SELECT count(*) FROM {table} WHERE player_id = ?", [keep]).fetchone()[0]:
            con.execute(f"DELETE FROM {table} WHERE player_id = ?", [dup])
        else:
            con.execute(f"UPDATE {table} SET player_id = ? WHERE player_id = ?", [keep, dup])
    con.execute("""INSERT INTO player_link SELECT link_lang, link_title, ? FROM player
                   WHERE id = ? AND link_title IS NOT NULL ON CONFLICT DO NOTHING""", [keep, dup])
    con.execute("UPDATE player_link SET player_id = ? WHERE player_id = ?", [keep, dup])
    con.execute("DELETE FROM player_wikidata WHERE player_id = ?", [dup])
    _reassign_other_tables(con, keep, dup)
    con.execute("DELETE FROM player WHERE id = ?", [dup])


_ONE_ROW = ("player_profile", "player_openfootball", "player_stat_source")          # une ligne par joueur : celle du joueur conservé gagne
_SETS = ("player_stat_club", "player_stat_national")                                 # un jeu de lignes par joueur : idem
_KEYED = {"squad_row_source": "club_season_id, source_lang", "squad_movement": "club_season_id, direction"}    # une ligne par (effectif, …) : en cas de conflit celle du joueur conservé gagne
_MATCH_TABLES = ("match_goal", "match_lineup", "match_card")                         # le joueur y est cité par son nom : on le rattache simplement


def _reassign_other_tables(con, keep: int, dup: int) -> None:
    """Tout ce qui référence `dup` passe à `keep` (ou est écarté si `keep` a déjà l'équivalent) : sans cela le joueur ne peut pas être supprimé."""
    for table in _ONE_ROW + _SETS:
        if con.execute(f"SELECT count(*) FROM {table} WHERE player_id = ?", [keep]).fetchone()[0]:
            con.execute(f"DELETE FROM {table} WHERE player_id = ?", [dup])
        else:
            con.execute(f"UPDATE {table} SET player_id = ? WHERE player_id = ?", [keep, dup])
    for table, key in _KEYED.items():
        con.execute(f"DELETE FROM {table} WHERE player_id = ? AND ({key}) IN (SELECT {key} FROM {table} WHERE player_id = ?)", [dup, keep])
        con.execute(f"UPDATE {table} SET player_id = ? WHERE player_id = ?", [keep, dup])
    for table in _MATCH_TABLES:
        con.execute(f"UPDATE {table} SET player_id = ? WHERE player_id = ?", [keep, dup])


def _delete_player(con, pid: int) -> None:
    """Supprime un joueur et tout ce qui le référence (les citations dans les matches perdent seulement leur rattachement)."""
    for table in _MATCH_TABLES:
        con.execute(f"UPDATE {table} SET player_id = NULL WHERE player_id = ?", [pid])
    for (table,) in con.execute("SELECT DISTINCT table_name FROM information_schema.columns WHERE column_name = 'player_id' "
                                "AND table_name NOT IN ('match_goal', 'match_lineup', 'match_card')").fetchall():
        con.execute(f"DELETE FROM {table} WHERE player_id = ?", [pid])
    con.execute("DELETE FROM player WHERE id = ?", [pid])


def purge_misplaced_squads(con: duckdb.DuckDBPyConnection, *, log=print) -> dict[str, int]:
    """Retire de la base deux sortes de fausses lignes d'effectif, jamais dans une saison figée :
    1. celles dont la section est un tableau de records (« Most appearances », « Retired numbers », « Player records ») : des légendes nées en 1954 dans l'effectif 2026/27 ;
    2. celles d'une saison PASSÉE dont la source est la page du CLUB et non une page de saison : son tableau « First-team squad » est l'effectif ACTUEL
       (Cerezo Osaka 2011/12 portait des joueurs nés en 2001). Le club-saison reste, enregistré comme trou connu.
    Chaque club-saison touché est tracé dans `amendment_log`. Rend le nombre de lignes retirées par sorte."""
    from openfootball.parse.squad import is_excluded_section
    done = {"records": 0, "page_du_club": 0}

    def drop(cs_id: int, season_id: int, where: str, params: list, why: str) -> int:
        ids = [r[0] for r in con.execute(f"SELECT player_id FROM player_club_season WHERE club_season_id = ? AND {where}", [cs_id, *params]).fetchall()]
        if not ids:
            return 0
        marks = ",".join("?" * len(ids))
        con.execute(f"DELETE FROM squad_row_source WHERE club_season_id = ? AND player_id IN ({marks})", [cs_id, *ids])
        con.execute(f"DELETE FROM player_club_season WHERE club_season_id = ? AND player_id IN ({marks})", [cs_id, *ids])
        con.execute("INSERT INTO amendment_log (id, season_id, club_season_id, description, reason, amended_at) "
                    "VALUES ((SELECT coalesce(max(id), 0) + 1 FROM amendment_log), ?, ?, ?, ?, now())", [season_id, cs_id, f"{len(ids)} ligne(s) d'effectif retirée(s)", why])
        return len(ids)

    sections = [r[0] for r in con.execute("""SELECT DISTINCT pcs.source_section FROM player_club_season pcs JOIN club_season cs ON cs.id = pcs.club_season_id
                                             JOIN season s ON s.id = cs.season_id WHERE s.status <> 'frozen' AND pcs.source_section IS NOT NULL""").fetchall()]
    bad = [s for s in sections if is_excluded_section(s)]
    if bad:
        marks = ",".join("?" * len(bad))
        for cs_id, season_id, section in con.execute(f"""SELECT DISTINCT pcs.club_season_id, cs.season_id, pcs.source_section FROM player_club_season pcs
                JOIN club_season cs ON cs.id = pcs.club_season_id JOIN season s ON s.id = cs.season_id
                WHERE s.status <> 'frozen' AND pcs.source_section IN ({marks})""", bad).fetchall():
            done["records"] += drop(cs_id, season_id, "source_section = ?", [section], f"section « {section} » : un tableau de records ou de joueurs hors effectif, pas l'effectif")
    for cs_id, season_id in con.execute("""SELECT cs.id, cs.season_id FROM club_season cs JOIN club cl ON cl.id = cs.club_id JOIN season s ON s.id = cs.season_id
            WHERE s.status NOT IN ('open', 'frozen') AND cs.source_title = cl.wikipedia_title""").fetchall():
        n = drop(cs_id, season_id, "TRUE", [], "effectif lu sur la page du club (effectif ACTUEL) et non sur une page de saison")
        if n:
            done["page_du_club"] += n
            con.execute("INSERT INTO known_gap (club_season_id, reason, validated_at) VALUES (?, ?, now()) ON CONFLICT DO NOTHING",
                        [cs_id, "pas de page de saison : seule la page du club (effectif actuel) existe"])
    if any(done.values()):
        log(f"{done['records']} lignes de tableaux de records et {done['page_du_club']} lignes d'effectifs lus sur la page du club (effectif actuel) retirées")
    return done


def remove_non_players(con: duckdb.DuckDBPyConnection) -> int:
    """Retire les « joueurs » qui n'en sont pas (« 3 May » lu dans un tableau de suspensions, « Loan ») : sans page ni QID, avec un nom qui est une date ou une
    valeur de tableau. Leurs lignes d'effectif partent avec eux ; chaque retrait est tracé dans `amendment_log`. Une saison figée n'est jamais touchée.
    Rend le nombre de faux joueurs retirés."""
    removed = 0
    for pid, name, why in non_players(con):
        if _frozen_rows(con, pid):
            continue
        for cs, season in con.execute("""SELECT pcs.club_season_id, cs.season_id FROM player_club_season pcs JOIN club_season cs ON cs.id = pcs.club_season_id
                                         WHERE pcs.player_id = ?""", [pid]).fetchall():
            con.execute("INSERT INTO amendment_log (id, season_id, club_season_id, description, reason, amended_at) "
                        "VALUES ((SELECT coalesce(max(id), 0) + 1 FROM amendment_log), ?, ?, ?, ?, now())",
                        [season, cs, f"« {name} » retiré de l'effectif", why])
        _delete_player(con, pid)
        removed += 1
    return removed


_ENTITY_TITLE = re.compile(r"federation|fédération|association|roster slots?|soviet|republic|national (football )?team", re.I)


def non_players(con) -> list[tuple[int, str, str]]:
    """(id, nom, raison) des « joueurs » qui n'en sont pas : un nom de tableau (date, « Loan ») ; ou un club, une fédération, un code pays (« FRA », « AFC Ajax »)
    dont la colonne a été lue comme un nom et que l'on a même rattaché à une page — jamais une personne : pas de naissance, pas de carrière, le QID est celui d'un club
    ou le lien mène à une fédération."""
    from openfootball.parse.squad import looks_like_non_player
    out = []
    club_qids = {r[0] for r in con.execute("SELECT wikidata_qid FROM club WHERE wikidata_qid IS NOT NULL").fetchall()}
    for pid, name, qid, title, loose in con.execute("""
            SELECT p.id, p.name, coalesce(p.wikidata_qid, w.qid), p.link_title, (w.player_id IS NULL AND p.link_title IS NULL)
            FROM player p LEFT JOIN player_wikidata w ON w.player_id = p.id""").fetchall():
        if loose:
            if looks_like_non_player(name) or len(name.split()) >= 6:           # six mots sans lien : une liste de noms de famille collés, pas une personne
                out.append((pid, name, "ce n'est pas un nom de joueur (date, note ou liste lue dans un tableau de l'effectif)"))
        elif (re.fullmatch(r"[A-Z]{2,4}", name) or qid in club_qids or (title and _ENTITY_TITLE.search(title))) \
                and not con.execute("SELECT 1 FROM player_birth WHERE player_id = ? UNION ALL SELECT 1 FROM player_career WHERE player_id = ? LIMIT 1", [pid, pid]).fetchone():
            out.append((pid, name, "ce n'est pas un joueur (club, fédération ou code pays lu dans une colonne de l'effectif)"))
    return out


def normalize_player_names(con: duckdb.DuckDBPyConnection) -> int:
    """« Lloris » (écrit `[[Hugo Lloris|Lloris]]` sur la page de l'équipe) devient « Hugo Lloris » : le nom d'un joueur lié est le titre de sa page
    quand le nom lu n'en est qu'une partie. Rend le nombre de noms modifiés."""
    changed = 0
    for pid, name in con.execute("SELECT id, name FROM player WHERE name LIKE '%, %'").fetchall():        # clé de tri cachée collée au nom (pages fr rendues en HTML)
        m = re.fullmatch(r"(.+?), (.+?)\2 \1", name)
        if m:
            con.execute("UPDATE player SET name = ? WHERE id = ?", [f"{m.group(2)} {m.group(1)}", pid])
            changed += 1
    for pid, name, title in con.execute("SELECT id, name, link_title FROM player WHERE link_title IS NOT NULL").fetchall():
        full = full_name(name, title)
        if full != name:
            con.execute("UPDATE player SET name = ? WHERE id = ?", [full, pid])
            changed += 1
    return changed


_NO_REFERENCE = ("player_club_season", "player_career", "player_stat_club", "player_stat_national", "player_national", "squad_movement", "squad_row_source",
                 "player_openfootball", "match_goal", "match_card", "match_lineup")


def remove_orphan_players(con: duckdb.DuckDBPyConnection) -> int:
    """Retire les fiches que plus rien ne référence : ni effectif, ni carrière, ni statistiques, ni sélection, ni match. Elles restent quand on détache un séjour impossible
    d'un homonyme lié à tort (un saint de 1515 « joueur » du Torino) et n'apportent qu'une page vide. Rend le nombre de fiches retirées."""
    ids = orphan_player_ids(con)
    for pid in ids:
        _delete_player(con, pid)
    return len(ids)


def orphan_player_ids(con: duckdb.DuckDBPyConnection) -> list[int]:
    free = " AND ".join(f"NOT EXISTS (SELECT 1 FROM {t} x WHERE x.player_id = p.id)" for t in _NO_REFERENCE)
    return [r[0] for r in con.execute(f"SELECT p.id FROM player p WHERE {free}").fetchall()]


def drop_impossible_births(con: duckdb.DuckDBPyConnection) -> int:
    """Efface une date de naissance que personne dans un effectif ne peut avoir (avant 1870, ou joueur de moins de 10 ans) : on préfère une date inconnue à une date fausse.
    Rend le nombre de dates effacées."""
    from datetime import date
    from openfootball.enrich import MIN_BIRTH_YEAR, MIN_PLAYER_AGE
    n = con.execute("SELECT count(*) FROM player_birth WHERE year(birth_date) < ? OR year(birth_date) > ?",
                    [MIN_BIRTH_YEAR, date.today().year - MIN_PLAYER_AGE]).fetchone()[0]
    con.execute("DELETE FROM player_birth WHERE year(birth_date) < ? OR year(birth_date) > ?", [MIN_BIRTH_YEAR, date.today().year - MIN_PLAYER_AGE])
    return n


def clean_player_names(con: duckdb.DuckDBPyConnection) -> int:
    """Retire des noms déjà en base ce que le wikicode y a laissé (`note 2]`, `<small>(U18)</small>`, `†`, `(footballer, born 1989)`, « NOM, Prénom »…) : mêmes règles
    que le lecteur (`clean_person_name`). Rend le nombre de noms modifiés."""
    changed = 0
    for pid, name in con.execute("SELECT id, name FROM player").fetchall():
        clean = clean_person_name(name)
        if clean != name:
            con.execute("UPDATE player SET name = ? WHERE id = ?", [clean, pid])
            changed += 1
    return changed


def _identity(qid: str | None, title: str | None) -> tuple | None:
    return ("q", qid) if qid else (("t", title) if title else None)


def _distinct(ia: tuple | None, ib: tuple | None) -> bool:
    """Deux identités prouvent-elles deux personnes ? Deux QID différents, oui ; deux liens différents sans QID, oui ; un QID et un lien sans QID, non (le lien est
    le plus souvent la page du même joueur, pas encore résolue en QID, ou une page inexistante)."""
    if not ia or not ib or ia == ib:
        return False
    return ia[0] == ib[0]


def merge_squad_duplicates(con: duckdb.DuckDBPyConnection) -> ReconcileReport:
    """Répète `_squad_duplicates_pass` jusqu'à ce qu'elle ne change plus rien : une fusion révèle parfois une nouvelle paire (trois graphies d'un même nom). Cumule les comptes."""
    total = ReconcileReport()
    for _ in range(5):
        r = _squad_duplicates_pass(con)
        total.merged += r.merged
        total.removed += r.removed
        total.unresolved = r.unresolved                    # l'état après la dernière passe, pas une somme (les mêmes paires reviennent à chaque passe)
        total.blocked = r.blocked
        if not (r.merged or r.removed):
            break
    return total


def squad_duplicate_pairs(con: duckdb.DuckDBPyConnection) -> list[tuple[int, int, int]]:
    """Les (joueur, joueur, club-saison) qui ressemblent à une même personne citée deux fois dans un effectif : noms identiques à l'accent et à l'ordre près, ou presque
    identiques avec le même numéro (et pas deux postes contradictoires) ; jamais deux numéros différents. Sert à fusionner et à auditer."""
    names = dict(con.execute("SELECT id, name FROM player").fetchall())
    squads: dict[int, list[tuple]] = defaultdict(list)
    for cs, pid, num, pos in con.execute("SELECT club_season_id, player_id, shirt_number, position_code FROM player_club_season").fetchall():
        squads[cs].append((pid, num, pos))
    pairs = set()
    for cs, members in squads.items():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                (a, na, pa), (b, nb, pb) = members[i], members[j]
                if a == b or (na is not None and nb is not None and na != nb):
                    continue
                kind = same_name_variant(names[a], names[b])
                if kind == "close" and not (na is not None and na == nb and (not pa or not pb or pa == pb)):
                    continue
                if kind:
                    pairs.add((a, b, cs))
    return sorted(pairs)


def _squad_duplicates_pass(con: duckdb.DuckDBPyConnection) -> ReconcileReport:
    """Un même effectif ne cite pas deux fois la même personne : « Matvey Safonov » (page anglaise) et « Matveï Safonov » (page française) au PSG, ou « Filip Šimeček » et
    « Filip Simecek » au Slavia, sont un seul joueur lu dans deux sources. On fusionne deux joueurs d'un même club-saison quand
      - leurs noms sont les mêmes mots à l'accent et à l'ordre près ; ou presque les mêmes (translittération, faute de frappe) ET portent le même numéro ;
      - ils n'ont pas deux numéros différents, ni deux identités différentes (deux QID : on ne tranche pas, c'est à l'audit de le dire).
    Le joueur conservé est celui qui a une identité, sinon celui qui a le plus de lignes ; il reprend le numéro et le poste que l'autre était seul à donner.
    Une fusion qui touche une saison figée est refusée (SPEC L9) et rapportée. `unresolved` compte les paires à deux identités laissées telles quelles."""
    report = ReconcileReport()
    info: dict[int, dict] = {}
    for pid, name, qid, title, n in con.execute("""
            SELECT p.id, p.name, coalesce(p.wikidata_qid, w.qid), p.link_title, (SELECT count(*) FROM player_club_season x WHERE x.player_id = p.id)
            FROM player p LEFT JOIN player_wikidata w ON w.player_id = p.id""").fetchall():
        info[pid] = {"name": name, "ident": _identity(qid, title), "rows": n}
    pairs = squad_duplicate_pairs(con)
    seen_conflict: set[tuple[int, int]] = set()
    moved: dict[int, int] = {}

    def rep(x: int) -> int:
        while x in moved:
            x = moved[x]
        return x

    for a, b, cs in sorted(set(pairs)):
        a, b = rep(a), rep(b)
        if a == b:
            continue
        ia, ib = info[a]["ident"], info[b]["ident"]
        if _distinct(ia, ib):
            if (min(a, b), max(a, b)) not in seen_conflict:
                seen_conflict.add((min(a, b), max(a, b)))
                report.unresolved += 1
                report.blocked_pairs.append((a, b, cs))
            continue
        keep, dup = sorted((a, b), key=lambda x: ({"q": 0, "t": 1}.get((info[x]["ident"] or ("", ""))[0], 2), -info[x]["rows"], x))
        if _frozen_rows(con, dup) or _frozen_rows(con, keep):
            report.blocked.append(f"{info[dup]['name']} / {info[keep]['name']}: fusion {dup}->{keep} touche une saison figée")
            continue
        con.execute("""UPDATE player_club_season k SET shirt_number = coalesce(k.shirt_number, d.shirt_number), position_code = coalesce(k.position_code, d.position_code),
                       nationality_raw = coalesce(k.nationality_raw, d.nationality_raw)
                       FROM player_club_season d WHERE k.player_id = ? AND d.player_id = ? AND k.club_season_id = d.club_season_id""", [keep, dup])
        _merge(con, keep, dup)
        moved[dup] = keep
        info[keep]["rows"] += info[dup]["rows"]
        info[keep]["ident"] = info[keep]["ident"] or info[dup]["ident"]
        report.merged += 1
    homonyms = resolve_homonym_slots(con, report.blocked_pairs)
    report.removed, report.unresolved = homonyms.merged, homonyms.unresolved
    report.blocked += homonyms.blocked
    return report


def _impossible_year(i: dict, year: int) -> bool:
    """Ce joueur (naissance, carrière) peut-il figurer dans un effectif de cette saison ? Mêmes règles que `implausible_stays`, pour ne pas recoller ce qu'elle détache."""
    if any(s <= year + 1 and e >= year for s, e in i["spans"]):
        return False
    if i["spans"] and max(e for _, e in i["spans"]) <= year - RETIRED_YEARS:
        return True
    born = i["born"]
    return bool(born and (born.year > year - MIN_AGE or born.year < year - MAX_AGE))


def merge_split_players(con: duckdb.DuckDBPyConnection) -> ReconcileReport:
    """Répète `_split_players_pass` jusqu'à ce qu'elle ne change plus rien (trois morceaux d'un même joueur demandent deux tours). Cumule les comptes."""
    total = ReconcileReport()
    for _ in range(5):
        r = _split_players_pass(con)
        total.merged += r.merged
        total.blocked += r.blocked
        if not r.merged:
            break
    return total


def _split_players_pass(con: duckdb.DuckDBPyConnection) -> ReconcileReport:
    """Le même joueur coupé en deux fiches d'un même club, d'une saison à l'autre : l'une liée à sa page (ou à son QID), l'autre lue sans lien (ou écrite autrement) dans la saison
    suivante. Aucune saison commune, donc `merge_squad_duplicates` ne les voit pas. On les réunit quand
      - c'est le même club, et le même nom (mots identiques à l'accent et à l'ordre près ; un nom d'un seul mot — « Diego » — exige en plus le même numéro), ou un nom
        presque pareil ET le même numéro ;
      - les saisons se touchent (au plus une saison d'écart) sans jamais coïncider : deux homonymes du même club ne se suivent pas de saison en saison sans se croiser ;
      - ni deux identités distinctes (deux QID), ni deux dates de naissance différentes.
    Une fusion qui touche une saison figée est refusée (SPEC L9). `merged` = fiches fusionnées."""
    report = ReconcileReport()
    info: dict[int, dict] = {}
    for pid, name, qid, title, bd in con.execute("""
            SELECT p.id, p.name, coalesce(p.wikidata_qid, w.qid), p.link_title,
                   (SELECT min(birth_date) FROM player_birth b WHERE b.player_id = p.id AND b.precision >= 9)
            FROM player p LEFT JOIN player_wikidata w ON w.player_id = p.id""").fetchall():
        info[pid] = {"name": name, "ident": _identity(qid, title), "born": bd, "rows": 0, "spans": [],
                     "by_club": defaultdict(lambda: {"years": set(), "numbers": set()})}          # club -> saisons et numéros portés dans ce club
    for pid, start, end in con.execute("SELECT player_id, coalesce(start_year, 0), coalesce(end_year, 9999) FROM player_career").fetchall():
        info[pid]["spans"].append((start, end))
    by_club: dict[int, set[int]] = defaultdict(set)
    for club, pid, year, num in con.execute("""SELECT cs.club_id, x.player_id, s.start_year, x.shirt_number FROM player_club_season x
            JOIN club_season cs ON cs.id = x.club_season_id JOIN season s ON s.id = cs.season_id""").fetchall():
        i = info[pid]
        i["rows"] += 1
        by_club[club].add(pid)
        i["by_club"][club]["years"].add(year)
        if num is not None:
            i["by_club"][club]["numbers"].add(num)

    candidates: set[tuple[int, int, int]] = set()
    for club, pids in by_club.items():
        same: dict[tuple, list[int]] = defaultdict(list)
        numbered: dict[int, list[int]] = defaultdict(list)
        for pid in pids:
            same[tuple(sorted(name_tokens(info[pid]["name"])))].append(pid)
            for n in info[pid]["by_club"][club]["numbers"]:
                numbered[n].append(pid)
        for key, group in same.items():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = sorted((group[i], group[j]))
                    if len(key) > 1 or info[a]["by_club"][club]["numbers"] & info[b]["by_club"][club]["numbers"]:
                        candidates.add((a, b, club))
        for group in numbered.values():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = sorted((group[i], group[j]))
                    if same_name_variant(info[a]["name"], info[b]["name"]):
                        candidates.add((a, b, club))

    moved: dict[int, int] = {}

    def rep(x: int) -> int:
        while x in moved:
            x = moved[x]
        return x

    for a, b, club in sorted(candidates):
        a, b = rep(a), rep(b)
        if a == b or a not in info or b not in info:
            continue
        ia, ib = info[a], info[b]
        if _distinct(ia["ident"], ib["ident"]) or (ia["born"] and ib["born"] and ia["born"] != ib["born"]):
            continue
        ya, yb = ia["by_club"][club]["years"], ib["by_club"][club]["years"]
        if ya & yb or min(yb) > max(ya) + 1 or min(ya) > max(yb) + 1:
            continue
        if any(_impossible_year(ia, y) for c in ib["by_club"].values() for y in c["years"]) \
                or any(_impossible_year(ib, y) for c in ia["by_club"].values() for y in c["years"]):
            continue                                          # le rattachement créerait un séjour que l'âge ou la carrière interdit : `split_implausible_stays` le défait
        keep, dup = sorted((a, b), key=lambda x: ({"q": 0, "t": 1}.get((info[x]["ident"] or ("", ""))[0], 2), -info[x]["rows"], x))
        if _frozen_rows(con, dup) or _frozen_rows(con, keep):
            report.blocked.append(f"{info[dup]['name']} / {info[keep]['name']}: fusion {dup}->{keep} touche une saison figée")
            continue
        _merge(con, keep, dup)
        moved[dup] = keep
        ki, di = info[keep], info[dup]
        ki["rows"] += di["rows"]
        ki["ident"] = ki["ident"] or di["ident"]
        ki["born"] = ki["born"] or di["born"]
        for c, d in di["by_club"].items():
            ki["by_club"][c]["years"] |= d["years"]
            ki["by_club"][c]["numbers"] |= d["numbers"]
        report.merged += 1
    return report


def resolve_homonym_slots(con: duckdb.DuckDBPyConnection, pairs: list[tuple[int, int, int]]) -> ReconcileReport:
    """Deux joueurs d'identités différentes tiennent la même place d'un effectif (même nom, même numéro) : un seul peut y être, l'autre est un homonyme lié à tort
    (Javier Hernández au Real Madrid : le QID de l'attaquant mexicain et celui d'un autre). On garde celui dont la CARRIÈRE contient ce club cette saison et on retire la
    ligne de l'autre, seulement si l'un est prouvé et l'autre non. Sinon on ne tranche pas (`unresolved`) : c'est à l'audit de le dire. `merged` = lignes retirées."""
    report = ReconcileReport()
    link_qid = _club_qids_by_link(con)
    careers: dict[int, list[tuple]] = defaultdict(list)
    for pid, link, name, start, end in con.execute("SELECT player_id, club_link, club_name, start_year, end_year FROM player_career").fetchall():
        careers[pid].append((link, name, start, end))
    for a, b, cs in pairs:
        row = con.execute("""SELECT cl.wikipedia_title, s.start_year, cl.wikidata_qid, s.status, s.id, cl.name_en, s.label FROM club_season x JOIN club cl ON cl.id = x.club_id
                             JOIN season s ON s.id = x.season_id WHERE x.id = ?""", [cs]).fetchone()
        if not row or not all(con.execute("SELECT 1 FROM player_club_season WHERE player_id = ? AND club_season_id = ?", [p, cs]).fetchone() for p in (a, b)):
            continue                                              # la place a déjà été réglée (fusion ou retrait précédents)
        title, year, club_qid, status, season_id, club, label = row
        ok = {p: _supported(careers.get(p, []), title or club, year, club_qid, link_qid) for p in (a, b)}
        if ok[a] == ok[b]:
            report.unresolved += 1
            continue
        wrong = b if ok[a] else a
        if status == "frozen":
            report.blocked.append(f"{club} {label} : homonyme {wrong} dans une saison figée")
            continue
        name = con.execute("SELECT name FROM player WHERE id = ?", [wrong]).fetchone()[0]
        con.execute("INSERT INTO amendment_log (id, season_id, club_season_id, description, reason, amended_at) "
                    "VALUES ((SELECT coalesce(max(id), 0) + 1 FROM amendment_log), ?, ?, ?, ?, now())",
                    [season_id, cs, f"« {name} » retiré de l'effectif", "homonyme lié à tort : sa carrière ne contient pas ce club cette saison, celle de l'autre joueur du même nom, si"])
        for table in ("squad_row_source", "squad_movement", "player_club_season"):
            con.execute(f"DELETE FROM {table} WHERE player_id = ? AND club_season_id = ?", [wrong, cs])
        report.merged += 1
    return report


def apply_player_aliases(con: duckdb.DuckDBPyConnection) -> int:
    """Applique la table `player_alias` aux joueurs déjà en base : un joueur SANS lien dont le nom est listé reçoit la page indiquée
    (ou est fusionné avec le joueur qui l'a déjà). `reconcile_players` en apprend ensuite le QID. Rend le nombre de joueurs touchés."""
    done = 0
    for name, lang, title in con.execute("SELECT name, link_lang, link_title FROM player_alias").fetchall():
        loose = [r[0] for r in con.execute("SELECT id FROM player WHERE name = ? AND link_title IS NULL", [name]).fetchall()]
        target = con.execute("SELECT player_id FROM player_link WHERE link_lang = ? AND link_title = ?", [lang, title]).fetchone() \
            or con.execute("SELECT id FROM player WHERE link_lang = ? AND link_title = ?", [lang, title]).fetchone()
        for pid in loose:
            if _frozen_rows(con, pid):
                continue
            if not target:       # DuckDB ne modifie pas un joueur référencé : on crée le joueur lié, puis on y fusionne l'autre
                new_id = con.execute("SELECT coalesce(max(id), 0) + 1 FROM player").fetchone()[0]
                con.execute("INSERT INTO player (id, name, link_lang, link_title) VALUES (?, ?, ?, ?)", [new_id, name, lang, title])
                target = (new_id,)
            if target[0] != pid:
                _merge(con, target[0], pid)
            done += 1
    return done


def reconcile_players(con: duckdb.DuckDBPyConnection, clients: dict, *, batch: int = 50) -> ReconcileReport:
    """`clients` : {langue: WikipediaClient}. Idempotent : ne traite que les joueurs sans QID."""
    report = ReconcileReport()
    todo = con.execute("SELECT p.id, p.link_lang, p.link_title FROM player p "
                       "LEFT JOIN player_wikidata w ON w.player_id = p.id "
                       "WHERE w.player_id IS NULL AND p.link_title IS NOT NULL ORDER BY p.id").fetchall()
    by_lang: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for pid, lang, title in todo:
        by_lang[lang].append((pid, title))

    for lang, items in by_lang.items():
        titles = sorted({t for _, t in items})
        qids: dict[str, str | None] = {}
        for i in range(0, len(titles), batch):
            qids.update(club_qids(clients[lang], titles[i:i + batch]))
        for pid, title in items:
            qid = qids.get(title)
            if not qid:
                report.unresolved += 1
                continue
            owner = con.execute("SELECT player_id FROM player_wikidata WHERE qid = ?", [qid]).fetchone()
            if owner is None:
                con.execute("INSERT INTO player_wikidata VALUES (?, ?)", [pid, qid])
                report.resolved += 1
            elif owner[0] != pid:
                if _frozen_rows(con, pid) or _frozen_rows(con, owner[0]):
                    report.blocked.append(f"{qid}: fusion {pid}->{owner[0]} touche une saison figée")
                    continue
                _merge(con, owner[0], pid)
                report.merged += 1
    return report


# --------------------------------------------------------------------------------------------------
# Joueurs SANS lien (pages françaises) : rattachés par nom + PREUVE de carrière, jamais par le nom seul.

_CLUB_STOP = {"fc", "f", "c", "afc", "cf", "ac", "the", "football", "club", "calcio"}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", fold(text)).strip()


def _club_key(text: str) -> frozenset[str]:
    return frozenset(w for w in _norm(text.replace(".", "")).split() if w not in _CLUB_STOP)    # « A.S. Roma » = « AS Roma »


def _club_qids_by_link(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """Titre de page d'un club (redirections des carrières comprises : « AS Nancy Lorraine ») -> QID Wikidata."""
    out = dict(con.execute("SELECT link_title, qid FROM club_link_qid WHERE qid IS NOT NULL").fetchall())
    out.update(con.execute("SELECT wikipedia_title, wikidata_qid FROM club WHERE wikipedia_title IS NOT NULL AND wikidata_qid IS NOT NULL").fetchall())
    return out


def _supported(spells: list[tuple], club_title: str, season_year: int, club_qid: str | None = None, link_qid: dict[str, str] | None = None) -> bool:
    """Vrai si la carrière (infobox) contient ce club pendant cette saison (années calendaires Y ou Y+1).
    Le club se reconnaît d'abord par son QID Wikidata (`club_qid` de l'effectif, `link_qid` : titre de la carrière -> QID), sinon par son nom."""
    key = _club_key(club_title)
    for link, name, start, end in spells:
        same = bool(club_qid and link and link_qid and link_qid.get(link) == club_qid) or bool(key and key in (_club_key(link or ""), _club_key(name or "")))
        if not same:
            continue
        if start is None or (start <= season_year + 1 and (end is None or end >= season_year)):
            return True
    return False


YOUTH_YEARS = 3      # saisons avant un séjour prouvé pendant lesquelles un joueur peut être listé (équipe de jeunes) sans figurer dans la carrière « senior »


def _stays_proven(spells: list[tuple], stays: list[tuple], link_qid: dict[str, str] | None) -> bool:
    """La carrière (infobox) prouve les séjours du joueur de notre base : (club, saison de début, QID du club).
    Chaque séjour doit être couvert ; seule exception, un séjour NON couvert qui précède d'au plus `YOUTH_YEARS` saisons un séjour couvert DANS LE MÊME CLUB
    (un jeune listé dans l'effectif avant ses débuts « senior » : Torino 2017 et 2018, carrière au Torino dès 2019). Au moins un séjour doit être couvert."""
    if not stays:
        return False
    covered = [(c, y) for c, y, q in stays if _supported(spells, c, y, q, link_qid)]
    if not covered:
        return False
    for c, y, q in stays:
        if (c, y) in covered:
            continue
        if not any(cc == c and 0 < yy - y <= YOUTH_YEARS for cc, yy in covered):
            return False
    return True


def reconcile_by_name(con: duckdb.DuckDBPyConnection) -> ReconcileReport:
    """Rattache un joueur sans lien à un joueur identifié (QID) de même nom, SEULEMENT si la carrière de
    celui-ci contient chacun des club-saisons du joueur sans lien et qu'un seul candidat y répond.
    Les cas ambigus ou non prouvés restent séparés (identité faible plutôt que fusion hasardeuse)."""
    report = ReconcileReport()
    ident: dict[str, list[int]] = defaultdict(list)
    for pid, name in con.execute("SELECT p.id, p.name FROM player p JOIN player_wikidata w ON w.player_id = p.id").fetchall():
        ident[_norm(name)].append(pid)
    careers: dict[int, list[tuple]] = defaultdict(list)
    for pid, link, name, start, end in con.execute(
            "SELECT player_id, club_link, club_name, start_year, end_year FROM player_career").fetchall():
        careers[pid].append((link, name, start, end))

    link_qid = _club_qids_by_link(con)
    loose = con.execute("SELECT p.id, p.name FROM player p LEFT JOIN player_wikidata w ON w.player_id = p.id "
                        "WHERE p.link_title IS NULL AND w.player_id IS NULL").fetchall()
    for pid, name in loose:
        cands = [c for c in ident.get(_norm(name), []) if careers.get(c)]
        if not cands:
            report.unresolved += 1
            continue
        stays = con.execute("""SELECT cl.wikipedia_title, s.start_year, cl.wikidata_qid FROM player_club_season pcs
            JOIN club_season cs ON cs.id = pcs.club_season_id JOIN club cl ON cl.id = cs.club_id
            JOIN season s ON s.id = cs.season_id WHERE pcs.player_id = ?""", [pid]).fetchall()
        proven = [c for c in cands if _stays_proven(careers[c], stays, link_qid)]
        if len(proven) != 1:
            report.unresolved += 1
            continue
        if _frozen_rows(con, pid) or _frozen_rows(con, proven[0]):
            report.blocked.append(f"{name}: fusion {pid}->{proven[0]} touche une saison figée")
            continue
        _merge(con, proven[0], pid)
        report.merged += 1
    return report


# --------------------------------------------------------------------------------------------------
# Homonymes mal rattachés : le lien de la page du club mène à un autre joueur du même nom.

MIN_AGE, MAX_AGE = 14, 46     # hors de ces âges (date de naissance précise au moins à l'année), nul ne figure dans un effectif…
RETIRED_YEARS = 3             # … ni un joueur dont la carrière s'est terminée plus de 3 saisons avant

_IMPLAUSIBLE_STAYS = f"""
    WITH span AS (SELECT player_id, max(coalesce(end_year, 9999)) AS last_end FROM player_career GROUP BY 1)
    SELECT pcs.id, pcs.player_id, pcs.club_season_id, p.name, s.start_year, s.label, cl.name_en, s.status,
           year(b.birth_date), span.last_end
    FROM player_club_season pcs JOIN player p ON p.id = pcs.player_id
    JOIN club_season cs ON cs.id = pcs.club_season_id JOIN season s ON s.id = cs.season_id JOIN club cl ON cl.id = cs.club_id
    LEFT JOIN span ON span.player_id = pcs.player_id
    LEFT JOIN player_birth b ON b.player_id = pcs.player_id AND b.precision >= 9
    WHERE NOT EXISTS (SELECT 1 FROM player_career c WHERE c.player_id = pcs.player_id        -- une période de carrière couvre la saison : plausible
                      AND coalesce(c.start_year, 0) <= s.start_year + 1 AND coalesce(c.end_year, 9999) >= s.start_year)
      AND (span.last_end <= s.start_year - {RETIRED_YEARS}
           OR year(b.birth_date) > s.start_year - {MIN_AGE} OR year(b.birth_date) < s.start_year - {MAX_AGE})
    ORDER BY s.start_year DESC, cl.name_en, p.name"""


def implausible_stays(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Lignes d'effectif qu'un joueur lié ne peut pas avoir tenues : âge impossible pour la saison, ou carrière (infobox) terminée
    plus de `RETIRED_YEARS` saisons avant, sans période qui couvre la saison. C'est la signature d'un homonyme : la page du club
    lie un autre joueur du même nom (ex. Fran González, gardien né en 2005 au Real Madrid, lié au Fran de 1969 du Deportivo).
    Rend (id de la ligne, joueur, club-saison, nom, année, saison, club, statut de la saison, année de naissance, fin de carrière)."""
    return con.execute(_IMPLAUSIBLE_STAYS).fetchall()


def split_implausible_stays(con: duckdb.DuckDBPyConnection) -> ReconcileReport:
    """Détache ces lignes du faux homonyme et les rend à un joueur SANS lien du même nom (identité faible) ; les étapes
    `reconcile --names/--wikidata/--infobox` l'identifient ensuite, preuve de carrière à l'appui, ou le laissent sans identité.
    Idempotent : un joueur sans lien n'a ni carrière ni naissance, donc plus rien à détacher. `merged` = lignes déplacées."""
    report = ReconcileReport()
    for row_id, pid, csid, name, year, label, club, status, *_ in implausible_stays(con):
        if status == "frozen":
            report.blocked.append(f"{name} ({club} {label}) : saison figée")
            continue
        loose = con.execute("SELECT id FROM player WHERE name = ? AND link_title IS NULL", [name]).fetchone()
        if loose is None:
            new_id = con.execute("SELECT coalesce(max(id), 0) + 1 FROM player").fetchone()[0]
            con.execute("INSERT INTO player (id, name) VALUES (?, ?)", [new_id, name])
            loose = (new_id,)
        con.execute("INSERT INTO squad_row_source SELECT club_season_id, ?, source_lang FROM squad_row_source "
                    "WHERE club_season_id = ? AND player_id = ? ON CONFLICT DO NOTHING", [loose[0], csid, pid])
        con.execute("INSERT INTO squad_movement SELECT club_season_id, ?, direction, kind, moved_on, transfer_window, other_club, "
                    "other_club_link, mid_season, source_title FROM squad_movement "
                    "WHERE club_season_id = ? AND player_id = ? ON CONFLICT DO NOTHING", [loose[0], csid, pid])
        con.execute("DELETE FROM squad_row_source WHERE club_season_id = ? AND player_id = ?", [csid, pid])
        con.execute("DELETE FROM squad_movement WHERE club_season_id = ? AND player_id = ?", [csid, pid])
        if con.execute("SELECT count(*) FROM player_club_season WHERE player_id = ? AND club_season_id = ?",
                       [loose[0], csid]).fetchone()[0]:
            con.execute("DELETE FROM player_club_season WHERE id = ?", [row_id])          # le joueur sans lien y figure déjà
        else:
            con.execute("UPDATE player_club_season SET player_id = ? WHERE id = ?", [loose[0], row_id])
        report.merged += 1
    return report


def _attach_qid(con, pid: int, qid: str, report: ReconcileReport) -> None:
    """Donne ce QID à ce joueur, ou le fusionne dans le joueur qui l'a déjà (refusé si une saison figée est touchée)."""
    owner = con.execute("SELECT player_id FROM player_wikidata WHERE qid = ?", [qid]).fetchone()
    if owner is None:
        con.execute("INSERT INTO player_wikidata VALUES (?, ?)", [pid, qid])
        report.resolved += 1
    elif owner[0] != pid:
        if _frozen_rows(con, pid) or _frozen_rows(con, owner[0]):
            report.blocked.append(f"{qid}: fusion {pid}->{owner[0]} touche une saison figée")
            return
        _merge(con, owner[0], pid)
        report.merged += 1


_LANGS = ("en", "fr", "it", "es", "de")
_Q_FOOTBALLER = "Q937857"


def _sparql_candidates(names: list[str]) -> str:
    esc = lambda n: n.replace("\\", "\\\\").replace('"', '\\"')
    values = " ".join(f'"{esc(n)}"@{l}' for n in names for l in _LANGS)
    return ("SELECT ?p ?l ?club ?start ?end WHERE { VALUES ?l { " + values + " } "
            f"?p rdfs:label ?l ; wdt:P106 wd:{_Q_FOOTBALLER} . "
            "OPTIONAL { ?p p:P54 ?st . ?st ps:P54 ?club . OPTIONAL { ?st pq:P580 ?start } OPTIONAL { ?st pq:P582 ?end } } }")


def _qid(url: str) -> str:
    return url.rsplit("/", 1)[-1]


def _year(iso: str | None) -> int | None:
    return int(iso[:4]) if iso and iso[:4].lstrip("-").isdigit() else None


def reconcile_by_wikidata(con: duckdb.DuckDBPyConnection, wd, *, batch: int = 80, log=print) -> ReconcileReport:
    """Identifie les joueurs sans QID par Wikidata : un footballeur de MÊME NOM (libellé dans une des 5 langues) dont les
    clubs (P54) contiennent CHACUN des club-saisons où il figure chez nous (dates P54 respectées quand elles existent),
    et qui est le seul dans ce cas. Sinon le joueur reste non identifié : une identité faible vaut mieux qu'inventée."""
    report = ReconcileReport()
    loose = [(pid, name) for pid, name in con.execute(
        "SELECT p.id, p.name FROM player p LEFT JOIN player_wikidata w ON w.player_id = p.id "
        "WHERE w.player_id IS NULL AND EXISTS (SELECT 1 FROM player_club_season x WHERE x.player_id = p.id) ORDER BY p.id").fetchall()
        if not re.search(r"[{}\[\]|<>#]", name) and _norm(name)]
    stays: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for pid, club_qid, year in con.execute("""SELECT pcs.player_id, cl.wikidata_qid, s.start_year FROM player_club_season pcs
            JOIN club_season cs ON cs.id = pcs.club_season_id JOIN club cl ON cl.id = cs.club_id
            JOIN season s ON s.id = cs.season_id WHERE cl.wikidata_qid IS NOT NULL""").fetchall():
        stays[pid].append((club_qid, year))

    for i in range(0, len(loose), batch):
        chunk = loose[i:i + batch]
        rows = wd.query(_sparql_candidates(sorted({n for _, n in chunk})))
        by_label: dict[str, dict[str, list[tuple[str, int | None, int | None]]]] = defaultdict(lambda: defaultdict(list))
        for r in rows:                                          # nom normalisé -> candidat -> [(club, début, fin)]
            cand = by_label[_norm(r["l"])][_qid(r["p"])]
            if r.get("club"):
                cand.append((_qid(r["club"]), _year(r.get("start")), _year(r.get("end"))))
        for pid, name in chunk:
            need = stays.get(pid)
            if not need:
                continue
            proven = []
            for cand_qid, spells in by_label.get(_norm(name), {}).items():
                ok = all(any(c == club and (s is None or s <= y + 1) and (e is None or e >= y) for c, s, e in spells)
                         for club, y in need)
                if ok:
                    proven.append(cand_qid)
            if len(proven) == 1:
                _attach_qid(con, pid, proven[0], report)
            else:
                report.unresolved += 1
        log(f"  {min(i + batch, len(loose))}/{len(loose)} joueurs (Wikidata) : {report.resolved + report.merged} identifiés")
    return report


def _name_matches(player_name: str, title: str) -> bool:
    """Le titre de la page (sans « (footballer, born …) ») et le nom du joueur partagent leurs mots, dans un sens ou l'autre."""
    a = set(_norm(player_name).split())
    b = set(_norm(re.sub(r"\s*\(.*\)\s*$", "", title)).split())
    return bool(a and b) and (a <= b or b <= a)


def reconcile_by_infobox(con: duckdb.DuckDBPyConnection, pages, search, qids, *, batch: int = 50,
                         since: int | None = None, direct_only: bool = False, log=print) -> ReconcileReport:
    """Retrouve la page anglaise des joueurs sans lien (pages fr/it/es sans liens) en lisant leur infobox.

    `pages(titles) -> [Page]` lit l'introduction (cache) ; `search(name) -> [titres]` interroge la recherche
    Wikipedia ; `qids(titres) -> {titre: QID}` résout les titres retenus. Un candidat n'est retenu que si (1) son titre ressemble au nom, (2) il a une infobox de carrière
    qui contient CHACUN des club-saisons où le joueur figure chez nous, (3) il est le seul dans ce cas.
    Sinon le joueur reste sans lien : une identité faible vaut mieux qu'une identité inventée."""
    from openfootball.parse.infobox import parse_career          # import local : évite un cycle au chargement

    report = ReconcileReport()
    loose = [(pid, name) for pid, name in con.execute(
        "SELECT p.id, p.name FROM player p LEFT JOIN player_wikidata w ON w.player_id = p.id "
        "WHERE w.player_id IS NULL AND (p.link_title IS NULL) ORDER BY p.id").fetchall()
        if not re.search(r"[{}\[\]|<>#]", name)]                  # un nom qui contient du code wiki n'est pas un titre de page
    if since is not None:                                           # seulement les joueurs d'un effectif depuis cette saison (les plus utiles, et la recherche est lente)
        recent = {r[0] for r in con.execute("""SELECT DISTINCT pcs.player_id FROM player_club_season pcs JOIN club_season cs ON cs.id = pcs.club_season_id
                                               JOIN season s ON s.id = cs.season_id WHERE pcs.stint <> 'loan_out' AND s.start_year >= ?""", [since]).fetchall()}
        loose = [(pid, name) for pid, name in loose if pid in recent]
    link_qid = _club_qids_by_link(con)
    stays: dict[int, list[tuple]] = defaultdict(list)
    for pid, club, year, club_qid in con.execute("""SELECT pcs.player_id, cl.wikipedia_title, s.start_year, cl.wikidata_qid FROM player_club_season pcs
            JOIN club_season cs ON cs.id = pcs.club_season_id JOIN club cl ON cl.id = cs.club_id
            JOIN season s ON s.id = cs.season_id""").fetchall():
        stays[pid].append((club, year, club_qid))

    def proven(pid: int, name: str, titles: list[str]) -> list[str]:
        titles = [t for t in dict.fromkeys(titles) if _name_matches(name, t)]
        out = []
        for page in (pages(titles) if titles else []):
            if not page.exists:
                continue
            spells = [(s.club_link, s.club_name, s.start_year, s.end_year) for s in parse_career(page.wikitext or "")]
            if spells and _stays_proven(spells, stays[pid], link_qid):
                out.append(page.resolved_title or page.title)
        return list(dict.fromkeys(out))

    matched: list[tuple[int, str]] = []

    def flush() -> None:
        """Enregistre les identifications en attente : une interruption ne perd que le lot en cours."""
        if not matched:
            return
        titles = sorted({t for _, t in matched})
        found_qids: dict[str, str | None] = {}
        for i in range(0, len(titles), 50):
            found_qids.update(qids(titles[i:i + 50]))
        for pid, title in matched:
            qid = found_qids.get(title)
            if not qid:
                report.unresolved += 1
                continue
            owner = con.execute("SELECT player_id FROM player_wikidata WHERE qid = ?", [qid]).fetchone()
            if owner is None:
                con.execute("INSERT INTO player_wikidata VALUES (?, ?)", [pid, qid])
                report.resolved += 1
            elif owner[0] != pid:
                if _frozen_rows(con, pid) or _frozen_rows(con, owner[0]):
                    report.blocked.append(f"{qid}: fusion {pid}->{owner[0]} touche une saison figée")
                    continue
                _merge(con, owner[0], pid)
                report.merged += 1
        matched.clear()

    def warm(titles: list[str]) -> None:
        """Lit d'un coup les pages de tout un lot (le client les met en cache) : un appel pour 50 joueurs, pas un par joueur."""
        try:
            pages(list(dict.fromkeys(titles)))
        except Exception as exc:                                # une page illisible ne doit pas arrêter tout le lot
            log(f"  lecture groupée impossible ({exc}); reprise joueur par joueur")

    def disambiguation_candidates(name: str) -> list[str]:
        """Page d'homonymie (« Abdoulaye Cissé may refer to: … ») : les titres des footballeurs qu'elle liste. Lues en lot avec le titre direct, donc sans requête de plus."""
        for page in pages([name]):
            text = page.wikitext or ""
            if page.exists and re.search(r"may refer to|\{\{\s*(disambig|dab|hndis|given name|surname)", text, re.I):
                return [m.group(1).strip() for line in text.splitlines() if re.search(r"footbal|soccer", line, re.I)
                        for m in re.finditer(r"\[\[([^\]|#]+)", line)]
        return []

    def titles_of(name: str) -> list[str]:
        """Le nom comme titre, puis ses deux qualifications usuelles : « Nom (footballer) » et « Nom (soccer) » (joueurs américains), lues en lot."""
        return [name, f"{name} (footballer)", f"{name} (soccer)"]

    remaining = []
    for i in range(0, len(loose), batch):                      # 1) le nom comme titre (redirections comprises), puis ses titres qualifiés
        warm([t for _, name in loose[i:i + batch] for t in titles_of(name)])
        for pid, name in loose[i:i + batch]:
            found = proven(pid, name, titles_of(name))
            if not found:
                candidates = disambiguation_candidates(name)       # le nom mène à une page d'homonymie : on essaie ses footballeurs
                found = proven(pid, name, candidates) if candidates else []
            if len(found) == 1:
                matched.append((pid, found[0]))
            else:
                remaining.append((pid, name))
        flush()
        log(f"  {min(i + batch, len(loose))}/{len(loose)} joueurs (titre direct) : {report.resolved + report.merged} identifiés")
    GROUP = 25
    if direct_only:                                            # sans la recherche (une requête par joueur, la partie lente)
        report.unresolved += len(remaining)
        remaining = []
    for g in range(0, len(remaining), GROUP):                  # 2) recherche, pour ceux dont le titre est qualifié
        group = remaining[g:g + GROUP]
        found_titles = {pid: [t for t in dict.fromkeys(search(name)) if _name_matches(name, t)] for pid, name in group}
        warm([t for ts in found_titles.values() for t in ts])
        for pid, name in group:
            found = proven(pid, name, found_titles[pid])
            if len(found) == 1:
                matched.append((pid, found[0]))
            else:
                report.unresolved += 1
        flush()
        log(f"  {min(g + GROUP, len(remaining))}/{len(remaining)} joueurs (recherche) : {report.resolved + report.merged} identifiés")
    flush()
    return report

