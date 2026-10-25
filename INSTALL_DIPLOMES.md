# Diplômes PDF + nom/prénom + classement — installation

Ajout de 5 fonctionnalités : libellé diplôme par test, saisie nom/prénom du
stagiaire, téléchargement du diplôme PDF (15 modèles), fiche stagiaire +
réédition côté admin, classement des stagiaires avec filtre par thème.

## 1. Dépendance de rendu PDF (une seule fois sur le serveur)

Le diplôme est rendu par Chromium via Playwright.

```
pip install -r requirements.txt
playwright install chromium
```

> `playwright install chromium` télécharge le navigateur (~150 Mo). À relancer
> après chaque mise à jour majeure de Playwright.

## 2. Base de données

Aucune manipulation : au démarrage, l'application ajoute automatiquement les
nouvelles colonnes manquantes (`formulaire.diploma_label`,
`attempt.first_name`, `attempt.last_name`). Les données existantes sont
conservées. Un message `[migration] colonne ajoutée : …` s'affiche au 1er
lancement.

## 3. Ce qui change pour l'utilisateur

- **Admin → formulaire** : nouveau champ « Libellé du diplôme » (2ᵉ ligne du
  diplôme, sous le nom du thème ; repli sur le titre du test si vide).
- **Stagiaire** : la page de départ demande désormais prénom + nom + email ;
  en cas de réussite, un bloc permet de choisir un modèle et de télécharger le
  diplôme en PDF.
- **Admin → Statistiques** : bouton « Classement des stagiaires » (triable,
  filtre par thème) ; chaque stagiaire a une fiche listant ses tentatives et
  ses diplômes ; depuis une tentative réussie, on peut rééditer le diplôme.

## 4. Les 15 modèles

Définis dans `templates/diploma/certificate.html` (compositions isométriques
charte AXE, reprises de la maquette). Pour en ajouter/retirer, éditer ce
template et la liste `MODELS` dans `diplomas.py`.

## Si le PDF ne se génère pas

Message « génération indisponible » → Chromium n'est pas installé :
relancer `playwright install chromium`. Le reste de l'app continue de
fonctionner normalement.
