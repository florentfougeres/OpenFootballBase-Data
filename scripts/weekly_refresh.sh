#!/usr/bin/env bash
# Mise à jour hebdomadaire (cron) : relit les joueurs encore en activité (infobox de carrière + tableaux de statistiques Wikipedia),
# réconcilie, exporte et PUBLIE une release GitHub `data-X.Y.(Z+1)` puis redéploie le site.
# Usage : scripts/weekly_refresh.sh          (variables : REPO_DIR, RESUME=1 reprend un passage interrompu, PUBLISH=release|draft|none, défaut release ; draft = brouillon à publier à la main)
set -euo pipefail
cd "${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
export OPENFOOTBALL_CONTACT="https://github.com/florentfougeres/OpenFootballBase"
OF=.venv/bin/openfootball
DB=data/work/openfootball.duckdb
STAMP=$(date +%Y%m%d)
mkdir -p data/work/logs dist
exec > >(tee -a "data/work/logs/weekly_$STAMP.log") 2>&1

LOCK=data/work/weekly.lock                              # un seul passage à la fois (la base DuckDB n'a qu'un écrivain) ; mkdir est atomique, sans flock (absent de macOS)
mkdir "$LOCK" 2>/dev/null || { echo "déjà en cours (ou verrou périmé : rmdir $LOCK), abandon"; exit 0; }
trap 'rmdir "$LOCK"' EXIT

echo "##### début $(date +%FT%T)"
LAST=$(gh release list --limit 1 --json tagName -q '.[0].tagName')
# Une release d'avant la Data 1.22.0 n'a pas la clé « work » (mouvements, prêts, libellés…) : une base reconstruite depuis elle serait INCOMPLÈTE et la prochaine release
# publiée perdrait ces données. On refuse avant tout calcul ; republier d'abord depuis une base complète (openfootball recover-work, puis export).
mkdir -p /tmp/prev && gh release download "$LAST" --pattern "*-data.tar.gz" --dir /tmp/prev --clobber
tar -xzOf /tmp/prev/*-data.tar.gz manifest.json > /tmp/prev/manifest.json
grep -q '"work"' /tmp/prev/manifest.json || { echo "la release $LAST n'a pas de données de travail (clé work) : reconstruire depuis elle perdrait mouvements, prêts et libellés. Abandon."; exit 1; }
# RESUME=1 : reprend un passage interrompu sur la base de travail actuelle (sans la reconstruire ni relire les pages déjà lues) ; les étapes `enrich` et suivantes sont relancées.
if [ -z "${RESUME:-}" ]; then
# Base de travail reconstruite à chaque passage depuis la dernière release publiée : on repart toujours de ce que le site affiche, sans dérive ni reste d'un essai.
if [ -f "$DB" ]; then mv -f "$DB" data/work/openfootball.avant.duckdb; fi   # une seule copie de sécurité (la base d'avant), écrasée à chaque passage
$OF restore-db --release "$LAST" --db "$DB"

$OF careers --active --fresh                           # infobox de carrière + profil
$OF reconcile --names --wikidata --infobox --infobox-direct-only    # + pages Wikipedia retrouvées par le titre (lecture groupée, sans la recherche lente)
$OF stats --active --fresh --cache cache/wikipedia_stats_v2   # tableaux « Career statistics » des joueurs en activité, relus
fi

if [ -n "${RESUME:-}" ]; then
$OF enrich --what careerclubs labels imagecheck clubfacts playerids
else
$OF enrich --what players careerclubs labels imagecheck clubfacts playerids
fi
$OF coaches || echo "entraîneurs : échec ignoré (Wikidata indisponible), table de la release précédente conservée"   # mandats d'entraîneurs (Wikidata)
$OF matches --fresh-seasons 2 || echo "matchs : échec ignoré (GitHub indisponible), table de la release précédente conservée"   # résultats et buteurs (données ouvertes OpenFootball, CC0)
$OF topscorers --current-only || echo "buteurs : échec ignoré (Wikipedia indisponible), table de la release précédente conservée"   # classement des buteurs de chaque championnat (saison en cours relue)
$OF enrich --what leaguelogos                          # logos et pages Wikipedia des compétitions (y compris celles de `matches`, après lui : il crée leurs noms)
$OF players-data || echo "joueurs OpenFootball : échec ignoré, table de la release précédente conservée"   # taille et lieu de naissance manquants (nom + date de naissance)
$OF progress
$OF audit                                               # cohérence de toute la base : un problème bloquant arrête avant l'export

mkdir -p /tmp/prev && gh release download "$LAST" --pattern "*-data.tar.gz" --dir /tmp/prev --clobber
tar -xzOf /tmp/prev/*-data.tar.gz manifest.json > /tmp/prev/manifest.json
rm -rf dist/data && $OF export --out dist/data --archive dist/openfootballbase-data.tar.gz --previous /tmp/prev/manifest.json   # refuse si une saison figée a changé

if [ "${PUBLISH:-release}" != none ]; then
  IFS=. read -r MA MI PA <<<"${LAST#data-}"
  NEXT="$MA.$MI.$((PA + 1))"
  printf '# Data %s — %s\n**Weekly refresh**\nType: Patch release (data fixes)\n\n## Changed\n- Players still active: career infobox and statistics tables re-read.\n\n---\n\n# Data %s — %s\n**Mise à jour hebdomadaire**\nType : Correctif (corrections de données)\n\n## Modifié\n- Joueurs encore en activité : infobox de carrière et tableaux de statistiques relus.\n' \
    "$NEXT" "$(date +%F)" "$NEXT" "$(date +%F)" > dist/notes.md
  if [ "${PUBLISH:-release}" = draft ]; then DRAFT=--draft; else DRAFT=; fi
  gh release create "data-$NEXT" dist/openfootballbase-data.tar.gz $DRAFT --target main --title "Data $NEXT" --notes-file dist/notes.md
  # Le site se redéploie tout seul : la release publiée lance .github/workflows/notify-site.yml, qui lance le déploiement du dépôt OpenFootballBase (jeton SITE_DEPLOY_TOKEN).
  # Un brouillon (PUBLISH=draft) ne lance rien : le site se redéploie quand on le publie.
fi
echo "##### fin $(date +%FT%T)"
