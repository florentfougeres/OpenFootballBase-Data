#!/usr/bin/env python3
"""Empreinte des effectifs d'une base de travail : nombre de lignes `player_club_season` et somme de hachages de (club-saison, joueur, statut, numéro, poste).
Le passage hebdomadaire ne doit JAMAIS toucher aux effectifs (ils ne bougent qu'à la mise à jour du mercato) : le script compare l'empreinte avant et après.
Usage : squad_fingerprint.py <base.duckdb>"""
import sys
import duckdb

con = duckdb.connect(sys.argv[1], read_only=True)
n, h = con.execute("""SELECT count(*), coalesce(sum(hash(concat_ws('|', club_season_id, player_id, coalesce(stint, ''), coalesce(shirt_number::VARCHAR, ''), coalesce(position_code, '')))::HUGEINT), 0)
                      FROM player_club_season""").fetchone()
print(f"{n}:{h}")
