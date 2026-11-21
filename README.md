# bw-dedupe

Fusionne les logins Bitwarden en double : même domaine, même identifiant et même mot de passe, mais un sous-domaine ou une URL différente.

Le script passe par la CLI officielle `bw` et modifie le coffre sur place. Les IDs, pièces jointes, passkeys et l'historique restent intacts.

## Confidentialité

- Mots de passe, clés TOTP, valeurs des champs perso et contenu des notes sont seulement comparés en mémoire. Ils ne sont jamais affichés, journalisés ni écrits dans le rapport.
- Les éléments modifiés sont transmis à `bw` par l'entrée standard, jamais en argument de ligne de commande.
- Le script n'accède pas au réseau, à part via `bw`. La Public Suffix List utilisée est celle embarquée dans `tldextract`.
- Les rapports HTML contiennent les noms, identifiants, URIs et IDs des éléments. Garde-les en local. `--mask-usernames` masque les identifiants.

## Prérequis

- [Bitwarden CLI](https://bitwarden.com/help/cli/) (`bw`) dans le PATH, ou son chemin passé avec `--bw`.
- [uv](https://docs.astral.sh/uv/) : il installe `tldextract` tout seul au premier lancement.
  Sans uv : Python 3.10+ et `pip install tldextract`, puis `python bw_dedupe.py` à la place de `uv run bw_dedupe.py`.

## Utilisation

1. Se connecter et déverrouiller le coffre.

   PowerShell :
   ```powershell
   bw login
   $env:BW_SESSION = bw unlock --raw
   ```
   Bash :
   ```bash
   bw login
   export BW_SESSION="$(bw unlock --raw)"
   ```

2. Simulation : génère un rapport, sans rien modifier.
   ```bash
   uv run bw_dedupe.py
   ```

3. Application :
   ```bash
   uv run bw_dedupe.py --apply
   ```
   Le script :
   1. écrit l'aperçu `bw-dedupe-report-<date>-apercu.html` ;
   2. attend que tu tapes `oui` (toute autre réponse annule sans rien toucher) ;
   3. fait une sauvegarde chiffrée `bw-backup-<date>.json` ;
   4. applique exactement le plan de l'aperçu ;
   5. écrit `bw-dedupe-report-<date>.html` avec le statut de chaque changement.

4. Verrouiller le coffre une fois terminé :
   ```bash
   bw lock
   ```

### Options

| Option | Effet |
|---|---|
| `--apply` | Applique les changements après aperçu et confirmation. Sans elle, le script fait une simulation. |
| `--yes` | Saute la confirmation. À éviter au premier passage. |
| `--no-backup` | Ne fait pas la sauvegarde chiffrée avant d'appliquer. |
| `--rename-all` | Renomme aussi les logins sans doublon d'après leur domaine. |
| `--mask-usernames` | Masque les identifiants dans le rapport (`m***@gmail.com`). |
| `--report <chemin>` | Chemin du rapport HTML. |
| `--bw <chemin>` | Chemin de l'exécutable `bw`. |

## Règles

### Doublons

Deux logins sont des doublons quand ils ont :
- le même domaine enregistrable : `login.amazon.fr` et `www.amazon.fr/ap/signin` donnent tous les deux `amazon.fr`. Les suffixes privés sont respectés : `alice.github.io` et `bob.github.io` restent distincts ;
- le même identifiant, sans tenir compte des espaces autour ni de la casse ;
- le même mot de passe.

### Fusion

- **Élément conservé** : celui qui porte des pièces jointes s'il y en a un, sinon le plus récemment modifié.
- **Nom** : le domaine, par exemple `amazon.fr`.
- **URIs** : une seule URI `https://<domaine>` en détection « domaine de base », plus les URIs d'application (`androidapp://`, etc.). `http` est gardé seulement si toutes les URIs d'origine étaient en `http`.
- **Repris des doublons** : notes distinctes (séparées par `----`), champs perso absents, clé TOTP si l'élément conservé n'en a pas, favori, dossier, re-demande du mot de passe maître.
- **Doublons** : envoyés dans la corbeille Bitwarden, récupérables 30 jours.

### Éléments jamais modifiés

Ils sont tous listés dans le rapport :

| Cas | Raison |
|---|---|
| Même domaine et identifiant, mots de passe différents | Conflit : l'un est peut-être périmé, à vérifier à la main. Les lettres `mdp A` / `mdp B` indiquent quels éléments partagent le même mot de passe, sans le révéler. |
| Même domaine, identifiant et mot de passe, clés TOTP différentes | Conflit. |
| Groupe contenant une passkey | Copie des passkeys par la CLI jugée risquée. |
| Pièces jointes sur plusieurs éléments du groupe | La CLI ne peut pas déplacer une pièce jointe. |
| Élément pointant vers plusieurs domaines | Domaine ambigu. |
| Élément d'organisation | Seul le coffre personnel est traité. |
| Aucune URI web exploitable (app seule, IP, `localhost`) | Pas de domaine. |

## Annuler

- **Restaurer les doublons supprimés** : le rapport final liste les commandes `bw restore item <id>`.
- **Retour complet**, y compris sur les éléments conservés : réimporter `bw-backup-<date>.json`. Cet export est chiffré avec la clé du compte et ne s'importe que sur ce même compte. Supprime-le une fois le résultat validé.

## En cas d'erreur

La console n'affiche que l'ID de l'élément concerné et le message de `bw`. Un échec d'édition n'entraîne aucune suppression dans le groupe concerné. Un `Ctrl+C` en cours d'application écrit quand même le rapport avec ce qui a été fait.
