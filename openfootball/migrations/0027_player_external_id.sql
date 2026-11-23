-- 0027 : identifiants externes des joueurs lus sur Wikidata (Transfermarkt P2446, FBref P5750) : des liens sortants fiables, jamais devinés.
-- Table à part (provenance claire) ; une ligne par joueur qui a au moins un identifiant.
CREATE TABLE player_external_id (
  player_id        INTEGER PRIMARY KEY,
  transfermarkt_id VARCHAR,       -- Wikidata P2446 : https://www.transfermarkt.com/-/profil/spieler/<id>
  fbref_id         VARCHAR        -- Wikidata P5750 : https://fbref.com/en/players/<id>/
);
