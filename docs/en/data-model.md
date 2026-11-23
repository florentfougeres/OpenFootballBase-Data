# OpenFootballBase — data dictionary

Football club squads by season, built **only** from Wikipedia (CC BY-SA 4.0) and Wikidata (CC0).
This file describes the Parquet files of this release; it is generated at export time, from the files themselves.
[Version française : `SCHEMA.fr.md`](../fr/data-model.md).

## Layout of a release

- `manifest.json` — **entry point**: date, schema version, and for each file its path, row count and SHA-256 fingerprint.
- One file **per season** for `squad` and `club_season`; one file per table for the others.
- File names contain the first 8 characters of their fingerprint: `squad/2025-26.8fdfe5a8.parquet`. A file whose content does not change keeps its name (browser cache, comparison between releases).
- `frozen` seasons are immutable; the `open` season (the current one) changes at each release.

```json
{ "format": 1, "schema_version": 9, "generated_at": "…",
  "seasons": { "2025/26": { "status": "…", "content_hash": null,
      "coverage": { "club_seasons": 96, "with_squad": 96, "known_gaps": 0 },
      "files": { "squad": { "path": "squad/…parquet", "rows": 2956, "sha256": "…" },
                 "club_season": { "path": "club_season/…parquet", "rows": 96, "sha256": "…" } } } },
  "tables": { "club": { "path": "club/…parquet", "rows": 42857, "sha256": "…" } } }
```

## Reading the data

```sql
-- DuckDB: every squad, every season (the files have different names: use a glob)
SELECT * FROM read_parquet('squad/*.parquet', union_by_name = true) WHERE club = 'Olympique de Marseille';
```

## Relational schema (join keys)

```
country.code ──< competition.country_code
competition.code ──< squad.competition, club_season.competition
club.wikipedia_title ──< squad.club, club_season.club        (club.has_squads = true)
club.wikidata_qid ──< career.club_qid
season.label ──< squad.season, club_season.season, known_gap.season
squad.player_qid ──< career.player_qid, national.player_qid, birth.player_qid
(club|player QID) ──< entity_wiki.qid
```

**A player's identity** is his Wikidata QID (`player_qid`). When it is empty (unidentified player), the fallback key is
`'name:' || player`; two unidentified namesakes cannot then be told apart.

## What to know before using the data

- **A squad is the union of several pages**: every language of the country is read and merged (`squad_source`, `squad.listed_in`) to be as complete as possible; a player may come from a page older or newer than the main one.
- **A squad is a snapshot**: the list published on the Wikipedia page at its update date, not the list of every player of the season. A player who joined or left mid-season may be missing.
- **In-season movements**: `stint = arrived_mid / left_mid` (with `stint_date`) read from the transfer tables of the **English** pages; club-seasons whose English page has no usable table stay `unknown`. A player who left mid-season is in his former club's squad (`left_mid`) and in his new club's (`arrived_mid`).
- **Loans**: a player loaned elsewhere (`loan_out`) is not in his parent club's squad; he is in the host club's (`stint = 'loan_in'`).
- **Career and caps** (appearances, goals): published as is from the Wikipedia infoboxes, **unverified**, and they may differ from one language to another.
- **Gaps**: squads that cannot be found are listed in `known_gap`; the other club-seasons without a squad have not been examined yet (`club_season.players = 0` with no reason).
- **Scripts**: stadium, league and city names in a non-Latin script are replaced by their English Wikidata label (empty if none exists).
- **Logos**: images hosted by Wikimedia, often non-free; use them for illustration only.
- **Ages**: compute from `birth` only if `precision = 11`.
- Licences: Wikipedia text CC BY-SA 4.0 (attribution: the source page is given by `source_title` / `source_revid`), Wikidata CC0.


## Tables

### `squad`

A club's squad for one season: **one row = one player in a club's squad that season**. One file per season (`squad/<season>.<sha8>.parquet`). Players loaned out elsewhere (`loan_out`) are not listed.

- Files : 27 files (one per season), e.g. `squad/2026-27.03e74a93.parquet` — **300 390 rows**
- Key : (season, club, player_qid or player)

