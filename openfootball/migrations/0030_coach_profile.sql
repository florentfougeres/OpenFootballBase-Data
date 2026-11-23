-- 0030 : fiche d'un entraîneur (Wikidata) : naissance (jour si la précision le permet, sinon l'année seule), lieu de naissance et pages Wikipedia.
-- Une ligne par entraîneur de `club_coach` ; les entraîneurs qui ont aussi joué ont en plus leur fiche joueur (même QID).
CREATE TABLE coach_profile (
  coach_qid     VARCHAR PRIMARY KEY,
  birth_date    DATE,            -- seulement quand Wikidata donne le jour (précision >= 11)
  birth_year    INTEGER,         -- l'année, quand la précision est celle de l'année
  birth_place   VARCHAR,         -- libellé anglais du lieu (P19)
  wikipedia_en  VARCHAR,         -- titre de la page anglaise
  wikipedia_fr  VARCHAR          -- titre de la page française
);
