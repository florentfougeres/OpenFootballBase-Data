# OpenFootballBase — dictionnaire de données

Effectifs de clubs de football par saison, construits **uniquement** à partir de Wikipedia (CC BY-SA 4.0) et Wikidata (CC0).
Ce fichier décrit les fichiers Parquet de cette release ; il est généré à l'export, à partir des fichiers eux-mêmes.
[English version: `SCHEMA.md`](../en/data-model.md).

## Organisation de la release

- `manifest.json` — **point d'entrée** : date, version du schéma, et pour chaque fichier son chemin, son nombre de lignes et son empreinte SHA-256.
- Un fichier **par saison** pour `squad` et `club_season` ; un fichier par table pour les autres.
- Les noms de fichiers contiennent les 8 premiers caractères de leur empreinte : `squad/2025-26.8fdfe5a8.parquet`. Un fichier dont le contenu ne change pas garde son nom (cache navigateur, comparaison entre releases).
- Les saisons `frozen` sont immuables ; la saison `open` (en cours) change à chaque release.

```json
{ "format": 1, "schema_version": 9, "generated_at": "…",
  "seasons": { "2025/26": { "status": "…", "content_hash": null,
      "coverage": { "club_seasons": 96, "with_squad": 96, "known_gaps": 0 },
      "files": { "squad": { "path": "squad/…parquet", "rows": 2956, "sha256": "…" },
                 "club_season": { "path": "club_season/…parquet", "rows": 96, "sha256": "…" } } } },
  "tables": { "club": { "path": "club/…parquet", "rows": 42857, "sha256": "…" } } }
```

## Lire les données

```sql
-- DuckDB : tous les effectifs, toutes saisons (les fichiers n'ont pas le même nom : motif *)
SELECT * FROM read_parquet('squad/*.parquet', union_by_name = true) WHERE club = 'Olympique de Marseille';
```

## Schéma relationnel (clés de jointure)

```
country.code ──< competition.country_code
competition.code ──< squad.competition, club_season.competition
club.wikipedia_title ──< squad.club, club_season.club        (club.has_squads = vrai)
club.wikidata_qid ──< career.club_qid
season.label ──< squad.season, club_season.season, known_gap.season
squad.player_qid ──< career.player_qid, national.player_qid, birth.player_qid
(club|player QID) ──< entity_wiki.qid
```

**Identité d'un joueur** : son QID Wikidata (`player_qid`). Quand il est vide (joueur non identifié), la clé de repli est
`'name:' || player` ; deux homonymes non identifiés ne sont alors pas distinguables.

## Ce qu'il faut savoir avant d'utiliser les données

- **Un effectif est l'union de plusieurs pages** : toutes les langues du pays sont lues et fusionnées (`squad_source`, `squad.listed_in`) pour être le plus complet possible ; un joueur peut venir d'une page plus ancienne ou plus récente que la principale.
- **Un effectif est un instantané** : la liste publiée sur la page Wikipedia à sa date de mise à jour, pas la liste de tous les joueurs de la saison. Un joueur arrivé ou parti en cours de saison peut manquer.
- **Mouvements en cours de saison** : `stint = arrived_mid / left_mid` (avec `stint_date`) lus dans les tableaux de transferts des pages **anglaises** ; les club-saisons dont la page anglaise n'a pas de tableau exploitable restent à `unknown`. Un joueur parti en cours de saison est dans l'effectif de son club d'origine (`left_mid`) et dans celui de son nouveau club (`arrived_mid`).
- **Les prêts** : un joueur prêté ailleurs (`loan_out`) n'est pas dans l'effectif de son club d'origine ; il est dans celui du club d'accueil (`stint = 'loan_in'`).
- **Carrière et sélections** (matchs, buts) : publiés tels quels depuis les infobox Wikipedia, **non vérifiés**, et ils peuvent différer d'une langue à l'autre.
- **Trous** : les effectifs introuvables sont listés dans `known_gap` ; les autres club-saisons sans effectif ne sont pas encore examinés (`club_season.players = 0` sans motif).
- **Alphabets** : les noms de stade, de championnat et de ville en alphabet non latin sont remplacés par leur libellé anglais Wikidata (vide s'il n'existe pas).
- **Logos** : images hébergées par Wikimedia, souvent non libres ; à utiliser à titre d'illustration.
- **Âges** : à calculer à partir de `birth` seulement si `precision = 11`.
- Licences : texte Wikipedia CC BY-SA 4.0 (attribution : la page source est donnée par `source_title` / `source_revid`), Wikidata CC0.


## Tables

### `squad`

Effectif d'un club pour une saison : **une ligne = un joueur dans l'effectif d'un club cette saison**. Un fichier par saison (`squad/<saison>.<sha8>.parquet`). Les joueurs prêtés ailleurs (`loan_out`) n'y figurent pas.

- Fichiers : 27 fichiers (un par saison), ex. `squad/2026-27.03e74a93.parquet` — **300 390 lignes**
- Clé : (season, club, player_qid ou player)

