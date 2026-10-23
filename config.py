"""Configuration de l'application Validation d'acquis."""
import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Chargement optionnel d'un fichier .env (voir .env.example) pour ne pas avoir
# à définir les variables d'environnement à la main.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    pass


def _secret_key():
    """SECRET_KEY de l'environnement, sinon clé aléatoire générée une fois et
    conservée dans instance/secret_key (stable entre les redémarrages).
    Jamais de valeur par défaut connue : elle permettrait de forger les
    cookies de session et d'entrer sans mot de passe."""
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    path = os.path.join(BASE_DIR, "instance", "secret_key")
    try:
        with open(path, encoding="utf-8") as fh:
            key = fh.read().strip()
        if key:
            return key
    except OSError:
        pass
    import secrets
    key = secrets.token_hex(32)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(key)
    return key


class Config:
    SECRET_KEY = _secret_key()

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "validation.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload des images de question
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 Mo par requête

    # Sécurité des sessions
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Passe à True quand l'app est servie derrière HTTPS (cas par défaut ici)
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") == "1"

    # Super administrateur créé au premier lancement
    DEFAULT_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "XXXXXXXXXXXXXXX")
    DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "XXXXXXXXXXXXXXX")
    DEFAULT_ADMIN_NAME = os.environ.get("ADMIN_NAME", "Super Administrateur")

    # Durée de validité d'un lien de réinitialisation de mot de passe
    RESET_TOKEN_MAX_AGE = 3600  # secondes

    # --- Envoi d'emails (réinitialisation de mot de passe) ---------------
    # Laisser MAIL_SERVER vide désactive l'envoi : le lien est alors affiché
    # à l'écran (utile en développement ou sans serveur SMTP).
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "1") == "1"   # STARTTLS (port 587)
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "0") == "1"   # SSL direct (port 465)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    # Adresse d'expédition ; par défaut, l'identifiant SMTP
    MAIL_SENDER = os.environ.get("MAIL_SENDER", "")
    MAIL_TIMEOUT = int(os.environ.get("MAIL_TIMEOUT", "15"))