| Column | Type | Description |
|---|---|---|
| `season` | VARCHAR | Season, formatted `2025/26` (= `season.label`). |
| `competition` | VARCHAR | League code, e.g. `FRA-L1` (= `competition.code`). |
| `club` | VARCHAR | Title of the club's English Wikipedia page (= `club.wikipedia_title`). |
| `player` | VARCHAR | Player name as published on the source page. |
| `player_qid` | VARCHAR | Player's Wikidata QID. **Empty if the player could not be identified**: his identity is then his name alone (fallback key: `'name:' || player`). |
| `link_lang` | VARCHAR | Language of the player's Wikipedia page cited on the source page (`en`, `it`…). Empty for pages without links (fr, es). |
| `link_title` | VARCHAR | Title of that Wikipedia page of the player. |
| `shirt_number` | INTEGER | Shirt number (0 to 99). Empty if absent from the source. |
| `position` | VARCHAR | Position: `GK` goalkeeper, `DF` defender, `MF` midfielder, `FW` forward. Empty if not stated. |
| `nationality` | VARCHAR | Nationality as published (free text, in the page's language: `France`, `España`, `IRL`…). |
| `nat_flag` | VARCHAR | Flag code (flag-icons: `fr`, `gb-eng`, `ie`…) derived from the nationality; empty if not recognised. |
| `stint` | VARCHAR | Status at the club: `unknown` (nothing specific), `arrived_mid` (joined during the season), `left_mid` (left during the season: he played for the club before), `loan_in` (loaned **to** this club). Players loaned elsewhere (`loan_out`) are not exported. Movements come from the "Transfers" tables of the English pages. |
| `confidence` | VARCHAR | Level of evidence: `attested` = cited in the squad published on the source page. |
| `source` | VARCHAR | Origin of the row: `wikipedia_season` ("club season" page). |
| `source_section` | VARCHAR | Title of the section or table of the page where the player was read. |
| `listed_in` | VARCHAR | Languages of the pages that list this player, by priority (`fr,it`: cited by the French and the Italian page). A player cited by several pages is better attested. |
| `stint_date` | VARCHAR | Date of the movement (`YYYY-MM-DD`) for `arrived_mid`, `left_mid` or a loan; empty if the page gives no date. |
| `stint_window` | VARCHAR | Transfer window (`winter`, `summer`) when the page names it without an exact date. |
| `stint_other_club` | VARCHAR | Club he comes from (`arrived_mid`, `loan_in`) or goes to (`left_mid`), as written on the page. |
| `source_lang` | VARCHAR | Language of the **main** source page of the squad (`en`, `fr`, `it`, `es`): the country's own language first. |
| `source_title` | VARCHAR | Title of that main page. |
| `source_revid` | BIGINT | Wikipedia revision number that was read (to retrieve the exact version). |

### `club_season`

One row = **a club in a league for one season** (with or without a squad). One file per season (`club_season/<season>.<sha8>.parquet`).

- Files : 27 files (one per season), e.g. `club_season/2026-27.f1cd6e1f.parquet` — **26 674 rows**
- Key : (season, club)

| Column | Type | Description |
|---|---|---|
| `season` | VARCHAR | Season, `2025/26`. |
| `competition` | VARCHAR | League code (`competition.code`). |
| `club` | VARCHAR | Title of the club's English Wikipedia page (`club.wikipedia_title`). |
| `source_lang` | VARCHAR | Language of the **main** page whose squad was read; empty if no squad could be established. The other pages used are in `squad_source`. |
| `source_title` | VARCHAR | Title of that main page. |
| `source_revid` | BIGINT | Wikipedia revision that was read. |
| `players` | BIGINT | Number of players in `squad` for this club and season (0 = no squad). |
| `known_gap_reason` | VARCHAR | If the squad is missing and the gap was validated by hand: the reason. Otherwise empty. |

### `squad_source`

The "club season" pages whose **union** makes the squad: a squad is read from every language of the country (the country's language first, then English, Italian…) to be as complete as possible. **One row = one page used.**

- Files : `squad_source/squad_source.d3a0cd20.parquet` — **13 125 rows**
- Key : (season, club, source_lang)

| Column | Type | Description |
|---|---|---|
| `season` | VARCHAR | Season, `2025/26`. |
| `competition` | VARCHAR | League code. |
| `club` | VARCHAR | Title of the club's Wikipedia page. |
| `rank` | INTEGER | Priority of the source: 1 = main source (the one in `club_season.source_*`). |
| `source_lang` | VARCHAR | Language of the page. |
| `source_title` | VARCHAR | Title of the page. |
| `source_revid` | BIGINT | Wikipedia revision that was read. |
| `players_read` | INTEGER | Players of the main squad read from this page (and found in the merged squad). |
| `players_added` | INTEGER | Players this page adds that no higher-priority source had. |

### `club`

Every known football club (≈ 43,000, source: Wikidata). `has_squads` tells the clubs whose squads we have.

- Files : `club/club.8985c057.parquet` — **44 983 rows**
- Key : wikidata_qid (wikipedia_title is also unique when present)

| Column | Type | Description |
|---|---|---|
| `wikidata_qid` | VARCHAR | The club's Wikidata identifier (e.g. `Q483020`). |
| `wikipedia_title` | VARCHAR | Title of the English Wikipedia page; empty if the club has none. |
| `name_en` | VARCHAR | English name (Wikidata label). |
| `name_fr` | VARCHAR | French name (Wikidata label). |
| `name_local` | VARCHAR | Name in the club's language; replaced by the English name if it is in a non-Latin script. |
| `nickname` | VARCHAR | Nickname; hidden if in a non-Latin script. |
| `category` | VARCHAR | Wikidata category (men, women, youth…). |
| `country_code` | VARCHAR | Internal country code (`ENG`, `FRA`, `ITA`, `ESP`, `DEU`) — **only for clubs with squads** (= `country.code`). |
| `country_iso` | VARCHAR | ISO 3166-1 alpha-2 country code, upper case (`FR`). |
| `country` | VARCHAR | Country name as published by Wikidata. |
| `city` | VARCHAR | City; English label if the published name is in a non-Latin script, empty if none exists. |
| `stadium` | VARCHAR | Stadium; same rule as `city`. |
| `stadium_capacity` | INTEGER | Stadium capacity (seats). |
| `division` | INTEGER | Current level in the pyramid (1 = top flight). |
| `league` | VARCHAR | Current league; same rule as `city`. |
| `founded` | VARCHAR | Foundation date: full ISO date or year only, as published. |
| `colors` | VARCHAR | Colour names, separated by ` | `. |
| `colors_hex` | VARCHAR | Colours in hexadecimal (`#0B61AC`), separated by ` | ` (same order as `colors`). |
| `website` | VARCHAR | Official website. |
| `logo_url` | VARCHAR | Logo thumbnail read from the infobox of the English Wikipedia page (hosted by Wikimedia). Many are **non-free** (fair use): see `logo_license`. |
| `logo_license` | VARCHAR | Licence of the logo file (`CC BY-SA`, `Public domain`, `non-free`…). |
| `logo_commons_url` | VARCHAR | Free logo on Wikimedia Commons, used as a fallback. |
| `wikipedia_en_url` | VARCHAR | URL of the English Wikipedia page. |
| `wikipedia_local_url` | VARCHAR | URL of the Wikipedia page in the club's language. |
| `wikipedia_count` | INTEGER | Number of language versions of the Wikipedia page: a notability indicator. |
| `lon` | DOUBLE | Longitude (WGS 84). |
| `lat` | DOUBLE | Latitude (WGS 84). |
| `transfermarkt_id` | VARCHAR | The club's Transfermarkt identifier (link only: no Transfermarkt data is used). |
| `fbref_id` | VARCHAR | FBref identifier (link only). |
| `worldfootball_id` | VARCHAR | WorldFootball identifier (link only). |
| `has_squads` | BOOLEAN | True if the club has at least one squad in `club_season`. |

### `competition`

The competitions covered: leagues in scope, partial leagues of countries outside the scope, and cups (`UEFA-CL`, `CONMEBOL-CL`…).

- Files : `competition/competition.aa65a820.parquet` — **152 rows**
- Key : code

| Column | Type | Description |
|---|---|---|
| `code` | VARCHAR | League code: `<COUNTRY>-<ABBREVIATION>`, e.g. `FRA-L1`. |
| `name_en` | VARCHAR | English name. |
| `name_fr` | VARCHAR | French name. |
| `country_code` | VARCHAR | The league's country (`country.code`). |
| `level` | INTEGER | Level in the pyramid (1 = first division). 5: domestic cup or supercup (no club or squad per season, only a list of winners). |
| `wikidata_qid` | VARCHAR | The league's Wikidata QID, when known. |
| `wikipedia_title` | VARCHAR | Title of the league's English Wikipedia page. |
| `logo_url` | VARCHAR | League logo thumbnail read from the infobox of its Wikipedia page (hosted by Wikimedia). Often **non-free**: see `logo_license`. |
| `logo_license` | VARCHAR | Licence of the logo file (`Public domain`, `Fair use`…). |

### `country`

The countries covered by `competition`.

- Files : `country/country.c2d43633.parquet` — **116 rows**
- Key : code

| Column | Type | Description |
|---|---|---|
| `code` | VARCHAR | Internal 3-letter code (`FRA`, `ENG`…). |
| `name_en` | VARCHAR | English name. |
| `name_fr` | VARCHAR | French name. |
| `flag` | VARCHAR | flag-icons code (`fr`, `gb-eng`). |

### `season`

The seasons present and their state.

- Files : `season/season.a28d16c4.parquet` — **27 rows**
- Key : label

| Column | Type | Description |
|---|---|---|
| `label` | VARCHAR | Season, `2025/26`. |
| `start_year` | INTEGER | Start year (2025 for 2025/26). |
| `status` | VARCHAR | `open` = current season (may change at each release), `backfill` = over but not frozen, `frozen` = frozen (immutable). |
| `content_hash` | VARCHAR | Content fingerprint, set only for a frozen season: `verify-release` rejects any release that changes it. |

### `competition_club`

Clubs taking part in a competition, by season: the league's clubs (from `club_season`) **and** those that take part in addition to their league (continental cups, table `competition_entry`).

- Files : `competition_club/competition_club.5eb08a4e.parquet` — **30 184 rows**
- Key : (season, competition, club)

| Column | Type | Description |
|---|---|---|
| `season` | VARCHAR | Season, `2025/26`. |
| `competition` | VARCHAR | Competition code (`UEFA-CL`, `ENG-PL`…), key of `competition.code`. |
| `club` | VARCHAR | Title of the club's Wikipedia page, key of `club.wikipedia_title`. |

### `known_gap`

Squads that cannot be found and whose absence was **explicitly validated** (the source does not exist).

- Files : `known_gap/known_gap.2e22296a.parquet` — **1 006 rows**
- Key : (season, club)

| Column | Type | Description |
|---|---|---|
| `season` | VARCHAR | Season, `2012/13`. |
| `club` | VARCHAR | Title of the club's Wikipedia page. |
| `reason` | VARCHAR | Reason for the gap (e.g. "page missing"). |

### `career`

A player's senior career, read from the infobox of his **English** Wikipedia page: **one row = one spell at a club**.

- Files : `career/career.12be0dfc.parquet` — **485 765 rows**
- Key : (player_qid or player, seq)

| Column | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | Player's Wikidata QID (join key with `squad.player_qid`). |
| `player` | VARCHAR | Player name (fallback key: `'name:' || player` when `player_qid` is empty). |
| `seq` | INTEGER | Rank of the spell in the infobox (1, 2, 3…). |
| `start_year` | INTEGER | Start year of the spell. |
| `end_year` | INTEGER | End year; **empty = ongoing or unknown**. |
| `years_raw` | VARCHAR | Years as published (`2015–2021`). |
| `club_name` | VARCHAR | Club name as published in the infobox. |
| `club_link` | VARCHAR | Title of the cited club's Wikipedia page (may be a redirect). |
| `club_qid` | VARCHAR | Club's Wikidata QID, resolved from `club_link` (= `club.wikidata_qid`); empty if not found. |
| `loan` | BOOLEAN | True if the spell is a loan (arrow `→` or `(loan)` in the infobox). |
| `apps` | INTEGER | Appearances, **as published by Wikipedia, unverified**. |
| `goals` | INTEGER | Goals, **as published by Wikipedia, unverified**. |
| `source_lang` | VARCHAR | Language of the page read (always `en`). |
| `source_title` | VARCHAR | Title of the player's page. |
| `source_revid` | BIGINT | Wikipedia revision that was read. |

### `national`

National-team appearances (youth included), read from the infobox: **one row = one team**.

- Files : `national/national.481fd655.parquet` — **90 838 rows**
- Key : (player_qid or player, seq)

| Column | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | Player's Wikidata QID. |
| `player` | VARCHAR | Player name. |
| `seq` | INTEGER | Rank in the infobox. |
| `years_raw` | VARCHAR | Years as published. |
| `team_name` | VARCHAR | Team: `France`, `France U21`… |
| `team_link` | VARCHAR | Title of the team's Wikipedia page. |
| `caps` | INTEGER | Caps, **as published, unverified**. |
| `goals` | INTEGER | International goals, **as published, unverified**. |

### `stat_club`

Career statistics **by club, season and competition**, read from the "Career statistics" section of the player's English Wikipedia page (players of Champions League clubs from the 7 major countries, since 2010). **One row = one club, one season, one competition group.** Values **as published, unverified**; an empty cell or "—" is empty, not zero.

- Files : `stat_club/stat_club.610725e7.parquet` — **911 539 rows**
- Key : (player_qid or player, seq)

| Column | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | Player's Wikidata QID. |
| `player` | VARCHAR | Player name (key fallback: `'name:' || player`). |
| `seq` | INTEGER | Rank in the table. |
| `club` | VARCHAR | Club, as written. |
| `club_link` | VARCHAR | Title of the club's Wikipedia page. |
| `club_qid` | VARCHAR | Club's Wikidata QID, when known. |
| `season` | VARCHAR | Season `2008–09`, or the year alone (`2022`) for a calendar-year league. |
| `division` | VARCHAR | Division, as written. |
| `competition_group` | VARCHAR | Competition group: `League`, `National cup`, `League cup`, `Continental` (or `Europe`), `Other`. |
| `apps` | INTEGER | Appearances. |
| `goals` | INTEGER | Goals. |
| `assists` | INTEGER | Assists, when the page gives them. |

### `stat_national`

National-team statistics **by team and year**, read from the "Career statistics" section (same scope as `stat_club`). Values **as published, unverified**.

- Files : `stat_national/stat_national.80662b6d.parquet` — **49 677 rows**
- Key : (player_qid or player, seq)

| Column | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | Player's Wikidata QID. |
| `player` | VARCHAR | Player name. |
| `seq` | INTEGER | Rank in the table. |
| `team` | VARCHAR | Team: `France`, `Portugal U21`… |
| `team_link` | VARCHAR | Title of the team's Wikipedia page. |
| `year` | VARCHAR | Year (`2014`) or period (`2014–15`). |
| `competition_group` | VARCHAR | `Competitive`, `Friendly`, or `Total` when the page does not split them. |
| `apps` | INTEGER | Caps. |
| `goals` | INTEGER | International goals. |

### `stat_source`

Provenance of the statistics: the page read for each player (one row per player read, even without a table).

- Files : `stat_source/stat_source.cb237ef7.parquet` — **49 417 rows**
- Key : (player_qid or player)

| Column | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | Player's Wikidata QID. |
| `player` | VARCHAR | Player name. |
| `source_title` | VARCHAR | Title of the English Wikipedia page read. |
| `source_revid` | BIGINT | Revision read. |
| `club_rows` | INTEGER | Rows read into `stat_club`. |
| `national_rows` | INTEGER | Rows read into `stat_national`. |

### `winner`

Honours: the winner of each season of a competition, from Wikidata (one row per winner; joint winners give two rows).

- Files : `winner/winner.152033d1.parquet` — **5 613 rows**
- Key : (competition, season_start, winner_qid)

| Column | Type | Description |
|---|---|---|
| `competition` | VARCHAR | Competition code (`FRA-L1`, `UEFA-CL`…). |
| `season_start` | INTEGER | Start year of the season (`2003` for 2003/04; the calendar year for a league played over one year). |
| `winner_name` | VARCHAR | English Wikidata label of the winner. |
| `winner_qid` | VARCHAR | Wikidata QID of the winner. |
| `club` | VARCHAR | Title of the club's Wikipedia page in `club` when the winner is there; empty otherwise. |
| `season_qid` | VARCHAR | Wikidata QID of the season (the row's source). |

### `award`

Rankings of individual awards: one row per ranked player of an edition of the Ballon d'Or (since 2000), from the edition's Wikipedia page.

- Files : `award/award.e18a6e69.parquet` — **609 rows**
- Key : (award, year, rank, player_name)

| Column | Type | Description |
|---|---|---|
| `award` | VARCHAR | Award (`BALLON_DOR`). |
| `year` | INTEGER | Edition year (of the ceremony). |
| `rank` | INTEGER | Rank (1 = winner). Some editions only give the podium. |
| `player_name` | VARCHAR | Player name. |
| `player_qid` | VARCHAR | Wikidata QID of the player (join key with `squad.player_qid`); empty if his page has no item. |
| `club_name` | VARCHAR | Club at the time of the edition, as written on the page. |
| `club` | VARCHAR | Title of the club's Wikipedia page in `club` when it is there; empty otherwise. |
| `points` | INTEGER | Points received; empty when the page does not give them. |

### `national_title`

National-team titles: for each edition of a national-team competition (World Cup, Euro, Copa América, Africa Cup of Nations, Asian Cup, Gold Cup, Confederations Cup), the players of the winning team, from the edition's squads page on Wikipedia. A listed player may not have played.

- Files : `national_title/national_title.f8610ca9.parquet` — **2 975 rows**
- Key : (competition, year, player_name)

| Column | Type | Description |
|---|---|---|
| `competition` | VARCHAR | `WORLD_CUP`, `EURO`, `COPA_AMERICA`, `AFCON`, `ASIAN_CUP`, `GOLD_CUP` or `CONFEDERATIONS_CUP`. |
| `year` | INTEGER | Edition year. |
| `team` | VARCHAR | Winning team (English name). |
| `player_name` | VARCHAR | Player name. |
| `player_qid` | VARCHAR | Wikidata QID of the player (join key with `squad.player_qid`); empty if his page has no item. |
| `shirt_number` | INTEGER | Shirt number in the list; empty if not given. |
| `position` | VARCHAR | Position written in the list (`GK`, `DF`, `MF`, `FW`). |

### `coach`

Coaches: one tenure per row (a coach of a club between two dates), from the Wikidata "head coach" property. Tenures without a start date are not published; caretaker coaches appear like the others.

- Files : `coach/coach.dbf04afe.parquet` — **8 099 rows**
- Key : (club, coach_qid, start_date)

| Column | Type | Description |
|---|---|---|
| `club` | VARCHAR | Title of the club's Wikipedia page in `club`. |
| `coach_qid` | VARCHAR | Wikidata QID of the coach (join key with `squad.player_qid` when he was also a player in our database). |
| `coach_name` | VARCHAR | Coach name (Wikidata label). |
| `start_date` | DATE | Start of the tenure. |
| `end_date` | DATE | End of the tenure; empty if the tenure is ongoing or the end is not recorded. |

### `match`

Matches: results, fixtures and details (ground, attendance, referee) of the league championships, the Champions League, World Cups, Euros, the Club World Cup, the Libertadores, the `world` repository and national teams since 1872. **Source: the open data of the OpenFootball project (github.com/openfootball, CC0)**, not Wikipedia; it covers recent seasons and some leagues only. A match without a score has not been played yet.

- Files : `match/match.be917553.parquet` — **165 719 rows**
- Key : (match_id)

| Column | Type | Description |
|---|---|---|
| `match_id` | INTEGER | Match identifier (join key with `match_goal`). |
| `competition` | VARCHAR | Our competition code (`ENG-PL`…) or `OF:<key>` when the competition does not exist in our data (`OF:worldcup`, `OF:euro`, `OF:en.3`…). |
| `season` | VARCHAR | Season (`2025/26`) or tournament year (`2022`). |
| `round` | VARCHAR | Matchday or round as written by the source (`Matchday 1`, `Round of 16`). |
| `group_name` | VARCHAR | Group (tournaments). |
| `match_date` | DATE | Match date. |
| `kickoff` | VARCHAR | Kick-off time, local, as written by the source. |
| `home_name` | VARCHAR | Home team, as written by the source. |
| `away_name` | VARCHAR | Away team, as written by the source. |
| `home_club` | VARCHAR | Title of the home club's Wikipedia page in `club`; empty if no club of the competition has that name (and for national teams). |
| `away_club` | VARCHAR | Title of the away club's Wikipedia page in `club`; empty if no club matches (and for national teams). |
| `ft_home` | INTEGER | Home goals at the end of regular time. |
| `ft_away` | INTEGER | Away goals at the end of regular time. |
| `ht_home` | INTEGER | Home goals at half-time. |
| `ht_away` | INTEGER | Away goals at half-time. |
| `et_home` | INTEGER | Home goals after extra time (cumulative). |
| `et_away` | INTEGER | Away goals after extra time (cumulative). |
| `pen_home` | INTEGER | Penalty shoot-out goals scored by the home team. |
| `pen_away` | INTEGER | Penalty shoot-out goals scored by the away team. |
| `ground` | VARCHAR | Ground, as written by the source. |
| `attendance` | INTEGER | Attendance. |
| `referee` | VARCHAR | Main referee. |
| `source_ref` | VARCHAR | File of the OpenFootball repository the row comes from (or the Wikipedia page for a match created from its matrix). |
| `result_source` | VARCHAR | Where the score comes from: empty = the OpenFootball match source; `wikipedia` = the results matrix of the season's Wikipedia page (current season, when OpenFootball lags). On disagreement, the OpenFootball score is kept. |

### `match_competition`

Name of the `OF:*` competitions of `match` (those we do not have as a championship), read from the source file's header; in English.

- Files : `match_competition/match_competition.420f56fa.parquet` — **33 rows**
- Key : (code)

| Column | Type | Description |
|---|---|---|
| `code` | VARCHAR | Code `OF:<key>` as in `match.competition`. |
| `name` | VARCHAR | Competition name, without the year (`FIFA World Cup`, `English League One`). |
| `wikipedia_title` | VARCHAR | Title of the competition's English Wikipedia page; qualifiers reuse the page of the tournament they lead to. Empty for friendlies. |
| `logo_url` | VARCHAR | Logo thumbnail (the infobox `image` field, hosted by Wikimedia); often non-free: see `logo_license`. |
| `logo_license` | VARCHAR | Licence of the logo file, as declared by Wikimedia. |

### `match_goal`

Goalscorers of a match, when the source gives them (World Cups, Euros).

- Files : `match_goal/match_goal.1e2d8175.parquet` — **48 147 rows**
- Key : (match_id, seq)

| Column | Type | Description |
|---|---|---|
| `match_id` | INTEGER | Match (`match.match_id`). |
| `seq` | INTEGER | Rank of the goal in the source's list. |
| `side` | VARCHAR | `home` or `away`: the team the goal counts for (for an own goal, the team that benefits). |
| `player_name` | VARCHAR | Scorer's name, as written by the source. |
| `player_qid` | VARCHAR | Wikidata QID of the player of our database this name was matched to (the club's squad that season, unambiguously); empty otherwise: a name alone designates nobody. |
| `minute` | VARCHAR | Minute (`37`, `90+4`). |
| `kind` | VARCHAR | `goal`, `penalty` or `own_goal`. |

### `match_lineup`

Line-ups of a match, when the source gives them (6 championships: Premier League, Bundesliga, Liga, Serie A, Ligue 1, Austrian Bundesliga, since 2025/26).

- Files : `match_lineup/match_lineup.3554b000.parquet` — **56 249 rows**
- Key : (match_id, side, seq)

| Column | Type | Description |
|---|---|---|
| `match_id` | INTEGER | Match (`match.match_id`). |
| `side` | VARCHAR | `home` or `away`. |
| `seq` | INTEGER | Writing order of the source: the goalkeeper first, then the lines, then the substitutes. |
| `player_name` | VARCHAR | Name as written by the source (the case varies: `MOHAMED SALAH`, `Hugo EKITIKE`); no player key. |
| `player_qid` | VARCHAR | Wikidata QID of the player of our database this name was matched to (the club's squad that season, unambiguously); empty otherwise: a name alone designates nobody. |
| `role` | VARCHAR | `start` (starter) or `sub` (came on during the match). |
| `minute` | VARCHAR | Minute a substitute came on; for a replaced starter, the minute he went off; empty otherwise. |
| `captain` | BOOLEAN | Captain. |

### `match_card`

Cards of a match, when the source gives the detail.

- Files : `match_card/match_card.783a1d02.parquet` — **7 227 rows**
- Key : (match_id, seq)

| Column | Type | Description |
|---|---|---|
| `match_id` | INTEGER | Match (`match.match_id`). |
| `seq` | INTEGER | Rank in the source's list. |
| `side` | VARCHAR | `home` or `away`: the team of the booked player. |
| `player_name` | VARCHAR | Player, as written by the source. |
| `player_qid` | VARCHAR | Wikidata QID of the player of our database this name was matched to (the club's squad that season, unambiguously); empty otherwise: a name alone designates nobody. |
| `minute` | VARCHAR | Minute. |
| `kind` | VARCHAR | `yellow` or `red`. |

### `player_openfootball`

Height and birthplace from the `players` repository of OpenFootball (public domain), **only where the Wikipedia profile (`player_profile`) has none**: a Wikipedia value is never overwritten. A player is linked only by name AND exact birth date, never by name alone.

- Files : `player_openfootball/player_openfootball.337eb1e3.parquet` — **667 rows**
- Key : (player_qid)

| Column | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | Wikidata QID of the player (join key with `player_profile.player_qid`). |
| `height_cm` | INTEGER | Height in centimetres; empty if Wikipedia already has one. |
| `birth_place` | VARCHAR | Birthplace (city); empty if Wikipedia already has one. |

### `player_external_id`

External identifiers of a player read from Wikidata (never guessed): Transfermarkt (P2446) and FBref (P5750). One row per player that has at least one; they serve as outbound links.

- Files : `player_external_id/player_external_id.5905f6c1.parquet` — **61 835 rows**
- Key : (player_qid)

| Column | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | Wikidata QID of the player (join key with `player_profile.player_qid`). |
| `transfermarkt_id` | VARCHAR | Transfermarkt identifier (`https://www.transfermarkt.com/-/profil/spieler/<id>`); empty if none. |
| `fbref_id` | VARCHAR | FBref identifier (`https://fbref.com/en/players/<id>/`); empty if none. |

### `top_scorer`

Top scorers of each league and each season, read from the "Top scorers" table of the season's Wikipedia page (no other computation). The rank is recomputed from the goals (standard competition ranking: 1, 2, 2, 4).

- Files : `top_scorer/top_scorer.224e7cdf.parquet` — **1 757 rows**
- Key : (competition, season, rank, player_name)

| Column | Type | Description |
|---|---|---|
| `competition` | VARCHAR | Competition code (`ENG-PL`, `FRA-L1`…). |
| `season` | VARCHAR | Season, for example `2017/18`. |
| `rank` | INTEGER | Rank on goals; ties share the same rank. |
| `player_name` | VARCHAR | Player name as Wikipedia writes it. |
| `player_qid` | VARCHAR | Wikidata QID of the player when the database knows them, otherwise empty. |
| `club_name` | VARCHAR | Club as written in the table (the one of that season). |
| `club` | VARCHAR | Title of the club's Wikipedia page when known, otherwise empty (join with `club.wikipedia_title`). |
| `goals` | INTEGER | League goals scored. |

### `player_profile`

Profile read from the English Wikipedia infobox: full name, birthplace, height, death and **photo** (one row per player with at least one of these). Values **published as is by Wikipedia, unverified**.

- Files : `player_profile/player_profile.60cbf6cf.parquet` — **60 603 rows**
- Key : (player_qid or player)

| Column | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | Player's Wikidata QID (join key with `squad.player_qid`). |
| `player` | VARCHAR | Player name (fallback key: `'name:' || player` when `player_qid` is empty). |
| `full_name` | VARCHAR | Full name (`full_name` of the infobox). |
| `birth_place` | VARCHAR | Birthplace, as text (city, region, country). |
| `height_cm` | INTEGER | Height in cm (between 140 and 220, otherwise empty). |
| `death_date` | VARCHAR | Death date `YYYY-MM-DD` (or the year alone); empty for a living player. |
| `photo_caption` | VARCHAR | Caption of the infobox photo. |
| `photo_url` | VARCHAR | Thumbnail (300 px) of the infobox photo, for a living player; removed if the file's licence is non-free (`enrich --what photos`). |
| `photo_page` | VARCHAR | File page on Wikipedia / Wikimedia Commons (attribution and full licence). |
| `photo_license` | VARCHAR | Licence of the photo (`CC BY-SA 4.0`…); empty until it has been checked. |
| `photo_author` | VARCHAR | Author of the photo, as declared on the file page; empty until it has been checked. |

### `birth`

Birth dates (Wikidata P569) of identified players.

- Files : `birth/birth.8095f521.parquet` — **63 005 rows**
- Key : player_qid

| Column | Type | Description |
|---|---|---|
| `player_qid` | VARCHAR | Player's Wikidata QID. |
| `birth_date` | VARCHAR | Date formatted `YYYY-MM-DD` (text). |
| `precision` | INTEGER | Wikidata precision: 9 = year only, 10 = month, 11 = day. **An age is computed only if the precision is 11.** |

### `entity_wiki`

Wikipedia page of a club or a player in each language (en, fr, it, de, es for clubs; en, fr for players).

- Files : `entity_wiki/entity_wiki.83ce0dd9.parquet` — **100 720 rows**
- Key : (qid, lang)

| Column | Type | Description |
|---|---|---|
| `qid` | VARCHAR | Wikidata QID of the club or player. |
| `lang` | VARCHAR | Wikipedia language code. |
| `title` | VARCHAR | Title of the page in that language. |


## Work tables (`work`)

`work_*/` files of the manifest (`work` key): what the working database keeps beyond the Parquet files the website reads. They rebuild a COMPLETE database (`openfootball restore-db`) and are not read by the website. They carry natural keys (club title, season, player QID or name), never an internal number.

| Files | rows | Description |
|---|---|---|
| `work_squad_movement/work_squad_movement.d0266bbd.parquet` | 62 201 | player movements: date, transfer window, origin or destination club, loan or transfer |
| `work_loan_out/work_loan_out.73d10adf.parquet` | 24 139 | players loaned out elsewhere (not in their parent club's squad, hence not in `squad`) |
| `work_entity_label/work_entity_label.f36f4bd8.parquet` | 9 042 | English and French labels of Wikidata entities (cities, stadiums, leagues, clubs) |
| `work_player_alias/work_player_alias.c402c405.parquet` | 2 | name patches mapping a player name to their Wikipedia page |
| `work_amendment_log/work_amendment_log.0c2fe472.parquet` | 785 | log of corrections made to seasons or club-seasons |
| `work_competition_wikidata/work_competition_wikidata.e5980bb3.parquet` | 92 | Wikidata identifier of competitions |
| `work_club_work/work_club_work.94d61dcc.parquet` | 41 769 | Wikidata identifiers of clubs (country, city, stadium, league) whose labels are in `entity_label` |

