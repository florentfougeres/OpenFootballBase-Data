# Changelog

[Français](../fr/changelog.md)

Published data releases, newest first. Names follow [semantic versioning](https://semver.org): **major** = incompatible schema change, **minor** = new data (league, country, cup, table, column), **patch** = data fixes. Each release is `Data X.Y.Z` with tag `data-X.Y.Z` ([how to publish](publishing-a-release.md)). Changes to the site and tooling that are not tied to a data release are listed under "Site and tooling".

## Next data release (unpublished)
- **Coaching career from the Wikipedia infobox** (`coach_career` table, migration 0031, filled by the `coaches` step): the "Teams managed" lines of each coach's English page, clubs **and national teams**, assistant roles included (36,676 lines for 3,862 coaches). The Wikidata tenures (`coach`) only cover the clubs with squads, so Hansi Flick showed two teams instead of five.
- **Coach profiles** (`coach_profile` table, migration 0030, filled by the `coaches` step): date of birth (the day when Wikidata gives it, otherwise the year), place of birth and the coach's Wikipedia pages (en, fr). Published only when `coaches` has read them.
- **The weekly run no longer touches the squads.** `reconcile` (identity merges, name changes, duplicate merges) is gone from `scripts/weekly_refresh.sh`: it is what created duplicate players in squads again after the weekly run (nine blocking `squad_duplicate` on 23 Nov). Squads only change at the transfer-window update, by hand; the script now fingerprints the squads after the restore and refuses to export if they changed. New manual command `clean-squads` (departures still listed, with the new case of the Spanish "Altas y bajas" lists: Rashford still at Barcelona 2026/27).
- **Coach nationality (flag)**: `coach` gets a `flag` column (new migration 0029), read from Wikidata with the coach tenures: country for sport (P1532, which gives "England" rather than the United Kingdom) and, failing that, citizenship (P27). Empty when Wikidata gives nothing recognisable. Filled by the next weekly run (`coaches` step).
- **Home: countries ranked by clubs with a real squad**: the per-country club count of the home file counted every club with a `club_season` row, even without a single player (results or standings only), so Bulgaria (53 clubs, 4 with a squad) and Poland ranked ahead of the Netherlands (30 of 31) and Turkey (43). It now counts the clubs that have players.
- **Images deleted from Wikimedia**: a player photo (Hamza Abdelkarim) whose file is deleted after it was read showed up broken on the site. The weekly run (`enrich --what imagecheck`) checks a quarter of the files per week, removes the vanished photos and puts back the current image of the player's page (failing that Wikidata's). The site no longer shows a broken image: the drawn logo or crest takes over.
- **Top scorers of every league and every season** (`topscorers`, new `top_scorer` table): read from the "Top scorers" table of the season's Wikipedia page, for the 9 top divisions from 2010/11 to the current season (153 rankings, 1,757 rows; 99% of the players linked to their QID). The rank is recomputed from the goals (1, 2, 2, 4); the goalkeepers' table (goals conceded) and any table not sorted from most to fewest goals are refused. The audit checks that every past season of the big five has one and that ranks follow goals. The weekly run re-reads the current season.
- **Transfermarkt and FBref identifiers of players** (`enrich --what playerids`, new `player_external_id` table): read from Wikidata (P2446, P5750) for players that have a QID: 61,835 players out of 63,377 (61,233 Transfermarkt, 46,735 FBref). Preferred foot is not added: Wikidata has it for fewer than 1% of players.
- **Two identities for one name in a squad**: of 26 cases, 9 were one person written two ways in two sources ("Christan" / "Christian" Enemark: same number, same position, nothing proving two people): merged; 17 are two real players with the same name (Henrique and Henrique at Portuguesa 2013/14) whose careers both contain the club: they are no longer flagged. The audit now only warns when the career really cannot tell.
- **Five scores disagreeing with Wikipedia (Ligue 1 2016/17 to 2019/20) settled**: with OpenFootball's scores, the goals for and against of each of the 20 teams give exactly the official final table; with the Wikipedia matrix's, they do not. They are no longer reported. Missing 2026/27 scores are filled when Wikipedia has them (14 more).
- **Club facts completed from Wikidata** (`enrich --what clubfacts`, added to the weekly run): missing colours, Transfermarkt/FBref/Soccerway/worldfootball identifiers and nickname, in empty cells only (on the current database: +54 colours, +215 Transfermarkt, +93 FBref, +68 Soccerway, +39 worldfootball, +111 nicknames).
- **Clubs: logo, colours and name are never modified by the weekly run**: they are frozen data (fixed by hand in the database). `imagecheck` used to remove club logos that disappeared from Wikimedia; it now only reports them, the site drawing a crest instead.

