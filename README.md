# Validation d'acquis — Axe Informatique

Application web de validation des acquis par questionnaires à choix multiples.
Un stagiaire répond à un formulaire depuis une URL publique ; les administrateurs
gèrent les questionnaires et consultent les statistiques.

Stack : Python / Flask, SQLite, Flask-Login, Waitress (production), thème clair/sombre.

## Hiérarchie

    Thème (famille)  →  Formulaire  →  Question  →  Propositions (réponses)

## Installation

Python 3.10+ recommandé.

    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # Linux / macOS
    source .venv/bin/activate

    pip install -r requirements.txt

## Lancement

**Développement** (HTTP, rechargement auto, sur http://127.0.0.1:5000) :

    python app.py

**Production** (HTTPS + Waitress, ~15 connexions simultanées) :

    python server.py

Au premier lancement de `server.py`, un certificat auto-signé est créé dans
`certs/`. L'application est alors accessible sur `https://<adresse-du-serveur>:8443`.
Le navigateur affichera un avertissement de sécurité (certificat auto-signé) :
c'est normal, on peut accepter l'exception. Pour supprimer l'avertissement,
remplacer `certs/cert.pem` et `certs/key.pem` par un certificat signé par une
autorité reconnue (ou interne à l'entreprise).

Réglages via variables d'environnement (voir `server.py` et `config.py`) :
`HTTPS_PORT`, `THREADS`, `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`…

## Premier compte

Un super-administrateur est créé automatiquement au premier démarrage et
affiché dans la console :

    Email        : admin@axe-informatique.fr
    Mot de passe : Axe@2025!

**À modifier dès la première connexion** (menu « Mon compte »).

## Configuration de l'email (SMTP)

L'envoi des liens de réinitialisation par email est intégré. Il s'active dès que
`MAIL_SERVER` est renseigné. Le plus simple : copier `.env.example` en `.env` et
compléter les valeurs (le fichier `.env` est chargé automatiquement).

    MAIL_SERVER=smtp.office365.com
    MAIL_PORT=587
    MAIL_USE_TLS=1            # STARTTLS (port 587)
    MAIL_USE_SSL=0            # ou 1 pour SSL direct (port 465)
    MAIL_USERNAME=compte-envoi@axe-informatique.fr
    MAIL_PASSWORD=...
    MAIL_SENDER=Validation d'acquis <no-reply@axe-informatique.fr>

Ces valeurs peuvent aussi être fournies comme variables d'environnement.
Si `MAIL_SERVER` reste vide, l'application se rabat sur l'affichage du lien à
l'écran (pratique en développement). En cas d'échec d'envoi, le lien est
journalisé côté serveur et un message d'erreur est affiché.

## Fonctionnalités

**Administration**
- Connexion sécurisée, mots de passe chiffrés (pbkdf2:sha256).
- Gestion des utilisateurs réservée au super-administrateur ; chaque
  administrateur peut se voir attribuer un ou plusieurs thèmes.
- Réinitialisation de mot de passe par lien à durée limitée (1 h), envoyé par
  email dès qu'un serveur SMTP est configuré (voir ci-dessous).
- Formulaires : plusieurs bonnes réponses par question, explication,
  image optionnelle par glisser-déposer, seuil de réussite, activation/
  désactivation, ordre des questions aléatoire à chaque passage.
- URL publique copiable par formulaire (régénérable).

**Statistiques**
- Vue d'ensemble par thème et formulaire, graphiques (barres / distribution).
- Détail par question (taux de réussite, fréquence de chaque proposition).
- Page « toutes les réponses » regroupées par thème puis formulaire.
- Modification (email, bascule correct/incorrect) et suppression des réponses
  et des tentatives, avec recalcul automatique du score.

**Passage du questionnaire (stagiaire)**
- Saisie de l'email, une question à la fois, validation puis suivante.
- Résultats finaux : score, réussite/échec selon le seuil, détail des
  réponses fausses avec explication, et taux de réussite global par question.

## Structure du projet

    app.py              Fabrique Flask, routes racine, création du super-admin
    server.py           Serveur de production (Waitress + proxy TLS)
    config.py           Configuration
    models.py           Modèles SQLAlchemy
    blueprints/         auth, admin, stats, public, utils
    templates/          Gabarits Jinja2 (auth, admin, stats, public)
    static/             CSS, JS, logo, images téléversées
    instance/           Base SQLite (créée automatiquement)
    certs/              Certificat TLS (créé automatiquement)

## Limites de la v1

- **Réinitialisation de mot de passe** : envoi par email opérationnel via SMTP
  (voir « Configuration de l'email »). Sans SMTP configuré, le lien est affiché
  à l'écran. L'envoi est synchrone (adapté au faible volume attendu).
- **Certificat auto-signé** : suffisant pour un réseau interne ; remplacer par
  un certificat officiel pour une exposition publique.
- **Sessions** : l'état du questionnaire en cours est stocké dans le cookie de
  session. Pour des formulaires très volumineux, prévoir un stockage côté
  serveur.
- **Base SQLite** : adaptée à la charge visée (~15 connexions). Pour une charge
  supérieure, migrer vers PostgreSQL (changer `DATABASE_URL`).
