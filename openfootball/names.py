"""Comparaison de noms : minuscules, sans accents, lettres spéciales ramenées à leur équivalent ASCII.

`NFD` seul ne décompose pas « ı » (i sans point), « ø », « đ », « ł », « ß »… : « Altıntop » (it) et « Altintop » (fr)
n'étaient donc pas reconnus comme le même joueur."""
from __future__ import annotations

import re
import unicodedata

_SPECIAL = str.maketrans({"ı": "i", "İ": "i", "ø": "o", "Ø": "o", "đ": "d", "Đ": "d", "ð": "d", "Ð": "d", "ł": "l",
                          "Ł": "l", "ß": "ss", "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe", "þ": "th", "Þ": "th"})


_SUFFIX = re.compile(r"\b(jr|sr)\b")


def fold(text: str) -> str:
    """« Vinícius Jr. » (fr) et « Vinícius Júnior » (es) : `jr` / `sr` valent `junior` / `senior`."""
    t = unicodedata.normalize("NFD", text.translate(_SPECIAL).lower()).encode("ascii", "ignore").decode()
    return _SUFFIX.sub(lambda m: "junior" if m.group(1) == "jr" else "senior", t)


def full_name(shown: str, target: str | None) -> str:
    """Nom à afficher d'un joueur dont le lien est `[[Hugo Lloris|Lloris]]` : le titre de la page (sans « (footballeur, né en 1986) »)
    quand le nom écrit en est la FIN (le nom de famille : « Lloris », « Kanté »). Un surnom ou un prénom (« Jean » pour Jean Paulo Fernandes Filho, « Gabriel », « Rodri », « Vini Jr. ») reste tel quel."""
    if not target:
        return shown
    title = re.sub(r"\s*\([^)]*\)\s*$", "", target).strip()
    sw, tw = fold(shown).split(), fold(title).split()
    return title if sw and len(tw) > len(sw) and tw[-len(sw):] == sw else shown


# --------------------------------------------------------------------------------------------------
# Nom affichable d'un joueur : les restes de wikicode et les annotations de tableau ne font pas partie du nom.

_HTML = re.compile(r"<[^>]+>")
_FOOTNOTE = re.compile(r"(?:note\s*\d+\s*\]|\[\s*(?:note\s*)?\d+\s*\])\s*$", re.I)         # `Ibrahim Fofananote 2]` : renvoi de note collé au nom
_PAREN = re.compile(r"\s*\([^()]*\)")                                                        # (U18), (*), (c), (on loan), (footballer, born 1989), (calciatore)
_NICK_AFTER_COMMA = re.compile(r',\s*["“”«»][^"“”«»]*["“”«»]\s*$')                           # `Mario Jiménez, "Gambín"`
_NICK_QUOTED = re.compile(r'^["“«]([^"“”«»]+)["”»]\s+(.+)$')                                  # `"Dani" Mas` -> `Dani Mas`
_SURNAME_FIRST = re.compile(r"^([A-ZÀ-ÝŁŚŹŻ][A-ZÀ-ÝŁŚŹŻ'’\- ]{1,}),\s+(\S.*)$")              # `GARCÍA, Eduardo` -> `Eduardo García`
_TRAILING_MARK = re.compile(r"[\s†‡*•]+$")
_RESERVE_B = re.compile(r"^(.+\S\s+\S.*?)\s+B$")                                              # `Aziz Deen-Conteh B` : équipe B, pas un patronyme


def clean_person_name(name: str) -> str:
    """Le nom d'un joueur sans ce que le wikicode y a laissé : balises, renvois de note, `(U18)`, `†`, `}}`, italique, surnom entre guillemets, « NOM, Prénom »…
    Rend le nom d'origine si le nettoyage ne laisserait rien."""
    n = _HTML.sub(" ", name or "").split("|")[0]                                            # `Patrick Lane|Patrick Lane` : le texte puis son doublon de lien
    n = re.sub(r"'{2,}", "", n)
    n = _FOOTNOTE.sub("", n)
    n = re.sub(r"[\]\}]+$|\{\{.*$", "", n)
    n = _PAREN.sub("", n)
    n = _NICK_AFTER_COMMA.sub("", n)
    n = _TRAILING_MARK.sub("", n.strip())
    if (m := _NICK_QUOTED.match(n)):
        n = f"{m.group(1)} {m.group(2)}"
    n = re.sub(r'\s*["“«][^"“”«»]+["”»]', "", n)                                            # `Antonio Rodríguez "Toño"`, `Victor "PC" Giro` : le surnom n'est pas dans le nom
    n = re.sub(r"\s*\[[^\]]*$", "", n)                                                       # `Rafhinha [L` : marqueur de prêt ou de note resté ouvert
    n = re.sub(r"(?<=[a-zà-ÿ])U\d{2}$", "", n)                                              # `Iman AbaszadehU21` : catégorie collée au nom
    if len(n) > 2 and n[0] == n[-1] == "'":
        n = n[1:-1]
    if (m := _SURNAME_FIRST.match(n)):
        n = f"{m.group(2)} {m.group(1).title()}"
    n = re.sub(r"^[^\w\"“«'‘]+", "", n)
    if (m := _RESERVE_B.match(n)):
        n = m.group(1)
    n = re.sub(r"\s+", " ", n).strip(" ,;:|")
    return n if re.search(r"[^\W\d_]", n) else (name or "")


def name_tokens(name: str) -> list[str]:
    return re.sub(r"[^a-z]+", " ", fold(name)).split()


def same_name_variant(a: str, b: str) -> str | None:
    """Les deux noms désignent-ils vraisemblablement la même personne ?
    `"same"` : mêmes mots à l'ordre et aux accents près (« Filip Šimeček » / « Filip Simecek ») ;
    `"close"` : écrits presque pareil (translittération, faute de frappe : « Matvey » / « Matveï » Safonov), même initiale de prénom et de nom ;
    `None` sinon. « close » ne suffit pas seul : l'appelant exige une autre preuve (même numéro dans le même effectif)."""
    from difflib import SequenceMatcher
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return None
    if sorted(ta) == sorted(tb):
        return "same"
    if ta[0][0] == tb[0][0] and ta[-1][0] == tb[-1][0] and SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio() >= 0.85:
        return "close"
    return None