## Data 1.24.0 — 2026-11-21
- **The five first divisions and the Champions League, complete**: Premier League, Liga, Serie A, Bundesliga and Ligue 1 now have **every season from 2010/11 to 2025/26** (the Liga, Serie A and Ligue 1 had 15, 14 and 13: 3,420 more matches, without date or scorers for the seasons the match source does not have, taken from Wikipedia's results matrix), and the Champions League has its 15 editions from 2011/12 to 2025/26 (2020/21 to 2023/24 and 2025/26 added: OpenFootball's `champions-league` repository is read). The number of matches in each season is checked (380, 306, 125, 189…).
- **A club is no longer taken for another**: from 2013/14 to 2019/20, all of Lazio's matches ("Lazio Roma" in the source) were attached to the club AS Roma (266 matches): "Roma" is part of "Lazio Roma"; a name matched by its words can no longer take a club already recognised by its real name, nor be taken by two teams. The Champions League's Crvena Zvezda (20 matches without a club) is recognised.
- **Every score checked against a second source**: Wikipedia's results matrix is compared with OpenFootball's scores for the 16 seasons of the five leagues: 22,000 identical scores, 5 disagreements (OpenFootball is kept, they are printed). Scores the first source lacked are filled in (the last matchday of the 2024/25 Liga and Serie A, the 2024/25 Champions League final, 287 scores from October and November 2026); the 101 Ligue 1 2019/20 matches that were never played (season stopped by the pandemic) are removed from the calendar.
- **Players found in matches**: more scorers, starters and cards linked to a squad player (the name of their Wikipedia page counts too: "Fede" Valverde = Federico Valverde; "FUEHRICH" = Führich, "OREILLY" = O'Reilly, "LEE Jaesung" = Lee Jae-sung, "S. Esposito"). A substitute who is replaced in turn is no longer read as one name. Of the players fielded in 2025/26, 87 to 95% (depending on the league) are linked, up from 84 to 91%.
- **Squads**: 1,458 rows read from reserve, academy or Primavera sections ("Effectif de la réserve", "Équipe réserve", "Fiorentina Primavera", "Almería B players": 26 of Rennes' 60 "players" in 2018/19 were the reserve team) are removed and no longer read; 522 pages nothing references any more disappear.
- **Audit**: four new checks: `club_name_collision` and `match_goals_vs_score` (blocking), `season_match_count` and `match_unscored` (to review).

## Data 1.23.2 — 2026-11-21
- **One player, one page**: the same player read from two sources (English and French pages, different spellings) appeared twice in a squad: "Matvey" and "Matveï" Safonov at PSG, "Filip Šimeček" and "Filip Simecek" at Slavia. 320 duplicates inside one squad and 1,127 pages split between two seasons of the same club (one linked to its page, the other read without a link) are merged. Cautious rule: same words regardless of accents, or near-identical names with the same shirt number; never two different QIDs, two different shirt numbers, two different birth dates, or a stay that age or career rules out. 15 wrongly linked homonyms (two QIDs for the same place) lose their row when the other player's career proves the club; 25 pairs that nothing settles stay flagged.
- **Clean names**: 169 names cleared of wikicode leftovers (`note 2]`, `<small>(U18)</small>`, `†`, `}}}}`, "(footballer, born 1989)", quoted nicknames, "SURNAME, Given"). The squad reader applies the same rules: these names no longer come back.
- **Real players only**: 98 fake players removed (clubs, federations and country codes read from a column: "FRA", "AFC Ajax"; dates such as "January 1, 2022"; transfer notes; glued lists of surnames), 71 empty pages, 6 impossible birth dates (a saint born in 1515 taken for a Torino player; "born in 2100"). Scorer, brace and captain sections are no longer read as squads (the goal count stood in for the shirt number there: nine "Fernando Zampedri" at Universidad Católica).
- **Audit**: six new checks: `name_artifact`, `not_a_player`, `squad_duplicate` and `birth_impossible` (blocking), `squad_homonym` and `orphan_player` (to review). `reconcile` fixes them; the weekly refresh applies them on every run.

## Data 1.23.0 — 2026-11-18
- **More players with their own page**: players listed on a squad page without a link are now linked to their Wikipedia page by three more routes: the page titled `Name (footballer)` / `Name (soccer)`, the footballers listed on a disambiguation page (`Abdoulaye Cissé may refer to…`), and a career proof that accepts the youth years a player spent at the same club before his senior debut (Torino from 2017, career from 2019). About 440 more players identified (13,147 without identity before, 12,703 after, including the players recreated from loans).
- **Titles on the right club**: the champions of the Süper Lig 2004, 2010 (Fenerbahçe), 2017 and 2018 (Galatasaray) pointed to the multi-sport club, which has no squad, instead of the football club: relinked (5 rows).
- **Clean-ups**: dates and table values read as players on some squad pages ("3 May" in a suspensions table, "Loan") are removed and no longer read; 5 impossible appearance counts (a season year read as a number of matches, "2010 matches") are cleared.
- **Wrong squad rows removed**: 167 rows read from record tables on club pages ("Most appearances", "Retired numbers": legends born in 1954 in the 2026/27 squad) and 382 rows of nine past seasons (Cerezo Osaka 2011/12, Mönchengladbach 2010/11, Kaiserslautern 2003/04…) read from the club's own page, whose table is the *current* squad, are removed; those club-seasons are recorded as known gaps. Homonym links that the name, Wikidata and infobox merges can create are now undone at the end of the run, not only at the start.

## Data 1.22.0 — 2026-11-18
- **In-season movements and club labels are back**: the `stint_date`, `stint_window` and `stint_other_club` columns of the squads (date, window and origin club of transfers and loans) were empty in Data 1.21.0 and 1.21.1, and clubs had lost their city, stadium and league. A database rebuilt from a release did not carry them. They are filled again (31,351 squad rows with a movement or loan; 62,259 movements; 9,040 Wikidata labels).
- **Complete rebuilds** (new `work` key in the manifest, `work_*/` files, not read by the website): the release now carries the movements, the players loaned out, the Wikidata labels, the aliases and the correction log, with natural keys (club, season, player QID or name). `restore-db` reads them back; the weekly refresh refuses to rebuild from a release without them.
- **Players without a page**: 361 players linked to their Wikipedia page by name and proof of career, the club being recognised by its Wikidata identifier ("AS Nancy" = "AS Nancy Lorraine"; Ilyes Housni, among others). Names glued to a hidden sort key on French pages ("Akpa, ClémentClément Akpa") are repaired.

## Data 1.21.0 — 2026-11-18
- **Height and birthplace from OpenFootball** (new table `player_openfootball`, new command `players-data`): the `players` repository (public domain) fills the height or birthplace that Wikipedia does not have, for 651 players. A player is linked only by name **and exact birth date** (18,378 players linked, 640 ambiguous pairs left out); a Wikipedia value is never overwritten. The player page shows these values when Wikipedia has none.
- **Fixes in the match data** (published in 1.20.0): a score typed by hand on a Wikipedia season page for a match not yet played (Juventus–Venezia "0-10") is no longer taken: a score is refused for a match the calendar dates in the future, and so is a goal difference of 8 or more that no other source confirms. 35 Copa Libertadores 2020 matches that carried a 2027 date (the year was wrongly rolled over when a file lists matches by group) now have their real 2020 date.

## Data 1.20.0 — 2026-11-18
- **Matches** (new tables `match`, `match_goal`, `match_lineup`, `match_card`, `match_competition`; new command `matches`): 161,703 matches (155,515 played) of 73 competitions: 26 championships since 2010, the Champions League, World Cups, Euros, the Club World Cup, the Libertadores and Sudamericana, national-team matches since 1872 and a dozen other championships. Scores, half-times, extra time, penalty shoot-outs, grounds, and goalscorers (48,147 goals). The six big championships of 2025/26 also have line-ups with substitutions, cards, attendance and referee. Source: the open data of the OpenFootball project (CC0), a third source next to Wikipedia and Wikidata, used for matches only.
- **Current season completed from Wikipedia**: OpenFootball's automatic updates stopped in September, so the missing scores of the nine first divisions are read from the results matrix of the Wikipedia season pages (444 matches; `result_source` column of `match`). On the hundreds of matches present in both sources, the scores are identical.
- **Names matched to our data**: team names to our clubs (club aliases), and goalscorers, line-ups and cards to the squad players of the club that season when the name is unambiguous (`player_qid` columns).
- **Competition pages**: Wikipedia page and logo of the competitions that exist only in the match source (`match_competition`: `wikipedia_title`, `logo_url`, `logo_license`).
- **Fixes**: squad rows held by a player whose age or career rules them out (the 56-year-old "Fran González" of Deportivo listed at Real Madrid in 2025/26) are detached and re-identified: 499 rows found, 35 left (mostly records sections read as squads, to be fixed in the parser). New audit check `homonym_stay`.

## Data 1.19.0 — 2026-11-16
- **Coaches** (new table `coach`, new command `coaches`): the head-coach tenures of the clubs, with start and end dates, from Wikidata (8,091 tenures, 1,381 of the 2,815 clubs with squads; the big clubs are well covered, small ones less). The club page shows them in the side column, most recent first; a coach who was also a player in our data links to his player page.
- **Fixes**: 12 birth dates taken from the wrong Wikidata item are no longer shown (a player "born in 2026", a career that starts before the birth); 165 impossible goal counts are left empty (Wikipedia typos such as "11 matches, 100 goals"); statistics tables whose season cell carries a stray `!colspan` no longer shift their columns.

## Data 1.18.2 — 2026-11-16
- **Vacant titles**: Marseille 1992/93 (bribery scandal) and Juventus 2004/05 (Calciopoli) are no longer credited as league titles, as the federations declared them vacant (Marseille: 9 Ligue 1 titles, not 10). Wikidata still lists the club that finished first.

## Data 1.18.1 — 2026-11-16
- **Weekly refresh** (first run of `scripts/weekly_refresh.sh`): career infobox and statistics tables re-read for the 29,000 players still active (544,634 statistics rows).

## Data 1.18.0 — 2026-11-16
- **Cups and supercups in the honours**: 23 new competitions with their winners from Wikidata and the Wikipedia season pages — the national cups and league cups of England, Spain, France, Italy, Germany, the Netherlands, Portugal, Scotland, Turkey, Brazil and Argentina, the August supercups (Community Shield, Trophée des champions, DFL-Supercup, Johan Cruyff Shield), the UEFA Super Cup, the Cup Winners' Cup and the FIFA Club World Cup. 5,615 winners over 119 competitions in all (4,339 over 97 before). These competitions have no clubs or squads per season: only a palmarès (`competition.level = 5` for the national ones).
- **Wikipedia season page first**: from 2000/01, the winner written on the season page replaces a different winner given by Wikidata (21 corrections, for example two winners for a La Liga season).
- **Site**: the club page groups its titles into leagues, domestic cups and continental / international competitions (Real Madrid: 36 league titles, 20 Copa del Rey, 15 Champions Leagues…); the player page does the same for club titles. A competition page works for a cup (palmarès only).
- **Fix**: the winning national team of an edition is stored under its name ("West Germany", "Netherlands", "United States"), not under a code ("FRG", "NED", "US"), so that it gets its flag.
- Not included: the Spanish, Italian and Portuguese supercups (edition moved from August to January, years counted differently by Wikidata and Wikipedia) and the old Intercontinental Cup (no winner in its infobox).

## Data 1.17.0 — 2026-11-14
- **National-team titles** (new table `national_title`, new command `nationals`): for every edition of the World Cup (22 of 22), the European Championship (17 of 17), the Copa América (19 editions from 1975), the Africa Cup of Nations (34 of 35), the AFC Asian Cup (17 of 18), the Gold Cup (18) and the Confederations Cup (10), the players of the winning team, read from the Wikipedia squads page of the edition: 2,975 players. A player of the list may not have played. The player page shows them under "with the national team" (Patrick Vieira: World Cup 1998, Euro 2000, Confederations Cup 2001).
- **Site**: player search ranks well-known players first and tolerates typos ("ronaldo" finds Cristiano Ronaldo, "viera" and "patrick vieira" find Patrick Vieira, "mbape" finds Kylian Mbappé).

## Data 1.16.0 — 2026-11-14
- **Ballon d'Or** (new table `award`, new command `awards`): the ranking of every edition since 2000 (609 rows, 25 editions; no 2020 edition; 2010-2015 only the podium), read from the Wikipedia page of each edition. New "Ballon d'Or" page on the site with the winners and the edition-by-edition rankings, and the player page shows a player's Ballon d'Or wins and podiums.
- **Honours completed**: the winner of 655 more seasons read from the infobox of the Wikipedia season page when Wikidata does not record it (Ligue 1 2024/25, the UEFA Cup 2000-2008, small top flights…): 4,339 winners over 97 competitions. A Wikidata winner who is not among the participants of the season is dropped (Wikidata credited the Real Madrid with the MLS 2011 and 2012).
- **Player honours** on the site: the titles won with a club whose listed squad includes the player in the season of the title (an approximation, shown as such); **club honours** redesigned, with title chips in the club header.
- **Site**: Season / Honours tabs on a competition page; a bottom tab bar replaces the top-right menu on mobile; matches and goals in two columns in player statistics.

## Data 1.15.0 — 2026-11-14
- **Honours** (new table `winner`, new command `honours`): the winner of each season of 69 competitions, from Wikidata (3,730 winners): the main leagues back to their first seasons (Serie A from 1898, La Liga from 1929, Ligue 1 from 1932, Bundesliga from 1963, Eredivisie from 1888, Primeira Liga from 1934) and the Champions League from 1955. Seasons whose winner Wikidata does not record are absent (for example Ligue 1 2024/25). The site shows the winner of the season and the most successful clubs on each competition page, and the titles of a club on its page.
- **Dutch Wikipedia squads**: 11 more Eredivisie squads read (273 → 284 of 469 club-seasons), from the tables "Naam | Duels" as well; titles guessed even when Wikidata links another page.
- **Mid-season moves**: for 2,368 more squad rows, the club a player left and the club he joined in mid-season are marked (`left_mid` / `arrived_mid`), deduced from the chronological order of his career.
- **Site**: reconstructed squads (deduced from careers, not read from a page) carry a notice on the club page.
- 85,099 players, 327,375 squad entries and 479,110 career rows in total.

## Data 1.14.2 — 2026-11-14
- **Eredivisie squads from the Dutch Wikipedia** (`<club> in het seizoen YYYY/YY`): 32 more squads read (241 → 273 of 469 club-seasons), the first team only (departures, arrivals, youth and reserve-team tables are left out).
- **Partial squads from careers** extended to the Primeira Liga, La Liga and Ligue 1 (+3, +1, +5 club-seasons). The Primeira Liga has almost no club-season pages in Portuguese (2 of 292 missing).
- The database now holds 84,899 players, 326,795 squad entries and 478,872 career rows.

## Data 1.14.1 — 2026-11-14
- **Career statistics for 26,835 players** (736 more) and 911,338 club rows: tables cut short by a malformed reference tag (`<ref name="14/15"/>`), pages that write the columns in another order than their header (Sergei Ignashevich) and pages that title the section "Statistics" or "Club statistics" are now read.
- **Fix**: flags. Former Yugoslavia written "YUG 1992-2003" and East Germany "RDA" no longer fall back to a code without a flag; the flags of the Soviet Union, East Germany, Corsica, Brittany, the Netherlands Antilles and Guam are added to the site.

## Data 1.14.0 — 2026-11-14
- **UEFA Cup from 2000/01 to 2008/09 and Europa League 2009/10** (new option `uefa --cup UC`): the 32 clubs of the round of 32 up to 2002/03 and 2003/04, the 40-club group stage from 2004/05, then the 48 clubs of the 2009/10 Europa League (328 UEFA Cup participations, 48 Europa League ones).
- **Second divisions from 2000/01 to 2009/10** for England, France, Germany, Spain and Italy: 915 of 1,055 club-seasons with a squad.
- **Partial squads built from the players' careers** (`reconstruct --from-careers`): for 969 club-seasons without a Wikipedia page (Liga, Ligue 1, Süper Lig, Eredivisie, Primeira Liga, Belgian league, second divisions, continental cup clubs), the players whose statistics table or infobox places them at the club that season (at least 10 players). 18,061 rows, all marked `inferred`; the club-season keeps its documented gap.
- **Career statistics for 26,099 players**; the database now holds 84,679 players and 326,072 squad entries.
- **Fix**: the 2000-2003 English second division (then "Football League First Division"), the French "Division 2" before 2002 and the size of the Serie B (20, 24, then 22 clubs) are now recognised.

## Data 1.13.0 — 2026-11-14
- **UEFA Champions League from 2000/01 to 2009/10**: participants of the group stage (320 participations, 299 with a squad) and the squads of the clubs from every country, with the other top-flight seasons of the clubs already seen (`complete-clubs`). The Portugal, Netherlands, Belgium and Türkiye leagues are read back to 2000/01 (Türkiye 2000/01 has no page on Wikipedia).
- **Squads of the continental cup clubs** (new option `continental --squads`): Copa Libertadores 263 of 544 participations with a squad, CAF Champions League 103 of 226, AFC Champions League 339 of 552 (2010 → 2026). Clubs without a season page stay empty and are listed as gaps.
- **Career statistics for 23,923 players** (instead of 4,134): every player with an English Wikipedia page was read (42,740 pages), 797,717 club rows and 45,534 national-team rows.
- **Fix**: flags. 38,377 squad rows written in Dutch ("Vlag van Nederland"), two-letter codes ("AR"), adjectives ("German", "Swiss"), Turkish and Dutch names, and former countries (Serbia and Montenegro, FR Yugoslavia, Czechoslovakia) had no flag; only 67 rows of 259,346 are left without one (values that are not countries). The site no longer maps "Germany" to the retired code `dd`, and Trinidad and Tobago, Saint Kitts and Nevis, Antigua and Barbuda, Saint Lucia, Catalonia, the Basque Country and Galicia have their flag.
- **Fix**: a Wikipedia page without any revision (malformed title) no longer stops a whole batch.
- **Site**: tall full-length player photos are aligned to the top so the face stays visible; the Players page has a name search, position buttons with counts, removable filter chips and sortable columns; the career statistics panel opens expanded and has a redesigned national-team view; home-screen icon for phones.

## Data 1.12.0 — 2026-11-13
- **Career statistics** (new tables `stat_club`, `stat_national`, `stat_source`): appearances and goals by club, season and competition (league, national cup, league cup, continental, other), then by national team and year, read from the "Career statistics" section of the English Wikipedia page of 4,695 players of clubs from France, England, Italy, Spain, the Netherlands, Portugal and Germany in a Champions League season since 2010 (4,134 have a club table, 161,480 rows). Values as published, unverified. New "Career statistics" block on the player page: by season, by club, by competition, national team.
- **Player page**: the career totals use this table (all competitions) when it exists, instead of the infobox (league only).

## Data 1.11.0 — 2026-11-13
- **Seasons 2000/01 to 2009/10 for the five major leagues** (Premier League, La Liga, Serie A, Bundesliga, Ligue 1): 10 more seasons, 932 club-seasons, 789 squads read. Without a "club season" page on Wikipedia the squad stays empty and is listed as such (mostly La Liga and Ligue 1 before 2005).
- **Reconstructed squads** (new command `reconstruct`): when a club-season has no squad but its page lists transfers in and out, the squad is rebuilt as the previous season's squad minus departures plus arrivals. Rows are marked `inferred` (never `attested`) and the gap stays documented. First use: Holstein Kiel and VfL Bochum 2024/25.
- **Fix**: squad tables without a "No." column (Blackburn Rovers 2008/09) are now read.

## Data 1.10.1 — 2026-11-13
- **Fix**: status icons written as images (`[[File:Injury icon 2.svg|15px]]`) were read as players named "15px" or "14px" and hid the real player (Maccabi Haifa 2025/26-2026/27, San Lorenzo 2022/23-2024/25, Palmeiras 2014/15-2016/17, Santos 2016/17); the affected seasons were re-read.
- **Fix**: a surname written as a piped link is shown with the full page title ("Lloris" → "Hugo Lloris"); first names and nicknames are left as written.
- **Fix**: "Abou Kanté" (Stade Lavallois 2026/27) is linked to his page "Aboubakary Kanté".

## Data 1.10.0 — 2026-11-13
- **New competitions**: Copa Libertadores, CAF Champions League and AFC Champions League, participants of the group / league stage from 2010 to 2026 (list only; [guide](continental-cups.md)).
- **Fix**: pool championships were undercounted (China 2020 and 2021, Tunisia 2012, 2016 and 2021, Egypt 2012 and 2013): the group tables are now merged.

## Data 1.9.0 — 2026-11-13
- **20 countries in "list only" mode**: Mexico, Japan, Australia, China, South Korea, Colombia, Ecuador, Chile, Egypt, Peru, Morocco, South Africa, Qatar, United Arab Emirates, Paraguay, Uruguay, Bolivia, Algeria, Vietnam, Tunisia. First-division league and clubs of each season since 2010, no squads yet. For the open season without a season page, the league's generic page is read.

## Data 1.8.0 — 2026-11-13
- **UEFA Conference League**: participants and squads from 2021/22 to 2026/27, with the national leagues of its clubs. About half of the clubs of small countries have no "club season" page and stay "Without squad".

## Data 1.7.0 — 2026-11-13
- **New leagues**: Brazil (Série A) and Argentina (Primera División) from 2010 to 2026, squads read in English, Portuguese and Spanish (partial coverage: many clubs have no "club season" page).
- Summer departures removed from squads; player profiles (birthplace, height, photo).

## Data 1.6.1 — 2026-11-13
- **Squad fixes**: a player who left a club in the summer window (before 2 September) and is present in another club the same season is no longer listed in the former club (Lewandowski and Ferran Torres at Barça 2026/27; 1,003 rows over 17 seasons).

## Data 1.6.0 — 2026-11-13
- **Player profiles**: birthplace, height, full name, death and infobox photo (new table `player_profile`).

## Data 1.5.1 — 2026-11-13
- Removed the wrong logo of Athletic Newham (Wikipedia showed Atlético de Madrid's there).

## Data 1.5.0 — 2026-11-13
- **New**: Europa League, second divisions (ENG/ESP/FRA/DEU/ITA), MLS and Saudi Pro League, every club of the national leagues seen in a European cup, career clubs added.
- Squad fixes (Roster, current season, Jr/Junior duplicates).

## Data 1.4.0 — 2026-11-12
- `home.json` (instant home page), league logos in the competition table, loan statuses only for real loans (loan returns are no longer labelled loans), cross-club loan consistency.

## Data 1.3.0 — 2026-11-12
- Same content as 1.2.0; the `club` table is now ordered with squad clubs first in small row groups, so the site reads about 170 KB instead of 3.2 MB at start-up.

## Data 1.2.0 — 2026-11-12
- Squads are the union of all language pages; loans cross-checked between clubs (a loaned player is not listed by the lender); players absent from a squad page are never added; Wikidata identification of players without links; dated movements published in `squad_movement`. Data dictionary `SCHEMA.md` in the archive.

## Data 1.1.0 — 2026-11-12
- Squads are the union of every language page of the country (main source first), with provenance (`squad_source`, `squad.listed_in`).
- Fixed players merged by mistake (`sortname` `dab=` parameter), e.g. Schalke 04 2026/27 / Diogo Leite.
- Loaned-out players no longer in their parent club's squad.
- International caps and goals; club logos (17,000+); English names for non-Latin stadiums, leagues and cities; country reference with es/it/de names (flags).
- `SCHEMA.md`: data dictionary of the Parquet files.

## Data 1.0.0 — 2026-11-12
- **First public release**: 5 leagues (Premier League, La Liga, Serie A, Bundesliga, Ligue 1), seasons 2010/11 to 2026/27 (open), built from Wikipedia and Wikidata only. Parquet files + `manifest.json`; the site is deployed from this release.

## Site and tooling

### 2026-11-18
- **Complete rebuilds**: a database rebuilt from a release lost the movement detail (`squad_movement`: 62,319 rows), the players loaned out (24,238), the Wikidata labels of cities, stadiums and leagues (9,022), the aliases and the correction log. The weekly script rebuilds from the release on every run, so the `stint_date` / `stint_window` / `stint_other_club` columns of the squads were empty in recent releases and clubs lost their city, stadium and league. The export now writes these tables (`work` key of the manifest, natural keys, not read by the website) and `restore-db` reads them back; `recover-work` takes them from an older working database.
- **Players without a page**: the proof of career used to link a player without a link to the identified player of the same name now compares the clubs' Wikidata identifiers ("AS Nancy" = "AS Nancy Lorraine" = "Nancy") and ignores dots in initials ("A.S. Roma"): 361 players linked to their page (Ilyes Housni, among others). French pages rendered as HTML glued a hidden sort key to names ("Akpa, ClémentClément Akpa"): fixed in the parser and in existing names.
- **Two repositories**: this repository now holds the pipeline, the tests and the data releases; the website stays in [OpenFootballBase](https://github.com/florentfougeres/OpenFootballBase). Publishing a release starts the site deployment (`notify-site.yml`, secret `SITE_DEPLOY_TOKEN`). The Data 1.21.0 release was republished here identically; earlier releases stay in the website repository. Plan: [migration-two-repos.md](https://github.com/florentfougeres/OpenFootballBase/blob/main/docs/en/migration-two-repos.md).
- **Competitions page**: a Clubs view (by confederation, then a "World" section for intercontinental cups, no longer mixed with UEFA) and a National teams view (finals, qualifiers, friendlies), with icons and the competitions' Wikipedia logos; competitions known only from the match source sit in their continent.
- **Results tab** on every competition page: computed standings with form, matches by matchday with goalscorers; honours tab aligned with the club honours panel. Weekly script: `matches` (results, then current-season completion from Wikipedia) and `enrich --what leaguelogos` after it.

### 2026-11-16
- **Consistency audit** (`audit`): checks the whole database before every publication, run by the weekly script (a blocking problem stops it). Statistics: goal counts that are impossible (more than 3 per match and at least 10, typos in Wikipedia such as "11 matches, 100 goals") are now left empty instead of displayed; tables whose season cell carries a stray `!colspan` no longer shift the columns.
- **Weekly refresh** (`scripts/weekly_refresh.sh`, [weekly-refresh.md](weekly-refresh.md)): script for a server cron that re-reads the players still active (career infobox and statistics tables), exports and publishes a release. New option `stats --active`.

### 2026-11-13
- **Security and speed**: Content-Security-Policy; the DuckDB engine is verified by a SHA-384 integrity hash and its Parquet extension is hosted with the site (see [security.md](security.md), [website.md](https://github.com/florentfougeres/OpenFootballBase/blob/main/docs/en/website.md)); `restore-db` verifies every file's SHA-256; deployment downloads the release that triggered it; GitHub Actions pinned by SHA; Dependabot, secret scanning and push protection enabled.
- **Releases renamed** `Data X.Y.Z` with tag `data-X.Y.Z` (they used to be `data-v1` … `data-v13` with names like "Data v1.10.0 (date)").
- **Bilingual data dictionary** (`SCHEMA.md` in English, `SCHEMA.fr.md` in French) and bilingual documentation under `docs/fr/` and `docs/en/`; bilingual README.
- **Competitions page**: uniform grid grouped by confederation; continental cups appear under their confederation.
- **Site**: Players section (filters, CSV download), league trends dashboard, career timeline, club movements between seasons, unified club + squad page, coverage heat map.
- **Tooling**: `openfootball restore-db`, `openfootball continental`, `--fresh` mode and `tools/refresh.sh --fresh` for the transfer window.

### 2026-11-12
- Site rebuilt with Svelte 5 + Vite + Tailwind 4 (dark app style), generic navigation by country, fast home page, beta notice.
- Mid-season transfers and loan consistency (D13), Wikidata identification of players without links, MIT licence.
- Belgium, Portugal, Netherlands and Türkiye (nl and tr parsers on rendered HTML); current-season squad from the club page; Champions League participants (D14).
- Project renamed OpenFootballBase; first deployment to GitHub Pages.

### 2026-11-11
- Project started from zero (see [spec.md](spec.md), §2): pipeline, declarative scopes, frozen seasons, identity by Wikidata QID, careers from infoboxes, world clubs, logos.
