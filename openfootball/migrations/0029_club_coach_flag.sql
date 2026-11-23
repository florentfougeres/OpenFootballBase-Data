-- 0029 : nationalité de l'entraîneur (drapeau) : pays pour le sport (Wikidata P1532, ex. « England ») à défaut pays de citoyenneté (P27).
-- Une valeur par entraîneur, répétée sur ses mandats ; vide quand Wikidata ne donne rien de reconnaissable.
ALTER TABLE club_coach ADD COLUMN flag VARCHAR;
