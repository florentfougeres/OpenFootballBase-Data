-- 0032 : une ligne de l'infobox peut être un poste d'adjoint (« Italy (assistant) ») : on le marque pour ne pas le compter comme entraîneur principal d'un club.
ALTER TABLE coach_career ADD COLUMN assistant BOOLEAN;
