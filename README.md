# P5R FR Audio Lab

Outil pour doubler en français les répliques de combat de **Persona 5 Royal (PC)**, pour le mod **PERSONA 5 ROYAL MOD VF**.

Il fait écouter les voix d'origine, garde les transcriptions, convertit les enregistrements français au format du jeu et les range directement dans un mod Reloaded-II prêt à tester.

## Installation

1. Télécharge la dernière version : bouton **Code → Download ZIP**, ou onglet **Releases**.
2. Dézippe le dossier où tu veux.
3. Double-clic sur **`start.bat`**.

Au premier lancement, tout se fait tout seul :
- Python est installé s'il manque (via winget), puis les dépendances (dont ffmpeg) ;
- les outils audio (vgmstream, VGAudio) sont téléchargés dans `tools/` ;
- Persona 5 Royal est trouvé via Steam, et ses voix de combat sont extraites (le jeu n'est pas modifié) ;
- le mod est créé dans le dossier `mod/` de l'outil et relié à Reloaded-II.

L'outil s'ouvre dans le navigateur (http://127.0.0.1:8005). Garde la fenêtre noire ouverte tant que tu l'utilises.

## Mises à jour

Quand une nouvelle version est publiée dans les **Releases** du dépôt, un bouton **« Nouvelle version »** apparaît en haut de l'outil. On peut aussi vérifier à la main dans **Réglages → Mises à jour**. Un clic l'installe et redémarre l'outil. Les réglages, les voix extraites et le mod sont gardés.

## Poser une VF

- **Une par une :** glisser un fichier audio (WAV, MP3, FLAC, OGG) sur une ligne, ou cliquer « Déposer un fichier ».
- **Export groupé :** toutes les VO d'un perso dans un zip (`BP01_3_Cue3001.wav`…) avec une liste CSV. Si les comédiens gardent ces noms pour leurs enregistrements, l'import se fait en un clic.
- **Import groupé :** dans Réglages, choisir le dossier des enregistrements VF. Les fichiers doivent commencer par `BP01_118` (perso puis numéro du clip), ou être rangés comme `BP01/118.wav`.
- **Plusieurs fichiers d'un coup :** glisser plusieurs fichiers sur la liste. Chacun est rangé d'après son nom (`BP01_118.wav`, `bp01-118.wav`…), même pour d'autres persos.
- **Télécharger une réplique :** l'icône tout à droite de la ligne.

À chaque fichier, l'outil coupe les silences au début et à la fin, cale le volume sur la VO, convertit au format de l'original et l'encode en ADX chiffré pour P5R. La durée de la VF s'affiche, en orange si elle est nettement plus longue que la VO.

Raccourcis : ↑ ↓ pour changer de ligne, Espace pour la VO, Maj + Espace pour la VF, **C** pour comparer VO puis VF, Entrée pour écrire la transcription.

## Reloaded-II

Le mod est un seul dossier, rangé dans l'outil (`mod/p5rpc.vf.combat`). Reloaded-II y accède par un raccourci (une jonction Windows) placé dans son dossier `Mods` : tout ce qui est posé dans l'outil est vu tout de suite par Reloaded-II, sans copie.

Dans **Réglages**, une liste vérifie que tout est branché :
1. Reloaded-II trouvé (automatiquement, ou dossier choisi à la main) ;
2. Persona Essentials installé ;
3. P5R ajouté dans Reloaded-II ;
4. mod relié ;
5. mod activé pour P5R.

Pour tester en jeu : voix du jeu **en anglais**, lancer P5R depuis Reloaded-II, faire un combat.

Si Reloaded-II affiche « IP relative memory operand is too far away » au lancement du jeu, c'est un bug connu de Reloaded-II : relancer (ou redémarrer le PC) suffit.

## Développement

- `server/` : serveur Python (FastAPI) : lecture des CPK/AWB, détection du jeu et de Reloaded-II, conversion, mises à jour.
- `web/` : interface (React + Vite). `web/dist` est la version compilée, utilisée telle quelle. Pour la modifier : `cd web && npm install && npm run build`.
- `tests/` : tests de bout en bout sur les vraies voix (`py -3 -m pip install pytest httpx` puis `py -3 -m pytest tests -q`). Ils utilisent un dossier temporaire et ne touchent ni au mod ni à Reloaded-II.

Pour publier une version : changer le numéro dans `VERSION`, puis créer une Release GitHub avec le tag correspondant (par exemple `v1.1.0`).

À partir de la 1.1.0, l'outil redémarre après une mise à jour dans une nouvelle fenêtre : `start.bat` peut donc être modifié sans risque. Une copie en 1.0.0 relance au contraire le `start.bat` en cours : pour qu'elle se mette à jour proprement, la version suivante doit garder un `start.bat` identique (c'est le cas de la 1.1.0).

Dans `SOUND/BATTLE` : `BP01` à `BP10` (pas de `BP08`) sont les persos jouables, `BP09_01` une deuxième série pour Crow, `SPT01`/`SPT02`/`SPT04` les navigatrices.
