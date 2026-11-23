-- 0028 : classement des buteurs de chaque championnat et de chaque saison (tableau « Top scorers » de la page Wikipedia de la saison).
CREATE TABLE top_scorer (
  competition_code VARCHAR NOT NULL,   -- code de la compétition (ENG-PL, FRA-L1…)
  season_label     VARCHAR NOT NULL,   -- « 2017/18 »
  rank             INTEGER NOT NULL,   -- classement standard sur les buts (1, 2, 2, 4)
  player_name      VARCHAR NOT NULL,
  player_link      VARCHAR,            -- titre de la page Wikipedia du joueur
  player_qid       VARCHAR,            -- QID Wikidata, quand le joueur est connu de la base
  club_name        VARCHAR,
  club_id          INTEGER,
  goals            INTEGER NOT NULL,
  source_title     VARCHAR,
  PRIMARY KEY (competition_code, season_label, rank, player_name)
);
