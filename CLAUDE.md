# Project rules for Claude Code

This repository is the **data** repository: the Python pipeline, the tests and the releases (`Data X.Y.Z`). The website is in the sibling repository `OpenFootballBase` (`../OpenFootball`), which has its own `CLAUDE.md`.

- **Documentation is bilingual — always.** Any change to `README.md` must be mirrored in `README.fr.md`, and any change to a page under `docs/en/` must be mirrored in the same file under `docs/fr/` (and vice versa). This includes `spec.md`, `roadmap.md` and `changelog.md`. New docs go in both indexes (`docs/en/README.md`, `docs/fr/README.md`). Data-dictionary descriptions go in both `openfootball/schema_doc.py` and `openfootball/schema_doc_en.py`.
- **Releases**: tag `data-X.Y.Z`, title exactly `Data X.Y.Z` (no "v", no date). Release notes use the common template (English then French, see `docs/en/publishing-a-release.md`). Add a changelog entry in both languages. Publishing a release starts the site deployment (`notify-site.yml`, secret `SITE_DEPLOY_TOKEN`: fine-grained token, expires in one year at most).
- **Commit and push only when the user asks** ("Commit" = commit only, "Commit push" = commit and push). Never commit databases or caches (`data/work/`, `cache/`, `dist*/`).
- **Contact in the User-Agent** is always `OPENFOOTBALL_CONTACT="https://github.com/florentfougeres/OpenFootballBase"`, never a personal e-mail.
- Do not propose `enrich --what photos`.
- One writing command at a time on the DuckDB database; back it up before long or destructive runs.
