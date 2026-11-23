# Journal des changements

[English](../en/changelog.md)

Les releases de données publiées, la plus récente d'abord. Les noms suivent le [versionnage sémantique](https://semver.org/lang/fr/) : **majeure** = changement de schéma incompatible, **mineure** = nouvelles données (championnat, pays, coupe, table, colonne), **correctif** = corrections de données. Chaque release s'appelle `Data X.Y.Z` avec le tag `data-X.Y.Z` ([comment publier](publishing-a-release.md)). Les changements du site et des outils qui ne sont pas liés à une release de données sont listés sous « Site et outils ».

## Prochaine release de données (non publiée)
- **Fiches d'entraîneurs** (table `coach_profile`, migration 0030, remplie par l'étape `coaches`) : date de naissance (le jour quand Wikidata le donne, sinon l'année), lieu de naissance et pages Wikipedia de l'entraîneur (en, fr). Publiée seulement quand `coaches` les a lues.
- **Le passage hebdomadaire ne touche plus aux effectifs.** `reconcile` (fusions d'identités, changements de noms, fusions de doublons) disparaît de `scripts/weekly_refresh.sh` : c'est lui qui recréait des doublons de joueurs dans les effectifs après le passage (neuf `squad_duplicate` bloquants le 23 nov.). Les effectifs ne changent qu'à la mise à jour du mercato, à la main ; le script prend maintenant l'empreinte des effectifs après la restauration et refuse d'exporter s'ils ont changé. Nouvelle commande manuelle `clean-squads` (départs restés listés, avec le nouveau cas des listes espagnoles « Altas y bajas » : Rashford encore au Barça 2026/27).
- **Nationalité des entraîneurs (drapeau)** : `coach` reçoit une colonne `flag` (nouvelle migration 0029), lue sur Wikidata avec les mandats : pays pour le sport (P1532, qui donne « England » plutôt que le Royaume-Uni) puis, à défaut, citoyenneté (P27). Vide quand Wikidata ne donne rien de reconnaissable. Remplie au prochain passage hebdomadaire (étape `coaches`).
- **Accueil : pays classés par clubs avec un vrai effectif** : le nombre de clubs par pays du fichier d'accueil comptait tout club ayant une ligne `club_season`, même sans un seul joueur (résultats ou classement seulement) ; la Bulgarie (53 clubs, 4 avec un effectif) et la Pologne passaient donc avant les Pays-Bas (30 sur 31) et la Turquie (43). Il compte maintenant les clubs qui ont des joueurs.
- **Images supprimées de Wikimedia** : une photo de joueur (Hamza Abdelkarim) dont le fichier est supprimé après la lecture s'affichait cassée sur le site. Le passage hebdomadaire (`enrich --what imagecheck`) contrôle un quart des fichiers par semaine, retire les photos disparues et remet l'image actuelle de la page du joueur (à défaut celle de Wikidata). Le site, lui, n'affiche plus d'image cassée : le logo ou l'écusson dessiné prend le relais.
- **Classement des buteurs de chaque championnat et de chaque saison** (`topscorers`, nouvelle table `top_scorer`) : lu dans le tableau « Top scorers » de la page Wikipedia de la saison, pour les 9 premières divisions de 2010/11 à la saison en cours (153 classements, 1 757 lignes ; 99 % des joueurs reliés à leur QID). Le rang est recalculé sur les buts (1, 2, 2, 4) ; le tableau des gardiens (buts encaissés) et tout tableau non trié du plus au moins de buts sont refusés. L'audit vérifie que chaque saison passée des cinq grands championnats a le sien et que les rangs suivent les buts. Le passage hebdomadaire relit la saison en cours.
- **Identifiants Transfermarkt et FBref des joueurs** (`enrich --what playerids`, nouvelle table `player_external_id`) : lus sur Wikidata (P2446, P5750) pour les joueurs qui ont un QID : 61 835 joueurs sur 63 377 (61 233 Transfermarkt, 46 735 FBref). Le pied fort n'est pas ajouté : Wikidata ne le renseigne que pour moins de 1 % des joueurs.
- **Deux identités pour un même nom dans un effectif** : sur 26 cas, 9 étaient une même personne écrite de deux façons dans deux sources (« Christan » / « Christian » Enemark : même numéro, même poste, aucun lien prouvant deux personnes) : fusionnés ; 17 sont deux vrais joueurs du même nom (Henrique et Henrique à Portuguesa 2013/14) dont les carrières contiennent toutes deux le club : ils ne sont plus signalés. L'audit n'avertit plus que des cas où la carrière ne tranche vraiment pas.
- **Cinq scores en désaccord avec Wikipedia (Ligue 1 2016/17 à 2019/20) tranchés** : avec les scores d'OpenFootball, les buts marqués et encaissés de chacune des 20 équipes redonnent exactement le classement final officiel ; avec ceux de la matrice Wikipedia, non. Ils ne sont plus signalés. Les scores 2026/27 manquants sont complétés quand Wikipedia les a (14 de plus).
- **Faits de clubs complétés depuis Wikidata** (`enrich --what clubfacts`, ajouté au passage hebdomadaire) : couleurs, identifiants Transfermarkt/FBref/Soccerway/worldfootball et surnom manquants, uniquement dans les cases vides (sur la base actuelle : +54 couleurs, +215 Transfermarkt, +93 FBref, +68 Soccerway, +39 worldfootball, +111 surnoms).
- **Clubs : logo, couleurs et nom ne sont jamais modifiés par le passage hebdomadaire** : ce sont des données figées (corrigées à la main dans la base). `imagecheck` ne retirait plus que les logos de clubs disparus de Wikimedia ; il les signale désormais seulement, le site dessinant un écusson à la place.

## Data 1.24.0 — 2026-11-21
- **Les cinq premières divisions et la Ligue des champions, complètes** : Premier League, Liga, Serie A, Bundesliga et Ligue 1 ont maintenant **toutes leurs saisons de 2010/11 à 2025/26** (la Liga, la Serie A et la Ligue 1 en avaient 15, 14 et 13 : 3 420 matchs de plus, sans date ni buteurs pour les saisons que la source de matchs n'a pas, d'après la matrice de résultats de Wikipedia), et la Ligue des champions a ses 15 éditions de 2011/12 à 2025/26 (2020/21 à 2023/24 et 2025/26 en plus : le dépôt `champions-league` d'OpenFootball est lu). Le nombre de matchs de chaque saison est contrôlé (380, 306, 125, 189…).
- **Un club n'est plus pris pour un autre** : de 2013/14 à 2019/20, tous les matchs de la Lazio (« Lazio Roma » dans la source) étaient rattachés au club AS Roma (266 matchs) : « Roma » est un morceau de « Lazio Roma » ; un nom rapproché par ses mots ne peut plus prendre un club déjà reconnu par son vrai nom, ni être pris par deux équipes. Le Crvena Zvezda de la Ligue des champions (20 matchs sans club) est reconnu.
- **Chaque score vérifié par une seconde source** : la matrice de résultats de Wikipedia est comparée aux scores d'OpenFootball pour les 16 saisons des cinq championnats : 22 000 scores identiques, 5 désaccords (OpenFootball est gardé, ils sont affichés). Les scores que la première source n'avait pas sont complétés (la dernière journée de la Liga et de la Serie A 2024/25, la finale de la Ligue des champions 2024/25, 287 scores d'octobre et novembre 2026) ; les 101 matchs de Ligue 1 2019/20 jamais joués (saison arrêtée par la pandémie) sont retirés du calendrier.
- **Joueurs retrouvés dans les matchs** : plus de buteurs, de titulaires et de cartons rattachés à un joueur de l'effectif (le nom de sa page Wikipedia compte aussi : « Fede » Valverde = Federico Valverde ; « FUEHRICH » = Führich, « OREILLY » = O'Reilly, « LEE Jaesung » = Lee Jae-sung, « S. Esposito »). Un remplaçant remplacé à son tour n'est plus lu comme un seul nom. Parmi les joueurs alignés en 2025/26, 87 à 95 % (selon le championnat) sont rattachés, contre 84 à 91 %.
- **Effectifs** : 1 458 lignes lues dans des sections de réserve, de centre de formation ou de Primavera (« Effectif de la réserve », « Équipe réserve », « Fiorentina Primavera », « Almería B players » : 26 des 60 « joueurs » de Rennes 2018/19 étaient la réserve) sont retirées et ne sont plus lues ; 522 fiches que plus rien ne référence disparaissent.
- **Audit** : quatre nouveaux contrôles : `club_name_collision` et `match_goals_vs_score` (bloquants), `season_match_count` et `match_unscored` (à relire).

## Data 1.23.2 — 2026-11-21
- **Un joueur, une fiche** : un même joueur lu dans deux sources (pages anglaise et française, graphies différentes) apparaissait deux fois dans un effectif : « Matvey » et « Matveï » Safonov au PSG, « Filip Šimeček » et « Filip Simecek » au Slavia. 320 doublons d'un même effectif et 1 127 fiches coupées entre deux saisons d'un même club (l'une liée à sa page, l'autre lue sans lien) sont fusionnés. Règle prudente : mêmes mots à l'accent près, ou noms presque identiques avec le même numéro ; jamais deux QID différents, deux numéros différents, deux dates de naissance différentes ni un séjour que l'âge ou la carrière interdit. 15 homonymes liés à tort (deux QID pour la même place) perdent leur ligne quand la carrière de l'autre prouve le club ; 25 paires que rien ne tranche restent signalées.
- **Des noms propres** : 169 noms nettoyés des restes de wikicode (`note 2]`, `<small>(U18)</small>`, `†`, `}}}}`, « (footballer, born 1989) », surnoms entre guillemets, « NOM, Prénom »). Le lecteur d'effectifs applique les mêmes règles : ces noms ne reviennent plus.
- **De vrais joueurs seulement** : 98 faux joueurs retirés (clubs, fédérations et codes pays lus dans une colonne : « FRA », « AFC Ajax » ; dates « January 1, 2022 » ; notes de transfert ; listes de noms de famille collées), 71 fiches vides, 6 dates de naissance impossibles (un saint né en 1515 pris pour un joueur du Torino ; « né en 2100 »). Les sections de buteurs, de doublés et de capitaines ne sont plus lues comme des effectifs (le nombre de buts y tenait lieu de numéro de maillot : neuf « Fernando Zampedri » à l'Universidad Católica).
- **Audit** : six nouveaux contrôles : `name_artifact`, `not_a_player`, `squad_duplicate` et `birth_impossible` (bloquants), `squad_homonym` et `orphan_player` (à relire). `reconcile` les corrige ; la mise à jour hebdomadaire les applique à chaque passage.

## Data 1.23.0 — 2026-11-18
- **Plus de joueurs avec leur propre fiche** : les joueurs listés sur une page d'effectif sans lien sont rattachés à leur page Wikipedia par trois voies de plus : la page au titre `Nom (footballer)` / `Nom (soccer)`, les footballeurs listés sur une page d'homonymie (`Abdoulaye Cissé may refer to…`), et une preuve de carrière qui accepte les années de jeunes passées dans le même club avant les débuts « senior » (Torino dès 2017, carrière dès 2019). Environ 440 joueurs de plus identifiés (13 147 sans identité avant, 12 703 après, y compris les joueurs recréés depuis les prêts).
- **Titres sur le bon club** : les champions de Süper Lig 2004 et 2010 (Fenerbahçe), 2017 et 2018 (Galatasaray) pointaient vers le club omnisports, qui n'a pas d'effectif, au lieu du club de football : rattachés (5 lignes).
- **Nettoyages** : les dates et valeurs de tableau lues comme des joueurs sur certaines pages d'effectif (« 3 May » dans un tableau de suspensions, « Loan ») sont retirées et ne sont plus lues ; 5 nombres de matchs impossibles (l'année de la saison lue comme un nombre de matchs, « 2010 matches ») sont vidés.
- **Fausses lignes d'effectif retirées** : 167 lignes lues dans des tableaux de records de pages de clubs (« Most appearances », « Retired numbers » : des légendes nées en 1954 dans l'effectif 2026/27) et 382 lignes de neuf saisons passées (Cerezo Osaka 2011/12, Mönchengladbach 2010/11, Kaiserslautern 2003/04…) lues sur la page du club lui-même, dont le tableau est l'effectif *actuel*, sont retirées ; ces club-saisons sont enregistrés comme trous connus. Les liens vers un homonyme que les fusions par nom, Wikidata et infobox peuvent créer sont maintenant défaits à la FIN du passage, et plus seulement au début.

## Data 1.22.0 — 2026-11-18
- **Les mouvements en cours de saison et les libellés de clubs reviennent** : les colonnes `stint_date`, `stint_window` et `stint_other_club` des effectifs (date, fenêtre et club d'origine des transferts et prêts) étaient vides dans les Data 1.21.0 et 1.21.1, et les clubs avaient perdu leur ville, leur stade et leur championnat. Une base reconstruite depuis une release ne les portait pas. Elles sont de nouveau remplies (31 351 lignes d'effectif avec un mouvement ou un prêt ; 62 259 mouvements ; 9 040 libellés Wikidata).
- **Reconstructions complètes** (nouvelle clé `work` du manifeste, fichiers `work_*/`, non lus par le site) : la release porte maintenant les mouvements, les joueurs prêtés ailleurs, les libellés Wikidata, les alias et le journal des corrections, avec des clés naturelles (club, saison, QID ou nom du joueur). `restore-db` les relit ; la mise à jour hebdomadaire refuse de reconstruire depuis une release qui n'en a pas.
- **Joueurs sans fiche** : 361 joueurs rattachés à leur page Wikipedia par leur nom et une preuve de carrière, le club étant reconnu par son identifiant Wikidata (« AS Nancy » = « AS Nancy Lorraine » ; Ilyes Housni, entre autres). Les noms collés à une clé de tri cachée sur les pages françaises (« Akpa, ClémentClément Akpa ») sont réparés.

## Data 1.21.0 — 2026-11-18
- **Taille et lieu de naissance d'OpenFootball** (nouvelle table `player_openfootball`, nouvelle commande `players-data`) : le dépôt `players` (domaine public) complète la taille ou le lieu de naissance que Wikipedia n'a pas, pour 651 joueurs. Un joueur n'est relié que par son nom **et sa date de naissance exacte** (18 378 joueurs reliés, 640 couples ambigus écartés) ; une valeur de Wikipedia n'est jamais écrasée. La fiche joueur affiche ces valeurs quand Wikipedia n'en a pas.
- **Corrections des données de matchs** (publiées en 1.20.0) : un score saisi à la main sur une page de saison de Wikipedia pour un match pas encore joué (Juventus–Venezia « 0-10 ») n'est plus repris : un score est refusé pour un match que le calendrier date dans le futur, et un écart de 8 buts ou plus qu'aucune autre source ne confirme l'est aussi. 35 matchs de la Copa Libertadores 2020 qui portaient une date de 2027 (l'année passait à tort à la suivante quand un fichier liste les matchs par groupe) ont retrouvé leur vraie date de 2020.

## Data 1.20.0 — 2026-11-18
- **Matchs** (nouvelles tables `match`, `match_goal`, `match_lineup`, `match_card`, `match_competition` ; nouvelle commande `matches`) : 161 703 matchs (155 515 joués) de 73 compétitions : 26 championnats depuis 2010, Ligue des champions, Coupes du monde, Euros, Coupe du monde des clubs, Libertadores et Sudamericana, matchs de sélections depuis 1872 et une douzaine d'autres championnats. Scores, mi-temps, prolongations, tirs au but, stades et buteurs (48 147 buts). Les six grands championnats de 2025/26 ont aussi les compositions avec remplacements, les cartons, l'affluence et l'arbitre. Source : les données ouvertes du projet OpenFootball (CC0), troisième source à côté de Wikipedia et Wikidata, pour les matchs seulement.
- **Saison en cours complétée depuis Wikipedia** : la mise à jour automatique d'OpenFootball s'est arrêtée en septembre ; les scores qui manquent aux neuf premières divisions sont lus dans la matrice de résultats des pages Wikipedia de saison (444 matchs ; colonne `result_source` de `match`). Sur les centaines de matchs présents dans les deux sources, les scores sont identiques.
- **Noms rattachés à nos données** : équipes à nos clubs (alias de clubs), buteurs, compositions et cartons aux joueurs de l'effectif du club cette saison-là quand le nom est sans ambiguïté (colonnes `player_qid`).
- **Pages de compétitions** : page Wikipedia et logo des compétitions qui n'existent que dans la source de matchs (`match_competition` : `wikipedia_title`, `logo_url`, `logo_license`).
- **Corrections** : les lignes d'effectif tenues par un joueur que son âge ou sa carrière exclut (le « Fran González » de 56 ans du Deportivo, listé au Real Madrid en 2025/26) sont détachées et ré-identifiées : 499 lignes trouvées, 35 restantes (surtout des rubriques de records lues comme des effectifs, à corriger dans le parseur). Nouveau contrôle d'audit `homonym_stay`.

## Data 1.19.0 — 2026-11-16
- **Entraîneurs** (nouvelle table `coach`, nouvelle commande `coaches`) : les mandats d'entraîneur des clubs, avec dates de début et de fin, d'après Wikidata (8 091 mandats, 1 381 des 2 815 clubs à effectifs ; les grands clubs sont bien couverts, les petits moins). La fiche club les montre dans la colonne de droite, le plus récent d'abord ; un entraîneur qui a aussi été joueur dans nos données mène à sa fiche.
- **Corrections** : 12 dates de naissance prises sur le mauvais élément Wikidata ne sont plus affichées (un joueur « né en 2026 », une carrière qui commence avant la naissance) ; 165 nombres de buts impossibles sont laissés vides (fautes de frappe de Wikipedia comme « 11 matchs, 100 buts ») ; les tableaux de statistiques dont la cellule de saison porte un `!colspan` parasite ne décalent plus leurs colonnes.

## Data 1.18.2 — 2026-11-16
- **Titres vacants** : Marseille 1992/93 (affaire VA-OM) et la Juventus 2004/05 (Calciopoli) ne sont plus comptés comme titres de champion, les fédérations les ayant déclarés vacants (Marseille : 9 titres de Ligue 1, pas 10). Wikidata cite encore le club arrivé premier.

## Data 1.18.1 — 2026-11-16
- **Mise à jour hebdomadaire** (premier passage de `scripts/weekly_refresh.sh`) : infobox de carrière et tableaux de statistiques relus pour les 29 000 joueurs encore en activité (544 634 lignes de statistiques).

## Data 1.18.0 — 2026-11-16
- **Coupes et supercoupes dans le palmarès** : 23 nouvelles compétitions avec leurs vainqueurs, d'après Wikidata et les pages de saison Wikipedia — les coupes nationales et coupes de la Ligue de l'Angleterre, de l'Espagne, de la France, de l'Italie, de l'Allemagne, des Pays-Bas, du Portugal, de l'Écosse, de la Turquie, du Brésil et de l'Argentine, les supercoupes d'août (Community Shield, Trophée des champions, DFL-Supercup, Johan Cruyff Shield), la Supercoupe de l'UEFA, la Coupe des coupes et la Coupe du monde des clubs. 5 615 vainqueurs sur 119 compétitions au total (4 339 sur 97 avant). Ces compétitions n'ont ni clubs ni effectifs par saison : seulement un palmarès (`competition.level = 5` pour les nationales).
- **La page de saison Wikipedia d'abord** : à partir de 2000/01, le vainqueur écrit sur la page de la saison remplace un vainqueur différent donné par Wikidata (21 corrections, par exemple deux vainqueurs pour une saison de Liga).
- **Site** : la page d'un club regroupe ses titres en championnats, coupes nationales et compétitions continentales ou internationales (Real Madrid : 36 championnats, 20 Coupes du Roi, 15 Ligues des champions…) ; la fiche joueur fait de même pour les titres de club. La page d'une compétition fonctionne pour une coupe (palmarès seulement).
- **Correction** : l'équipe nationale victorieuse d'une édition est enregistrée sous son nom (« West Germany », « Netherlands », « United States »), pas sous un code (« FRG », « NED », « US »), pour avoir son drapeau.
- Non inclus : les supercoupes d'Espagne, d'Italie et du Portugal (édition passée d'août à janvier, années comptées différemment par Wikidata et Wikipedia) et l'ancienne Coupe intercontinentale (pas de vainqueur dans son infobox).

## Data 1.17.0 — 2026-11-14
- **Titres en équipe nationale** (nouvelle table `national_title`, nouvelle commande `nationals`) : pour chaque édition de la Coupe du monde (22 sur 22), du Championnat d'Europe (17 sur 17), de la Copa América (19 éditions depuis 1975), de la Coupe d'Afrique des nations (34 sur 35), de la Coupe d'Asie (17 sur 18), de la Gold Cup (18) et de la Coupe des confédérations (10), les joueurs de l'équipe victorieuse, lus sur la page Wikipedia des effectifs de l'édition : 2 975 joueurs. Un joueur de la liste a pu ne pas jouer. La fiche joueur les montre sous « en équipe nationale » (Patrick Vieira : Coupe du monde 1998, Euro 2000, Coupe des confédérations 2001).
- **Site** : la recherche de joueurs classe d'abord les joueurs connus et tolère les fautes de frappe (« ronaldo » trouve Cristiano Ronaldo, « viera » et « patrick vieira » trouvent Patrick Vieira, « mbape » trouve Kylian Mbappé).

## Data 1.16.0 — 2026-11-14
- **Ballon d'Or** (nouvelle table `award`, nouvelle commande `awards`) : le classement de chaque édition depuis 2000 (609 lignes, 25 éditions ; pas d'édition en 2020 ; de 2010 à 2015 seulement le podium), lu sur la page Wikipedia de chaque édition. Nouvelle page « Ballon d'Or » sur le site avec les lauréats et les classements édition par édition ; la fiche d'un joueur montre ses Ballons d'Or et ses podiums.
- **Palmarès complété** : le vainqueur de 655 saisons de plus, lu dans l'infobox de la page Wikipedia de la saison quand Wikidata ne le renseigne pas (Ligue 1 2024/25, Coupe UEFA 2000-2008, petits championnats…) : 4 339 vainqueurs sur 97 compétitions. Un vainqueur Wikidata qui ne figure pas parmi les participants de la saison est écarté (Wikidata créditait le Real Madrid de la MLS 2011 et 2012).
- **Palmarès des joueurs** sur le site : les titres remportés avec un club dont l'effectif listé inclut le joueur la saison du titre (une approximation, présentée comme telle) ; **palmarès des clubs** refait, avec des pastilles de titres dans l'en-tête du club.
- **Site** : onglets Saison / Palmarès sur la page d'une compétition ; une barre d'onglets en bas remplace le menu en haut à droite sur mobile ; matchs et buts en deux colonnes dans les statistiques des joueurs.

## Data 1.15.0 — 2026-11-14
- **Palmarès** (nouvelle table `winner`, nouvelle commande `honours`) : le vainqueur de chaque saison de 69 compétitions, d'après Wikidata (3 730 vainqueurs) : les grands championnats depuis leurs premières saisons (Serie A depuis 1898, Liga depuis 1929, Ligue 1 depuis 1932, Bundesliga depuis 1963, Eredivisie depuis 1888, Primeira Liga depuis 1934) et la Ligue des champions depuis 1955. Les saisons dont Wikidata ne renseigne pas le vainqueur sont absentes (par exemple la Ligue 1 2024/25). Le site affiche le vainqueur de la saison et les clubs les plus titrés sur la page de chaque compétition, et les titres d'un club sur sa page.
- **Effectifs depuis Wikipedia en néerlandais** : 11 effectifs d'Eredivisie lus de plus (273 → 284 sur 469 club-saisons), y compris depuis les tableaux « Naam | Duels » ; les titres sont devinés même quand Wikidata relie une autre page.
- **Mouvements en cours de saison** : pour 2 368 lignes d'effectif de plus, le club quitté et le club rejoint en cours de saison sont marqués (`left_mid` / `arrived_mid`), déduits de l'ordre chronologique de la carrière du joueur.
- **Site** : les effectifs reconstitués (déduits des carrières, non lus sur une page) portent un avis sur la page du club.
- 85 099 joueurs, 327 375 lignes d'effectif et 479 110 lignes de carrière au total.

## Data 1.14.2 — 2026-11-14
- **Effectifs de l'Eredivisie depuis Wikipedia en néerlandais** (`<club> in het seizoen YYYY/YY`) : 32 effectifs lus de plus (241 → 273 sur 469 club-saisons), l'équipe première seulement (les tableaux des partants, des arrivants, des jeunes et de l'équipe réserve sont écartés).
- **Effectifs partiels d'après les carrières** étendus à la Primeira Liga, à la Liga et à la Ligue 1 (+3, +1, +5 club-saisons). La Primeira Liga n'a presque aucune page « saison du club » en portugais (2 sur 292 manquantes).
- La base compte maintenant 84 899 joueurs, 326 795 lignes d'effectif et 478 872 lignes de carrière.

## Data 1.14.1 — 2026-11-14
- **Statistiques de carrière pour 26 835 joueurs** (736 de plus) et 911 338 lignes de club : les tableaux coupés par une balise de référence mal formée (`<ref name="14/15"/>`), les pages qui écrivent les colonnes dans un autre ordre que leur en-tête (Sergei Ignashevich) et celles qui titrent la section « Statistics » ou « Club statistics » sont maintenant lues.
- **Correction** : drapeaux. L'ex-Yougoslavie écrite « YUG 1992-2003 » et la RDA écrite « RDA » ne retombent plus sur un code sans drapeau ; les drapeaux de l'Union soviétique, de la RDA, de la Corse, de la Bretagne, des Antilles néerlandaises et de Guam sont ajoutés au site.

## Data 1.14.0 — 2026-11-14
- **Coupe UEFA de 2000/01 à 2008/09 et Ligue Europa 2009/10** (nouvelle option `uefa --cup UC`) : les 32 clubs des seizièmes de finale jusqu'en 2002/03 et 2003/04, la phase de groupes à 40 clubs dès 2004/05, puis les 48 clubs de la Ligue Europa 2009/10 (328 participations en Coupe UEFA, 48 en Ligue Europa).
- **Deuxièmes divisions de 2000/01 à 2009/10** pour l'Angleterre, la France, l'Allemagne, l'Espagne et l'Italie : 915 club-saisons sur 1 055 avec un effectif.
- **Effectifs partiels construits d'après les carrières des joueurs** (`reconstruct --from-careers`) : pour 969 club-saisons sans page Wikipedia (Liga, Ligue 1, Süper Lig, Eredivisie, Primeira Liga, championnat belge, deuxièmes divisions, clubs de coupes continentales), les joueurs dont le tableau de statistiques ou l'infobox les place dans le club cette saison (10 joueurs au moins). 18 061 lignes, toutes marquées `inferred` ; la club-saison garde son trou documenté.
- **Statistiques de carrière pour 26 099 joueurs** ; la base compte maintenant 84 679 joueurs et 326 072 lignes d'effectif.
- **Correction** : la D2 anglaise de 2000 à 2003 (alors « Football League First Division »), la « Division 2 » française avant 2002 et la taille de la Serie B (20, 24, puis 22 clubs) sont maintenant reconnues.

## Data 1.13.0 — 2026-11-14
- **Ligue des champions de l'UEFA de 2000/01 à 2009/10** : participants de la phase de groupes (320 participations, 299 avec un effectif) et effectifs des clubs de tous les pays, avec les autres saisons de première division des clubs déjà vus (`complete-clubs`). Les championnats du Portugal, des Pays-Bas, de la Belgique et de la Turquie sont lus jusqu'à 2000/01 (Turquie 2000/01 : pas de page sur Wikipedia).
- **Effectifs des clubs des coupes continentales** (nouvelle option `continental --squads`) : Copa Libertadores 263 participations sur 544 avec un effectif, Ligue des champions CAF 103 sur 226, Ligue des champions AFC 339 sur 552 (2010 → 2026). Un club sans page de saison reste vide et est listé comme trou.
- **Statistiques de carrière pour 23 923 joueurs** (au lieu de 4 134) : tous les joueurs qui ont une page Wikipedia anglaise ont été lus (42 740 pages), 797 717 lignes de club et 45 534 lignes de sélection.
- **Correction** : drapeaux. 38 377 lignes d'effectif écrites en néerlandais (« Vlag van Nederland »), codes à deux lettres (« AR »), adjectifs (« German », « Swiss »), noms turcs et néerlandais, et anciens pays (Serbie-et-Monténégro, RF Yougoslavie, Tchécoslovaquie) n'avaient pas de drapeau ; il n'en reste que 67 lignes sur 259 346 (valeurs qui ne sont pas des pays). Le site ne rattache plus « Germany » à l'ancien code `dd`, et Trinité-et-Tobago, Saint-Kitts-et-Nevis, Antigua-et-Barbuda, Sainte-Lucie, la Catalogne, le Pays basque et la Galice ont leur drapeau.
- **Correction** : une page Wikipedia sans aucune révision (titre mal formé) n'arrête plus tout un lot.
- **Site** : les photos de joueur en pied sont calées sur le haut pour garder le visage ; la page Joueurs a une recherche par nom, des boutons de poste avec compteurs, des filtres amovibles et des colonnes triables ; le panneau des statistiques de carrière s'ouvre déplié et sa vue des sélections est refaite ; icône d'écran d'accueil pour les téléphones.

## Data 1.12.0 — 2026-11-13
- **Statistiques de carrière** (nouvelles tables `stat_club`, `stat_national`, `stat_source`) : matchs et buts par club, saison et compétition (championnat, coupe nationale, coupe de la Ligue, continental, autres), puis par sélection et année, lus dans la section « Career statistics » de la page Wikipedia anglaise de 4 695 joueurs de clubs de France, d'Angleterre, d'Italie, d'Espagne, des Pays-Bas, du Portugal et d'Allemagne une saison de Ligue des champions depuis 2010 (4 134 ont un tableau club, 161 480 lignes). Valeurs telles que publiées, non vérifiées. Nouveau bloc « Statistiques de carrière » sur la fiche joueur : par saison, par club, par compétition, sélection.
- **Fiche joueur** : les totaux de carrière utilisent ce tableau (toutes compétitions) quand il existe, au lieu de l'infobox (championnat seulement).

## Data 1.11.0 — 2026-11-13
- **Saisons 2000/01 à 2009/10 pour les cinq grands championnats** (Premier League, Liga, Serie A, Bundesliga, Ligue 1) : 10 saisons de plus, 932 club-saisons, 789 effectifs lus. Sans page « saison du club » sur Wikipedia, l'effectif reste vide et est listé comme tel (surtout Liga et Ligue 1 avant 2005).
- **Effectifs reconstitués** (nouvelle commande `reconstruct`) : quand un club-saison n'a pas d'effectif mais que sa page liste les transferts, l'effectif est reconstruit comme celui de la saison précédente, moins les départs, plus les arrivées. Les lignes sont marquées `inferred` (jamais `attested`) et le trou reste documenté. Premier usage : Holstein Kiel et VfL Bochum 2024/25.
- **Correction** : les tableaux d'effectif sans colonne « No. » (Blackburn Rovers 2008/09) sont maintenant lus.

## Data 1.10.1 — 2026-11-13
- **Correction** : les icônes de statut écrites comme des images (`[[File:Injury icon 2.svg|15px]]`) étaient lues comme des joueurs nommés « 15px » ou « 14px » et masquaient le vrai joueur (Maccabi Haifa 2025/26-2026/27, San Lorenzo 2022/23-2024/25, Palmeiras 2014/15-2016/17, Santos 2016/17) ; les saisons concernées ont été relues.
- **Correction** : un nom de famille écrit comme lien avec texte affiché est présenté avec le titre complet de la page (« Lloris » → « Hugo Lloris ») ; prénoms et surnoms restent tels qu'écrits.
- **Correction** : « Abou Kanté » (Stade Lavallois 2026/27) est relié à sa page « Aboubakary Kanté ».

## Data 1.10.0 — 2026-11-13
- **Nouvelles compétitions** : Copa Libertadores, Ligue des champions de la CAF et Ligue des champions de l'AFC, participants de la phase de groupes ou de ligue de 2010 à 2026 (liste seulement ; [guide](continental-cups.md)).
- **Correction** : les championnats à poules étaient sous-comptés (Chine 2020 et 2021, Tunisie 2012, 2016 et 2021, Égypte 2012 et 2013) : les tableaux de poules sont maintenant fusionnés.

## Data 1.9.0 — 2026-11-13
- **Vingt pays en « liste seulement »** : Mexique, Japon, Australie, Chine, Corée du Sud, Colombie, Équateur, Chili, Égypte, Pérou, Maroc, Afrique du Sud, Qatar, Émirats arabes unis, Paraguay, Uruguay, Bolivie, Algérie, Vietnam, Tunisie. Championnat de première division et clubs de chaque saison depuis 2010, sans effectifs pour le moment. Pour la saison en cours sans page de saison, la page générique du championnat est lue.

## Data 1.8.0 — 2026-11-13
- **Ligue Conférence de l'UEFA** : participants et effectifs de 2021/22 à 2026/27, avec les championnats nationaux de ses clubs. Environ la moitié des clubs de petits pays n'ont pas de page « saison du club » et restent « Sans effectif ».

## Data 1.7.0 — 2026-11-13
- **Nouveaux championnats** : Brésil (Série A) et Argentine (Primera División) de 2010 à 2026, effectifs lus en anglais, portugais et espagnol (couverture partielle : beaucoup de clubs n'ont pas de page « saison du club »).
- Départs d'été retirés des effectifs ; profils de joueurs (lieu de naissance, taille, photo).

## Data 1.6.1 — 2026-11-13
- **Corrections d'effectifs** : un joueur parti d'un club dans la fenêtre d'été (avant le 2 septembre) et présent dans un autre club la même saison n'est plus listé dans l'ancien club (Lewandowski et Ferran Torres au Barça 2026/27 ; 1 003 lignes sur 17 saisons).

## Data 1.6.0 — 2026-11-13
- **Profils des joueurs** : lieu de naissance, taille, nom complet, décès et photo d'infobox (nouvelle table `player_profile`).

## Data 1.5.1 — 2026-11-13
- Retrait du logo erroné d'Athletic Newham (Wikipedia y affichait celui de l'Atlético de Madrid).

## Data 1.5.0 — 2026-11-13
- **Nouveau** : Ligue Europa, deuxièmes divisions (ENG/ESP/FRA/DEU/ITA), MLS et Saudi Pro League, tous les clubs des championnats nationaux vus en coupe d'Europe, clubs de carrière ajoutés.
- Corrections d'effectifs (Roster, saison en cours, doublons Jr/Junior).

## Data 1.4.0 — 2026-11-12
- `home.json` (accueil instantané), logos de championnats dans la table des compétitions, statuts de prêt seulement pour les vrais prêts (un retour de prêt n'est plus un prêt), cohérence des prêts entre clubs.

## Data 1.3.0 — 2026-11-12
- Même contenu que la 1.2.0 ; la table `club` est ordonnée avec les clubs à effectifs d'abord, en petits groupes de lignes : le site lit environ 170 Ko au lieu de 3,2 Mo au démarrage.

## Data 1.2.0 — 2026-11-12
- Effectifs = union de toutes les langues du pays ; prêts recoupés entre clubs (un prêté n'est pas listé par le prêteur) ; un joueur absent d'une page d'effectif n'est jamais ajouté ; identification Wikidata des joueurs sans lien ; mouvements datés publiés dans `squad_movement`. Dictionnaire de données `SCHEMA.md` dans l'archive.

## Data 1.1.0 — 2026-11-12
- Effectifs = union de toutes les langues du pays (source principale d'abord), avec provenance (`squad_source`, `squad.listed_in`).
- Joueurs fusionnés par erreur corrigés (paramètre `dab=` de `sortname`), ex. Schalke 04 2026/27 / Diogo Leite.
- Prêtés hors de l'effectif d'origine.
- Sélections et buts internationaux ; logos de clubs (17 000+) ; noms anglais pour les stades, championnats et villes en alphabet non latin ; référentiel de pays avec noms es/it/de (drapeaux).
- `SCHEMA.md` : dictionnaire de données des fichiers Parquet.

## Data 1.0.0 — 2026-11-12
- **Première publication** : 5 championnats (Premier League, La Liga, Serie A, Bundesliga, Ligue 1), saisons 2010/11 à 2026/27 (en cours), issues de Wikipedia et Wikidata uniquement. Fichiers Parquet + `manifest.json` ; le site est déployé à partir de cette release.

## Site et outils

### 2026-11-18
- **Reconstructions complètes** : une base reconstruite depuis une release perdait le détail des mouvements (`squad_movement` : 62 319 lignes), les joueurs prêtés ailleurs (24 238), les libellés Wikidata des villes, stades et championnats (9 022), les alias et le journal des corrections. Le script hebdomadaire reconstruit depuis la release à chaque passage : les colonnes `stint_date` / `stint_window` / `stint_other_club` des effectifs étaient donc vides dans les dernières releases et les clubs perdaient leur ville, leur stade et leur championnat. L'export écrit maintenant ces tables (clé `work` du manifeste, clés naturelles, non lues par le site) et `restore-db` les relit ; `recover-work` les reprend d'une ancienne base de travail.
- **Joueurs sans fiche** : la preuve de carrière qui rattache un joueur sans lien au joueur identifié de même nom compare maintenant les identifiants Wikidata des clubs (« AS Nancy » = « AS Nancy Lorraine » = « Nancy ») et ignore les points des sigles (« A.S. Roma ») : 361 joueurs rattachés à leur fiche (dont Ilyes Housni). Les pages françaises rendues en HTML collaient une clé de tri cachée aux noms (« Akpa, ClémentClément Akpa ») : corrigé dans le lecteur et dans les noms existants.
- **Deux dépôts** : ce dépôt contient désormais le pipeline, les tests et les releases de données ; le site reste dans [OpenFootballBase](https://github.com/florentfougeres/OpenFootballBase). Publier une release lance le déploiement du site (`notify-site.yml`, secret `SITE_DEPLOY_TOKEN`). La release Data 1.21.0 a été republiée ici à l'identique ; les précédentes restent dans le dépôt du site. Plan : [migration-two-repos.md](https://github.com/florentfougeres/OpenFootballBase/blob/main/docs/fr/migration-two-repos.md).
- **Page Compétitions** : une vue Clubs (par confédération, puis une rubrique « Monde » pour les coupes intercontinentales, qui ne sont plus mélangées à l'UEFA) et une vue Équipes nationales (phases finales, qualifications, amicaux), avec des icônes et les logos Wikipedia des compétitions ; celles que seule la source de matchs connaît sont dans leur continent.
- **Onglet Résultats** sur chaque page de compétition : classement calculé avec la forme, matchs par journée avec les buteurs ; onglet Palmarès aligné sur le palmarès des clubs. Script hebdomadaire : `matches` (résultats, puis complément de la saison en cours depuis Wikipedia) et `enrich --what leaguelogos` à sa suite.

### 2026-11-16
- **Audit de cohérence** (`audit`) : contrôle toute la base avant chaque publication, lancé par le script hebdomadaire (un problème bloquant l'arrête). Statistiques : les nombres de buts impossibles (plus de 3 par match et au moins 10, fautes de frappe de Wikipedia comme « 11 matchs, 100 buts ») sont désormais laissés vides au lieu d'être affichés ; les tableaux dont la cellule de saison porte un `!colspan` parasite ne décalent plus les colonnes.
- **Mise à jour hebdomadaire** (`scripts/weekly_refresh.sh`, [weekly-refresh.md](weekly-refresh.md)) : script pour un cron sur serveur qui relit les joueurs encore en activité (infobox de carrière et tableaux de statistiques), exporte et publie une release. Nouvelle option `stats --active`.

### 2026-11-13
- **Sécurité et vitesse** : politique de sécurité de contenu (CSP) ; le moteur DuckDB est vérifié par une empreinte SHA-384 et son extension Parquet est hébergée avec le site (voir [security.md](security.md), [website.md](https://github.com/florentfougeres/OpenFootballBase/blob/main/docs/fr/website.md)) ; `restore-db` vérifie le SHA-256 de chaque fichier ; le déploiement télécharge la release qui l'a déclenché ; actions GitHub figées par SHA ; Dependabot, analyse de secrets et protection au push activés.
- **Releases renommées** `Data X.Y.Z` avec le tag `data-X.Y.Z` (elles s'appelaient `data-v1` … `data-v13`, avec des noms comme « Data v1.10.0 (date) »).
- **Dictionnaire de données bilingue** (`SCHEMA.md` en anglais, `SCHEMA.fr.md` en français) et documentation bilingue sous `docs/fr/` et `docs/en/` ; README bilingue.
- **Page Compétitions** : grille uniforme groupée par confédération ; les coupes continentales apparaissent dans leur confédération.
- **Site** : section Joueurs (filtres, téléchargement CSV), tableau de bord des tendances d'un championnat, frise de carrière, mouvements d'un club d'une saison à l'autre, page club + effectif unifiée, couverture en grille de chaleur.
- **Outils** : `openfootball restore-db`, `openfootball continental`, mode `--fresh` et `tools/refresh.sh --fresh` pour le mercato.

### 2026-11-12
- Site refait en Svelte 5 + Vite + Tailwind 4 (style d'application sombre), navigation générique par pays, accueil rapide, bandeau bêta.
- Transferts en cours de saison et cohérence des prêts (D13), identification Wikidata des joueurs sans lien, licence MIT.
- Belgique, Portugal, Pays-Bas et Turquie (analyseurs nl et tr sur le HTML rendu) ; effectif de la saison en cours depuis la page du club ; participants de la Ligue des champions (D14).
- Projet renommé OpenFootballBase ; premier déploiement sur GitHub Pages.

### 2026-11-11
- Projet démarré de zéro (voir [spec.md](spec.md), §2) : pipeline, périmètres déclaratifs, saisons figées, identité par QID Wikidata, carrières depuis les infoboxes, clubs du monde, logos.