| Colonne | Type | Description |
|---|---|---|
| `season` | VARCHAR | Saison, au format `2025/26` (= `season.label`). |
| `competition` | VARCHAR | Code du championnat, ex. `FRA-L1` (= `competition.code`). |
| `club` | VARCHAR | Titre de la page Wikipedia anglaise du club (= `club.wikipedia_title`). |
| `player` | VARCHAR | Nom du joueur tel que publié sur la page source. |
| `player_qid` | VARCHAR | QID Wikidata du joueur. **Vide si le joueur n'a pas pu être identifié** : son identité est alors son nom seul (clé de repli : `'name:' || player`). |
| `link_lang` | VARCHAR | Langue de la page Wikipedia du joueur citée sur la page source (`en`, `it`…). Vide pour les pages sans liens (fr, es). |
| `link_title` | VARCHAR | Titre de cette page Wikipedia du joueur. |
| `shirt_number` | INTEGER | Numéro de maillot (0 à 99). Vide si absent de la source. |
| `position` | VARCHAR | Poste : `GK` gardien, `DF` défenseur, `MF` milieu, `FW` attaquant. Vide si non précisé. |
| `nationality` | VARCHAR | Nationalité telle que publiée (texte libre, dans la langue de la page : `France`, `España`, `IRL`…). |
| `nat_flag` | VARCHAR | Code de drapeau (flag-icons : `fr`, `gb-eng`, `ie`…) déduit de la nationalité ; vide si non reconnue. |
| `stint` | VARCHAR | Statut dans le club : `unknown` (rien de précis), `arrived_mid` (arrivé en cours de saison), `left_mid` (parti en cours de saison : il a joué au club avant), `loan_in` (prêté **à** ce club). Les prêtés partis ailleurs (`loan_out`) ne sont pas exportés. Les mouvements viennent des tableaux « Transfers » des pages anglaises. |
| `confidence` | VARCHAR | Niveau de preuve : `attested` = cité dans l'effectif publié sur la page source. |
| `source` | VARCHAR | Origine de la ligne : `wikipedia_season` (page « saison du club »). |
| `source_section` | VARCHAR | Titre de la section ou du tableau de la page où le joueur a été lu. |
| `listed_in` | VARCHAR | Langues des pages qui listent ce joueur, par priorité (`fr,it` : cité par la page française et par l'italienne). Un joueur cité par plusieurs pages est mieux attesté. |
| `stint_date` | VARCHAR | Date du mouvement (`YYYY-MM-DD`) pour `arrived_mid`, `left_mid` ou un prêt ; vide si la page ne donne pas la date. |
| `stint_window` | VARCHAR | Fenêtre de transferts (`winter`, `summer`) quand la page la dit sans date exacte. |
| `stint_other_club` | VARCHAR | Club d'où il vient (`arrived_mid`, `loan_in`) ou où il va (`left_mid`), tel qu'écrit sur la page. |
| `source_lang` | VARCHAR | Langue de la page source **principale** de l'effectif (`en`, `fr`, `it`, `es`) : celle du pays d'abord. |
| `source_title` | VARCHAR | Titre de cette page principale. |
| `source_revid` | BIGINT | Numéro de révision Wikipedia lu (permet de retrouver la version exacte). |

### `club_season`

Une ligne = **un club dans un championnat pour une saison** (avec ou sans effectif). Un fichier par saison (`club_season/<saison>.<sha8>.parquet`).

- Fichiers : 27 fichiers (un par saison), ex. `club_season/2026-27.f1cd6e1f.parquet` — **26 674 lignes**
- Clé : (season, club)

| Colonne | Type | Description |
|---|---|---|
| `season` | VARCHAR | Saison, `2025/26`. |
| `competition` | VARCHAR | Code du championnat (`competition.code`). |
| `club` | VARCHAR | Titre de la page Wikipedia anglaise du club (`club.wikipedia_title`). |
| `source_lang` | VARCHAR | Langue de la page **principale** dont l'effectif a été lu ; vide si aucun effectif n'a pu être établi. Les autres pages utilisées sont dans `squad_source`. |
| `source_title` | VARCHAR | Titre de cette page principale. |
| `source_revid` | BIGINT | Révision Wikipedia lue. |
| `players` | BIGINT | Nombre de joueurs dans `squad` pour ce club et cette saison (0 = pas d'effectif). |
| `known_gap_reason` | VARCHAR | Si l'effectif manque et que ce trou a été validé à la main : le motif. Sinon vide. |

### `squad_source`

Les pages « saison du club » dont l'effectif est l'**union** : un effectif est lu sur toutes les langues du pays (langue du pays d'abord, puis anglais, italien…) pour être le plus complet possible. **Une ligne = une page utilisée.**

- Fichiers : `squad_source/squad_source.d3a0cd20.parquet` — **13 125 lignes**
- Clé : (season, club, source_lang)

| Colonne | Type | Description |
|---|---|---|
| `season` | VARCHAR | Saison, `2025/26`. |
| `competition` | VARCHAR | Code du championnat. |
| `club` | VARCHAR | Titre de la page Wikipedia du club. |
| `rank` | INTEGER | Priorité de la source : 1 = source principale (celle de `club_season.source_*`). |
| `source_lang` | VARCHAR | Langue de la page. |
| `source_title` | VARCHAR | Titre de la page. |
| `source_revid` | BIGINT | Révision Wikipedia lue. |
| `players_read` | INTEGER | Joueurs de l'effectif principal lus sur cette page (et retrouvés dans l'effectif fusionné). |
| `players_added` | INTEGER | Joueurs que cette page apporte et qu'aucune source de rang inférieur n'avait. |

### `club`

Tous les clubs de football connus (≈ 43 000, source : Wikidata). `has_squads` distingue les clubs dont on a les effectifs.

- Fichiers : `club/club.8985c057.parquet` — **44 983 lignes**
- Clé : wikidata_qid (wikipedia_title est aussi unique quand il existe)

| Colonne | Type | Description |
|---|---|---|
| `wikidata_qid` | VARCHAR | Identifiant Wikidata du club (ex. `Q483020`). |
| `wikipedia_title` | VARCHAR | Titre de la page Wikipedia anglaise ; vide si le club n'en a pas. |
| `name_en` | VARCHAR | Nom anglais (libellé Wikidata). |
| `name_fr` | VARCHAR | Nom français (libellé Wikidata). |
| `name_local` | VARCHAR | Nom dans la langue du club ; remplacé par le nom anglais s'il est en alphabet non latin. |
| `nickname` | VARCHAR | Surnom ; masqué s'il est en alphabet non latin. |
| `category` | VARCHAR | Catégorie Wikidata (masculin, féminin, jeunes…). |
| `country_code` | VARCHAR | Code pays interne (`ENG`, `FRA`, `ITA`, `ESP`, `DEU`) — **seulement pour les clubs à effectifs** (= `country.code`). |
| `country_iso` | VARCHAR | Code pays ISO 3166-1 alpha-2, en majuscules (`FR`). |
| `country` | VARCHAR | Nom du pays tel que publié par Wikidata. |
| `city` | VARCHAR | Ville ; libellé anglais si le nom publié est en alphabet non latin, vide s'il n'existe pas. |
| `stadium` | VARCHAR | Stade ; même règle que `city`. |
| `stadium_capacity` | INTEGER | Capacité du stade (places). |
| `division` | INTEGER | Niveau actuel dans la pyramide (1 = élite). |
| `league` | VARCHAR | Championnat actuel ; même règle que `city`. |
| `founded` | VARCHAR | Date de fondation : date ISO complète ou année seule, telle que publiée. |
| `colors` | VARCHAR | Noms des couleurs, séparés par ` | `. |
| `colors_hex` | VARCHAR | Couleurs en hexadécimal (`#0B61AC`), séparées par ` | ` (même ordre que `colors`). |
| `website` | VARCHAR | Site officiel. |
| `logo_url` | VARCHAR | Miniature du logo lue dans l'infobox de la page Wikipedia anglaise (hébergée par Wikimedia). Beaucoup sont **non libres** (usage loyal) : voir `logo_license`. |
| `logo_license` | VARCHAR | Licence du fichier logo (`CC BY-SA`, `Public domain`, `non-free`…). |
| `logo_commons_url` | VARCHAR | Logo libre sur Wikimedia Commons, utilisé en repli. |
| `wikipedia_en_url` | VARCHAR | URL de la page Wikipedia anglaise. |
| `wikipedia_local_url` | VARCHAR | URL de la page Wikipedia dans la langue du club. |
| `wikipedia_count` | INTEGER | Nombre de versions linguistiques de la page Wikipedia : indicateur de notoriété. |
| `lon` | DOUBLE | Longitude (WGS 84). |
| `lat` | DOUBLE | Latitude (WGS 84). |
| `transfermarkt_id` | VARCHAR | Identifiant du club chez Transfermarkt (lien seulement : aucune donnée Transfermarkt n'est utilisée). |
| `fbref_id` | VARCHAR | Identifiant FBref (lien seulement). |
| `worldfootball_id` | VARCHAR | Identifiant WorldFootball (lien seulement). |
| `has_squads` | BOOLEAN | Vrai si le club a au moins un effectif dans `club_season`. |

### `competition`

Les compétitions couvertes : championnats du périmètre, championnats partiels de pays hors périmètre, et coupes d'Europe (`UEFA-CL`).

- Fichiers : `competition/competition.aa65a820.parquet` — **152 lignes**
- Clé : code

| Colonne | Type | Description |
|---|---|---|
| `code` | VARCHAR | Code du championnat : `<PAYS>-<ABRÉVIATION>`, ex. `FRA-L1`. |
| `name_en` | VARCHAR | Nom anglais. |
| `name_fr` | VARCHAR | Nom français. |
| `country_code` | VARCHAR | Pays du championnat (`country.code`). |
| `level` | INTEGER | Niveau dans la pyramide (1 = première division). 5 : coupe nationale ou supercoupe (aucun club ni effectif par saison, seulement un palmarès). |
| `wikidata_qid` | VARCHAR | QID Wikidata du championnat, s'il est renseigné. |
| `wikipedia_title` | VARCHAR | Titre de la page Wikipedia anglaise du championnat. |
| `logo_url` | VARCHAR | Miniature du logo du championnat lue dans l'infobox de sa page Wikipedia (hébergée par Wikimedia). Souvent **non libre** : voir `logo_license`. |
| `logo_license` | VARCHAR | Licence du fichier logo (`Public domain`, `Fair use`…). |

### `country`

Les pays couverts par `competition`.

- Fichiers : `country/country.c2d43633.parquet` — **116 lignes**
- Clé : code

| Colonne | Type | Description |
|---|---|---|
| `code` | VARCHAR | Code interne à 3 lettres (`FRA`, `ENG`…). |
| `name_en` | VARCHAR | Nom anglais. |
| `name_fr` | VARCHAR | Nom français. |
| `flag` | VARCHAR | Code de drapeau flag-icons (`fr`, `gb-eng`). |

### `season`

Les saisons présentes et leur état.

- Fichiers : `season/season.a28d16c4.parquet` — **27 lignes**
- Clé : label

| Colonne | Type | Description |
|---|---|---|
| `label` | VARCHAR | Saison, `2025/26`. |
| `start_year` | INTEGER | Année de début (2025 pour 2025/26). |
| `status` | VARCHAR | `open` = saison en cours (peut changer à chaque release), `backfill` = terminée mais pas figée, `frozen` = figée (immuable). |
| `content_hash` | VARCHAR | Empreinte du contenu, renseignée seulement pour une saison figée : `verify-release` refuse toute release qui la modifie. |

### `competition_club`

Clubs participant à une compétition, par saison : les clubs du championnat (d'après `club_season`) **et** ceux qui y participent en plus de leur championnat (Ligue des champions, table `competition_entry`).

- Fichiers : `competition_club/competition_club.5eb08a4e.parquet` — **30 184 lignes**
- Clé : (season, competition, club)

| Colonne | Type | Description |
|---|---|---|
| `season` | VARCHAR | Saison, `2025/26`. |
| `competition` | VARCHAR | Code de la compétition (`UEFA-CL`, `ENG-PL`…), clé de `competition.code`. |
| `club` | VARCHAR | Titre de la page Wikipedia du club, clé de `club.wikipedia_title`. |

### `known_gap`

Effectifs introuvables dont l'absence a été **validée explicitement** (la source n'existe pas).

- Fichiers : `known_gap/known_gap.2e22296a.parquet` — **1 006 lignes**
- Clé : (season, club)

| Colonne | Type | Description |
|---|---|---|
| `season` | VARCHAR | Saison, `2012/13`. |
| `club` | VARCHAR | Titre de la page Wikipedia du club. |
| `reason` | VARCHAR | Motif du trou (ex. « page absente »). |

### `career`

Carrière senior d'un joueur, lue dans l'infobox de sa page Wikipedia **anglaise** : **une ligne = un passage dans un club**.

- Fichiers : `career/career.12be0dfc.parquet` — **485 765 lignes**
- Clé : (player_qid ou player, seq)

| Colonne | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | QID Wikidata du joueur (clé de jointure avec `squad.player_qid`). |
| `player` | VARCHAR | Nom du joueur (repli de clé : `'name:' || player` quand `player_qid` est vide). |
| `seq` | INTEGER | Rang du passage dans l'infobox (1, 2, 3…). |
| `start_year` | INTEGER | Année de début du passage. |
| `end_year` | INTEGER | Année de fin ; **vide = en cours ou inconnue**. |
| `years_raw` | VARCHAR | Années telles que publiées (`2015–2021`). |
| `club_name` | VARCHAR | Nom du club tel que publié dans l'infobox. |
| `club_link` | VARCHAR | Titre de la page Wikipedia du club cité (peut être une redirection). |
| `club_qid` | VARCHAR | QID Wikidata du club, résolu à partir de `club_link` (= `club.wikidata_qid`) ; vide si introuvable. |
| `loan` | BOOLEAN | Vrai si le passage est un prêt (flèche `→` ou `(loan)` dans l'infobox). |
| `apps` | INTEGER | Matchs, **tels que publiés par Wikipedia, non vérifiés**. |
| `goals` | INTEGER | Buts, **tels que publiés par Wikipedia, non vérifiés**. |
| `source_lang` | VARCHAR | Langue de la page lue (toujours `en`). |
| `source_title` | VARCHAR | Titre de la page du joueur. |
| `source_revid` | BIGINT | Révision Wikipedia lue. |

### `national`

Sélections en équipe nationale (jeunes comprises), lues dans l'infobox : **une ligne = une équipe**.

- Fichiers : `national/national.481fd655.parquet` — **90 838 lignes**
- Clé : (player_qid ou player, seq)

| Colonne | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | QID Wikidata du joueur. |
| `player` | VARCHAR | Nom du joueur. |
| `seq` | INTEGER | Rang dans l'infobox. |
| `years_raw` | VARCHAR | Années telles que publiées. |
| `team_name` | VARCHAR | Équipe : `France`, `France U21`… |
| `team_link` | VARCHAR | Titre de la page Wikipedia de l'équipe. |
| `caps` | INTEGER | Sélections, **telles que publiées, non vérifiées**. |
| `goals` | INTEGER | Buts en sélection, **tels que publiés, non vérifiés**. |

### `stat_club`

Statistiques de carrière **par club, saison et compétition**, lues dans la section « Career statistics » de la page Wikipedia anglaise du joueur (joueurs de clubs de Ligue des champions des 7 grands pays, depuis 2010). **Une ligne = un club, une saison, un groupe de compétition.** Valeurs **publiées telles quelles, non vérifiées** ; une cellule vide ou « — » est vide, pas zéro.

- Fichiers : `stat_club/stat_club.610725e7.parquet` — **911 539 lignes**
- Clé : (player_qid ou player, seq)

| Colonne | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | QID Wikidata du joueur. |
| `player` | VARCHAR | Nom du joueur (repli de clé : `'name:' || player`). |
| `seq` | INTEGER | Rang dans le tableau. |
| `club` | VARCHAR | Club, tel qu'écrit. |
| `club_link` | VARCHAR | Titre de la page Wikipedia du club. |
| `club_qid` | VARCHAR | QID Wikidata du club, quand il est connu. |
| `season` | VARCHAR | Saison `2008–09`, ou l'année seule (`2022`) pour un championnat sur l'année civile. |
| `division` | VARCHAR | Division, telle qu'écrite. |
| `competition_group` | VARCHAR | Groupe de compétition : `League`, `National cup`, `League cup`, `Continental` (ou `Europe`), `Other`. |
| `apps` | INTEGER | Matchs joués. |
| `goals` | INTEGER | Buts. |
| `assists` | INTEGER | Passes décisives, quand la page les donne. |

### `stat_national`

Statistiques en sélection **par équipe nationale et année**, lues dans la section « Career statistics » (même périmètre que `stat_club`). Valeurs **publiées telles quelles, non vérifiées**.

- Fichiers : `stat_national/stat_national.80662b6d.parquet` — **49 677 lignes**
- Clé : (player_qid ou player, seq)

| Colonne | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | QID Wikidata du joueur. |
| `player` | VARCHAR | Nom du joueur. |
| `seq` | INTEGER | Rang dans le tableau. |
| `team` | VARCHAR | Équipe : `France`, `Portugal U21`… |
| `team_link` | VARCHAR | Titre de la page Wikipedia de l'équipe. |
| `year` | VARCHAR | Année (`2014`) ou période (`2014–15`). |
| `competition_group` | VARCHAR | `Competitive`, `Friendly`, ou `Total` quand la page ne distingue pas. |
| `apps` | INTEGER | Sélections. |
| `goals` | INTEGER | Buts en sélection. |

### `stat_source`

Provenance des statistiques : la page lue pour chaque joueur (une ligne par joueur lu, même sans tableau).

- Fichiers : `stat_source/stat_source.cb237ef7.parquet` — **49 417 lignes**
- Clé : (player_qid ou player)

| Colonne | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | QID Wikidata du joueur. |
| `player` | VARCHAR | Nom du joueur. |
| `source_title` | VARCHAR | Titre de la page Wikipedia anglaise lue. |
| `source_revid` | BIGINT | Révision lue. |
| `club_rows` | INTEGER | Lignes lues dans `stat_club`. |
| `national_rows` | INTEGER | Lignes lues dans `stat_national`. |

### `winner`

Palmarès : le vainqueur de chaque saison d'une compétition, d'après Wikidata (une ligne par vainqueur ; un co-vainqueur donne deux lignes).

- Fichiers : `winner/winner.152033d1.parquet` — **5 613 lignes**
- Clé : (competition, season_start, winner_qid)

| Colonne | Type | Description |
|---|---|---|
| `competition` | VARCHAR | Code de la compétition (`FRA-L1`, `UEFA-CL`…). |
| `season_start` | INTEGER | Année de début de la saison (`2003` pour 2003/04 ; l'année civile pour un championnat qui se joue sur l'année). |
| `winner_name` | VARCHAR | Libellé anglais Wikidata du vainqueur. |
| `winner_qid` | VARCHAR | QID Wikidata du vainqueur. |
| `club` | VARCHAR | Titre de la page Wikipedia du club dans `club`, quand le vainqueur y figure ; vide sinon. |
| `season_qid` | VARCHAR | QID Wikidata de la saison (la source de la ligne). |

### `award`

Classements de récompenses individuelles : une ligne par joueur classé d'une édition du Ballon d'Or (depuis 2000), d'après la page Wikipedia de l'édition.

- Fichiers : `award/award.e18a6e69.parquet` — **609 lignes**
- Clé : (award, year, rank, player_name)

| Colonne | Type | Description |
|---|---|---|
| `award` | VARCHAR | Récompense (`BALLON_DOR`). |
| `year` | INTEGER | Année de l'édition (de la cérémonie). |
| `rank` | INTEGER | Rang (1 = lauréat). Certaines éditions ne donnent que le podium. |
| `player_name` | VARCHAR | Nom du joueur. |
| `player_qid` | VARCHAR | QID Wikidata du joueur (clé de jointure avec `squad.player_qid`) ; vide si sa page n'a pas d'élément. |
| `club_name` | VARCHAR | Club au moment de l'édition, tel qu'écrit sur la page. |
| `club` | VARCHAR | Titre de la page Wikipedia du club dans `club`, quand il y figure ; vide sinon. |
| `points` | INTEGER | Points reçus ; vide quand la page ne les donne pas. |

### `national_title`

Titres en équipe nationale : pour chaque édition d'une compétition de sélections (Coupe du monde, Euro, Copa América, Coupe d'Afrique des nations, Coupe d'Asie, Gold Cup, Coupe des confédérations), la liste des joueurs de l'équipe victorieuse, d'après la page Wikipedia des effectifs de l'édition. Un joueur de la liste a pu ne pas jouer.

- Fichiers : `national_title/national_title.f8610ca9.parquet` — **2 975 lignes**
- Clé : (competition, year, player_name)

| Colonne | Type | Description |
|---|---|---|
| `competition` | VARCHAR | `WORLD_CUP`, `EURO`, `COPA_AMERICA`, `AFCON`, `ASIAN_CUP`, `GOLD_CUP` ou `CONFEDERATIONS_CUP`. |
| `year` | INTEGER | Année de l'édition. |
| `team` | VARCHAR | Sélection victorieuse (nom anglais). |
| `player_name` | VARCHAR | Nom du joueur. |
| `player_qid` | VARCHAR | QID Wikidata du joueur (clé de jointure avec `squad.player_qid`) ; vide si sa page n'a pas d'élément. |
| `shirt_number` | INTEGER | Numéro de maillot dans la liste ; vide si non donné. |
| `position` | VARCHAR | Poste écrit dans la liste (`GK`, `DF`, `MF`, `FW`). |

### `coach`

Entraîneurs : un mandat par ligne (entraîneur d'un club entre deux dates), d'après la propriété Wikidata « entraîneur ». Les mandats sans date de début ne sont pas publiés ; les entraîneurs intérimaires y figurent comme les autres.

- Fichiers : `coach/coach.dbf04afe.parquet` — **8 099 lignes**
- Clé : (club, coach_qid, start_date)

| Colonne | Type | Description |
|---|---|---|
| `club` | VARCHAR | Titre de la page Wikipedia du club dans `club`. |
| `coach_qid` | VARCHAR | QID Wikidata de l'entraîneur (clé de jointure avec `squad.player_qid` quand il a aussi été joueur de notre base). |
| `coach_name` | VARCHAR | Nom de l'entraîneur (libellé Wikidata). |
| `start_date` | DATE | Début du mandat. |
| `end_date` | DATE | Fin du mandat ; vide si le mandat est en cours ou si la fin n'est pas renseignée. |

### `match`

Matchs : résultats, calendriers et détails (stade, affluence, arbitre) des championnats, de la Ligue des champions, des Coupes du monde, des Euros, de la Coupe du monde des clubs, de la Libertadores, du dépôt `world` et des sélections nationales depuis 1872. **Source : les données ouvertes du projet OpenFootball (github.com/openfootball, CC0)**, pas Wikipedia ; elles couvrent les saisons récentes et certaines ligues seulement. Un match sans score n'est pas encore joué.

- Fichiers : `match/match.be917553.parquet` — **165 719 lignes**
- Clé : (match_id)

| Colonne | Type | Description |
|---|---|---|
| `match_id` | INTEGER | Identifiant du match (clé de jointure avec `match_goal`). |
| `competition` | VARCHAR | Code de notre compétition (`ENG-PL`…) ou `OF:<clé>` quand la compétition n'existe pas chez nous (`OF:worldcup`, `OF:euro`, `OF:en.3`…). |
| `season` | VARCHAR | Saison (`2025/26`) ou année du tournoi (`2022`). |
| `round` | VARCHAR | Journée ou tour tel qu'écrit par la source (`Matchday 1`, `Round of 16`). |
| `group_name` | VARCHAR | Groupe (tournois). |
| `match_date` | DATE | Date du match. |
| `kickoff` | VARCHAR | Heure du coup d'envoi, locale, telle qu'écrite par la source. |
| `home_name` | VARCHAR | Équipe qui reçoit, telle qu'écrite par la source. |
| `away_name` | VARCHAR | Équipe qui se déplace, telle qu'écrite par la source. |
| `home_club` | VARCHAR | Titre de la page Wikipedia du club qui reçoit dans `club` ; vide si aucun club de la compétition ne porte ce nom (et pour les sélections). |
| `away_club` | VARCHAR | Titre de la page Wikipedia du club qui se déplace dans `club` ; vide si aucun club ne correspond (et pour les sélections). |
| `ft_home` | INTEGER | Buts de l'équipe qui reçoit à la fin du temps réglementaire. |
| `ft_away` | INTEGER | Buts de l'équipe qui se déplace à la fin du temps réglementaire. |
| `ht_home` | INTEGER | Buts de l'équipe qui reçoit à la mi-temps. |
| `ht_away` | INTEGER | Buts de l'équipe qui se déplace à la mi-temps. |
| `et_home` | INTEGER | Buts de l'équipe qui reçoit après prolongation (cumul). |
| `et_away` | INTEGER | Buts de l'équipe qui se déplace après prolongation (cumul). |
| `pen_home` | INTEGER | Tirs au but marqués par l'équipe qui reçoit. |
| `pen_away` | INTEGER | Tirs au but marqués par l'équipe qui se déplace. |
| `ground` | VARCHAR | Stade, tel qu'écrit par la source. |
| `attendance` | INTEGER | Affluence. |
| `referee` | VARCHAR | Arbitre central. |
| `source_ref` | VARCHAR | Fichier du dépôt OpenFootball d'où vient la ligne (ou page Wikipedia pour un match créé depuis sa matrice). |
| `result_source` | VARCHAR | Provenance du score : vide = la source de matchs OpenFootball ; `wikipedia` = la matrice de résultats de la page Wikipedia de la saison (saison en cours, quand OpenFootball a du retard). En cas de désaccord, le score d'OpenFootball est gardé. |

### `match_competition`

Nom des compétitions `OF:*` de `match` (celles que nous n'avons pas comme championnat), lu dans l'en-tête du fichier source ; en anglais.

- Fichiers : `match_competition/match_competition.420f56fa.parquet` — **33 lignes**
- Clé : (code)

| Colonne | Type | Description |
|---|---|---|
| `code` | VARCHAR | Code `OF:<clé>` tel que dans `match.competition`. |
| `name` | VARCHAR | Nom de la compétition, sans l'année (`FIFA World Cup`, `English League One`). |
| `wikipedia_title` | VARCHAR | Titre de la page Wikipedia anglaise de la compétition ; les qualifications reprennent la page du tournoi qu'elles préparent. Vide pour les matchs amicaux. |
| `logo_url` | VARCHAR | Miniature du logo (champ `image` de l'infobox, hébergée par Wikimedia) ; souvent non libre : voir `logo_license`. |
| `logo_license` | VARCHAR | Licence du fichier du logo, telle que Wikimedia la déclare. |

### `match_goal`

Buteurs d'un match, quand la source les donne (Coupes du monde, Euros).

- Fichiers : `match_goal/match_goal.1e2d8175.parquet` — **48 147 lignes**
- Clé : (match_id, seq)

| Colonne | Type | Description |
|---|---|---|
| `match_id` | INTEGER | Match (`match.match_id`). |
| `seq` | INTEGER | Rang du but dans la liste de la source. |
| `side` | VARCHAR | `home` ou `away` : l'équipe à qui le but est compté (pour un but contre son camp, celle qui en profite). |
| `player_name` | VARCHAR | Nom du buteur, tel qu'écrit par la source. |
| `player_qid` | VARCHAR | QID Wikidata du joueur de notre base à qui ce nom a été rattaché (effectif du club cette saison-là, sans ambiguïté) ; vide sinon : le nom seul ne désigne personne. |
| `minute` | VARCHAR | Minute (`37`, `90+4`). |
| `kind` | VARCHAR | `goal`, `penalty` ou `own_goal`. |

### `match_lineup`

Compositions d'un match, quand la source les donne (6 championnats : Premier League, Bundesliga, Liga, Serie A, Ligue 1, Bundesliga autrichienne, depuis 2025/26).

- Fichiers : `match_lineup/match_lineup.3554b000.parquet` — **56 249 lignes**
- Clé : (match_id, side, seq)

| Colonne | Type | Description |
|---|---|---|
| `match_id` | INTEGER | Match (`match.match_id`). |
| `side` | VARCHAR | `home` ou `away`. |
| `seq` | INTEGER | Ordre d'écriture de la source : le gardien d'abord, puis les lignes, puis les remplaçants. |
| `player_name` | VARCHAR | Nom tel qu'écrit par la source (la casse varie : `MOHAMED SALAH`, `Hugo EKITIKE`) ; pas de clé de joueur. |
| `player_qid` | VARCHAR | QID Wikidata du joueur de notre base à qui ce nom a été rattaché (effectif du club cette saison-là, sans ambiguïté) ; vide sinon : le nom seul ne désigne personne. |
| `role` | VARCHAR | `start` (titulaire) ou `sub` (entré en cours de match). |
| `minute` | VARCHAR | Minute d'entrée d'un remplaçant ; pour un titulaire remplacé, minute de sa sortie ; vide sinon. |
| `captain` | BOOLEAN | Capitaine. |

### `match_card`

Cartons d'un match, quand la source donne le détail.

- Fichiers : `match_card/match_card.783a1d02.parquet` — **7 227 lignes**
- Clé : (match_id, seq)

| Colonne | Type | Description |
|---|---|---|
| `match_id` | INTEGER | Match (`match.match_id`). |
| `seq` | INTEGER | Rang dans la liste de la source. |
| `side` | VARCHAR | `home` ou `away` : l'équipe du joueur sanctionné. |
| `player_name` | VARCHAR | Joueur, tel qu'écrit par la source. |
| `player_qid` | VARCHAR | QID Wikidata du joueur de notre base à qui ce nom a été rattaché (effectif du club cette saison-là, sans ambiguïté) ; vide sinon : le nom seul ne désigne personne. |
| `minute` | VARCHAR | Minute. |
| `kind` | VARCHAR | `yellow` ou `red`. |

### `player_openfootball`

Taille et lieu de naissance venus du dépôt `players` d'OpenFootball (domaine public), **seulement là où le profil Wikipedia (`player_profile`) n'en a pas** : une valeur Wikipedia n'est jamais écrasée. Un joueur n'est relié que par son nom ET sa date de naissance exacte, jamais par le nom seul.

- Fichiers : `player_openfootball/player_openfootball.337eb1e3.parquet` — **667 lignes**
- Clé : (player_qid)

| Colonne | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | QID Wikidata du joueur (clé de jointure avec `player_profile.player_qid`). |
| `height_cm` | INTEGER | Taille en centimètres ; vide si Wikipedia en a déjà une. |
| `birth_place` | VARCHAR | Lieu de naissance (ville) ; vide si Wikipedia en a déjà un. |

### `player_external_id`

Identifiants externes d'un joueur lus sur Wikidata (jamais devinés) : Transfermarkt (P2446) et FBref (P5750). Une ligne par joueur qui en a au moins un ; ils servent de liens sortants.

- Fichiers : `player_external_id/player_external_id.5905f6c1.parquet` — **61 835 lignes**
- Clé : (player_qid)

| Colonne | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | QID Wikidata du joueur (clé de jointure avec `player_profile.player_qid`). |
| `transfermarkt_id` | VARCHAR | Identifiant Transfermarkt (`https://www.transfermarkt.com/-/profil/spieler/<id>`) ; vide s'il n'y en a pas. |
| `fbref_id` | VARCHAR | Identifiant FBref (`https://fbref.com/en/players/<id>/`) ; vide s'il n'y en a pas. |

### `top_scorer`

Classement des buteurs de chaque championnat et de chaque saison, lu dans le tableau « Top scorers » de la page Wikipedia de la saison (aucun autre calcul). Le rang est recalculé sur les buts (classement standard : 1, 2, 2, 4).

- Fichiers : `top_scorer/top_scorer.224e7cdf.parquet` — **1 757 lignes**
- Clé : (competition, season, rank, player_name)

| Colonne | Type | Description |
|---|---|---|
| `competition` | VARCHAR | Code de la compétition (`ENG-PL`, `FRA-L1`…). |
| `season` | VARCHAR | Saison, par exemple `2017/18`. |
| `rank` | INTEGER | Rang sur les buts ; les ex æquo partagent le même rang. |
| `player_name` | VARCHAR | Nom du joueur, tel que Wikipedia l'écrit. |
| `player_qid` | VARCHAR | QID Wikidata du joueur quand il est connu de la base, sinon vide. |
| `club_name` | VARCHAR | Club tel qu'écrit dans le tableau (celui de la saison). |
| `club` | VARCHAR | Titre de la page Wikipedia du club quand il est connu, sinon vide (jointure avec `club.wikipedia_title`). |
| `goals` | INTEGER | Buts marqués en championnat. |

### `player_profile`

Profil lu dans l'infobox Wikipedia anglaise : nom complet, lieu de naissance, taille, décès et **photo** (une ligne par joueur ayant au moins une de ces informations). Valeurs **publiées telles quelles par Wikipedia, non vérifiées**.

- Fichiers : `player_profile/player_profile.60cbf6cf.parquet` — **60 603 lignes**
- Clé : (player_qid ou player)

| Colonne | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | QID Wikidata du joueur (clé de jointure avec `squad.player_qid`). |
| `player` | VARCHAR | Nom du joueur (repli de clé : `'name:' || player` quand `player_qid` est vide). |
| `full_name` | VARCHAR | Nom complet (`full_name` de l'infobox). |
| `birth_place` | VARCHAR | Lieu de naissance, en texte (ville, région, pays). |
| `height_cm` | INTEGER | Taille en cm (entre 140 et 220, sinon vide). |
| `death_date` | VARCHAR | Date de décès `YYYY-MM-DD` (ou l'année seule) ; vide pour un joueur en vie. |
| `photo_caption` | VARCHAR | Légende de la photo dans l'infobox. |
| `photo_url` | VARCHAR | Miniature (300 px) de la photo d'infobox, pour un joueur en vie ; retirée si la licence du fichier est non libre (`enrich --what photos`). |
| `photo_page` | VARCHAR | Page du fichier sur Wikipedia / Wikimedia Commons (attribution et licence complète). |
| `photo_license` | VARCHAR | Licence de la photo (`CC BY-SA 4.0`…) ; vide tant qu'elle n'a pas été vérifiée. |
| `photo_author` | VARCHAR | Auteur de la photo, tel que déclaré sur la page du fichier ; vide tant qu'il n'a pas été vérifié. |

### `birth`

Dates de naissance (Wikidata P569) des joueurs identifiés.

- Fichiers : `birth/birth.8095f521.parquet` — **63 005 lignes**
- Clé : player_qid

| Colonne | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | QID Wikidata du joueur. |
| `birth_date` | VARCHAR | Date au format `YYYY-MM-DD` (texte). |
| `precision` | INTEGER | Précision Wikidata : 9 = année seule, 10 = mois, 11 = jour. **Un âge n'est calculé que si la précision est 11.** |

### `entity_wiki`

Page Wikipedia d'un club ou d'un joueur dans chaque langue (en, fr, it, de, es pour les clubs ; en, fr pour les joueurs).

- Fichiers : `entity_wiki/entity_wiki.83ce0dd9.parquet` — **100 720 lignes**
- Clé : (qid, lang)

| Colonne | Type | Description |
|---|---|---|
| `qid` | VARCHAR | QID Wikidata du club ou du joueur. |
| `lang` | VARCHAR | Code de langue Wikipedia. |
| `title` | VARCHAR | Titre de la page dans cette langue. |


## Tables de travail (`work`)

Fichiers `work_*/` du manifeste (clé `work`) : ce que la base de travail garde en plus du Parquet lu par le site. Ils servent à reconstruire une base COMPLÈTE (`openfootball restore-db`) et ne sont pas lus par le site. Ils portent des clés naturelles (titre du club, saison, QID du joueur ou son nom), jamais de numéro interne.

| Fichiers | lignes | Description |
|---|---|---|
| `work_squad_movement/work_squad_movement.d0266bbd.parquet` | 62 201 | mouvements de joueurs : date, fenêtre de transferts, club d'origine ou de destination, prêt ou transfert |
| `work_loan_out/work_loan_out.73d10adf.parquet` | 24 139 | joueurs prêtés ailleurs (absents de l'effectif de leur club d'origine, donc de `squad`) |
| `work_entity_label/work_entity_label.f36f4bd8.parquet` | 9 042 | libellés anglais et français des entités Wikidata (villes, stades, championnats, clubs) |
| `work_player_alias/work_player_alias.c402c405.parquet` | 2 | rustines de noms de joueurs vers leur page Wikipedia |
| `work_amendment_log/work_amendment_log.0c2fe472.parquet` | 785 | journal des corrections apportées à des saisons ou à des clubs-saisons |
| `work_competition_wikidata/work_competition_wikidata.e5980bb3.parquet` | 92 | identifiant Wikidata des compétitions |
| `work_club_work/work_club_work.94d61dcc.parquet` | 41 769 | identifiants Wikidata des clubs (pays, ville, stade, championnat) dont les libellés sont dans `entity_label` |

