-- 0031 : carrière d'entraîneur d'après l'infobox de sa page Wikipedia anglaise (« Teams managed » : clubs ET sélections, adjoint compris),
-- une ligne par équipe dans l'ordre de l'infobox. Complète `club_coach` (mandats de Wikidata, clubs à effectifs seulement).
CREATE TABLE coach_career (
  coach_qid   VARCHAR NOT NULL,
  seq         INTEGER NOT NULL,
  start_year  INTEGER,
  end_year    INTEGER,           -- vide : en cours ou inconnue
  years_raw   VARCHAR NOT NULL,
  team_name   VARCHAR NOT NULL,
  team_link   VARCHAR,           -- titre de la page Wikipedia de l'équipe quand l'infobox la lie
  PRIMARY KEY (coach_qid, seq)
);
