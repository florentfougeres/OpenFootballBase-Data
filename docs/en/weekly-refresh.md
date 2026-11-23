# Weekly refresh of active players (server cron)

[Français](../fr/weekly-refresh.md)

`scripts/weekly_refresh.sh` keeps the players who are **still active** up to date (in a current squad, or with an open career line):

1. **rebuilds the working database from the latest published release** on every run (`restore-db`), so each run starts from exactly what the site shows; the previous database is moved to `data/work/openfootball.avant.duckdb` (a single copy, overwritten on every run; **since Data 1.22.0 the rebuild is complete**: the release carries the movements, loans, labels, aliases and corrections in its `work` key, see [restoring-a-database.md](restoring-a-database.md));
2. `careers --active --fresh`: re-reads the career infobox and profile, ignoring the cache;
3. `stats --active --fresh`: re-reads the "Career statistics" tables. **The weekly run never touches the squads** (no `reconcile`, no cleaning): they only change when the squads are updated at the transfer window, by hand (`openfootball clean-squads` removes the departures still listed). The script checks it: it fingerprints the squads right after the restore and **refuses to export** if they changed (`ALLOW_SQUAD_CHANGES=1` to go ahead knowingly);
4. `enrich --what players careerclubs labels imagecheck clubfacts playerids` (removes player photos deleted from Wikimedia since they were read and puts the current image back; never touches clubs: logo, colours and name are frozen; a quarter of the files per week), `coaches` (a Wikidata failure is tolerated: the previous table is kept), `matches --fresh-seasons 2` (OpenFootball results and goalscorers, then current-season scores completed from Wikipedia for the 9 first divisions; a network failure is tolerated), `topscorers --current-only` (top scorers of the current season; a failure is tolerated), `enrich --what leaguelogos` (logos and Wikipedia pages of the competitions, including those of `matches`), `players-data` (OpenFootball height and birthplace), `progress`, `audit` (a blocking problem stops the script before the export);
5. exports with `--previous` (refused if a frozen season changed) and **publishes** a GitHub release `data-X.Y.(Z+1)` (patch bump of the latest one), then the site redeploys by itself (`notify-site.yml`, token `SITE_DEPLOY_TOKEN`: see [publishing-a-release.md](publishing-a-release.md)).

A lock (`data/work/weekly.lock`) prevents two runs at once (DuckDB has a single writer). Log: `data/work/logs/weekly_YYYYMMDD.log`.

## Server setup (Ubuntu)

```bash
git clone https://github.com/florentfougeres/OpenFootballBase-Data && cd OpenFootballBase-Data
python3 -m venv .venv && .venv/bin/pip install -e .
gh auth login        # token with the minimal scope to create releases; keep it outside the repository
crontab -e           # then add the line below: Monday 03:00
```

```cron
0 3 * * 1 /home/USER/OpenFootballBase-Data/scripts/weekly_refresh.sh
```

## Publishing

By default the release is **published** and the site redeployed (the continuity guard `--previous` refuses a bad export first). `PUBLISH=draft` creates a draft to publish by hand (`gh release edit data-X.Y.Z --draft=false`), `PUBLISH=none` stops after the export. Release notes are generic; add the changelog entry by hand when something notable changes. A first run is long (thousands of pages); the following ones only re-read the active players.
