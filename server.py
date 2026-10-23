"""Serveur de production : Waitress (WSGI).

Ce script utilise spécifiquement le fichier '.env2' pour sa configuration réseau.
"""
import os
import sys

# --------------------------------------------------------------------------- #
# Chargement forcé du fichier .env2 spécifique                                #
# --------------------------------------------------------------------------- #
try:
    from dotenv import load_dotenv
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    ENV2_PATH = os.path.join(BASE_DIR, ".env2")
    
    if os.path.exists(ENV2_PATH):
        load_dotenv(dotenv_path=ENV2_PATH, override=True)
        print(f"Configuration chargée avec succès depuis : .env2")
except ImportError:
    pass

from waitress import serve
from app import app

# HTTPS_PORT et le proxy TCP local sont ignorés pour respecter le port unique
BACKEND_HOST = os.environ.get("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "12001"))
THREADS = int(os.environ.get("THREADS", "16"))

def main():
    app.config["SESSION_COOKIE_SECURE"] = True

    print(f"Waitress actif sur http://{BACKEND_HOST}:{BACKEND_PORT} — {THREADS} threads")
    
    try:
        # Lancement direct au premier plan : un seul port ouvert, pas de proxy interne
        serve(
            app,
            host=BACKEND_HOST,
            port=BACKEND_PORT,
            threads=THREADS,
            url_scheme="https",
            ident="Axe Informatique",
            # L'aiguilleur (127.0.0.1) transmet l'IP réelle du visiteur dans
            # X-Forwarded-For : sans ces options Waitress efface l'en-tête et
            # le filtre IP voit tout le monde en 127.0.0.1 (toujours autorisé).
            trusted_proxy="127.0.0.1",
            trusted_proxy_count=1,
            trusted_proxy_headers={"x-forwarded-for"},
            clear_untrusted_proxy_headers=True,
        )
    except KeyboardInterrupt:
        print("\nArrêt du serveur.")

if __name__ == "__main__":
    main()
