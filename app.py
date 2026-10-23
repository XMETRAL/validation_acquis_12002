"""Application Validation d'acquis - fabrique Flask.

Lancement en développement :   python app.py
Lancement en production :       python server.py   (Waitress + HTTPS)
"""
import os

from flask import Flask, redirect, url_for
from flask_login import LoginManager, current_user

from config import Config
from models import User, db

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Merci de vous connecter pour accéder à cette page."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_class)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(os.path.join(app.root_path, "instance"), exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from blueprints.auth import auth_bp
    from blueprints.admin import admin_bp
    from blueprints.stats import stats_bp
    from blueprints.public import public_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(public_bp)

    # --- Filtre d'accès par IP publique sur la partie administration -------
    import parametres as _param
    from flask import render_template, request

    @app.before_request
    def _filtre_ip_admin():
        # Protège toute la partie administration, y compris la page de
        # connexion : une IP non autorisée ne voit jamais le formulaire login.
        # Restent ouverts : le questionnaire stagiaire (blueprint « public »)
        # et les fichiers statiques (CSS, logo, images des questions).
        if request.endpoint == "static" or request.blueprint == "public":
            return
        try:
            actif = _param.get_param("ip_filtre_actif", "0") == "1"
        except Exception:
            return  # jamais bloquer l'app sur une erreur de lecture
        if not actif:
            return
        ip = _param.ip_client()
        if _param.est_loopback(ip):
            return  # accès local toujours permis (anti-verrouillage)
        liste = _param.parse_liste_ips(_param.get_param("ip_autorisees", "") or "")
        if not liste:
            return  # liste vide = pas de blocage (anti-verrouillage)
        if not _param.ip_autorisee(ip, liste):
            return render_template("acces_refuse.html", ip=ip), 403

    # --- Protection CSRF des formulaires (hors questionnaire stagiaire) ---
    import hmac
    import secrets
    from flask import flash, session

    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(32)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def _verif_csrf():
        if request.method != "POST" or request.blueprint == "public":
            return
        attendu = session.get("_csrf", "")
        recu = request.form.get("csrf_token", "")
        if not attendu or not hmac.compare_digest(attendu, recu):
            app.logger.warning("Requête refusée (jeton CSRF invalide) : %s", request.path)
            flash("Formulaire expiré ou invalide : rechargez la page et réessayez.", "error")
            retour = request.referrer or ""
            if not retour.startswith(request.host_url):
                retour = url_for("index")  # jamais de renvoi vers un site tiers
            return redirect(retour)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("auth.login"))

    with app.app_context():
        db.create_all()
        seed_super_admin(app)

    return app


def seed_super_admin(app):
    """Crée le super administrateur au premier lancement s'il n'existe pas."""
    if User.query.filter_by(is_super_admin=True).first():
        return
    admin = User(
        email=app.config["DEFAULT_ADMIN_EMAIL"],
        name=app.config["DEFAULT_ADMIN_NAME"],
        is_super_admin=True,
    )
    admin.set_password(app.config["DEFAULT_ADMIN_PASSWORD"])
    db.session.add(admin)
    db.session.commit()
    print("=" * 60)
    print(" Super administrateur créé :")
    print("   Email        :", app.config["DEFAULT_ADMIN_EMAIL"])
    print("   Mot de passe :", app.config["DEFAULT_ADMIN_PASSWORD"])
    print(" (à modifier après la première connexion)")
    print("=" * 60)


app = create_app()


if __name__ == "__main__":
    # Serveur de développement uniquement (HTTP). Pour la prod : python server.py
    # Le cookie de session « secure » n'est pas envoyé en HTTP : on le désactive ici.
    app.config["SESSION_COOKIE_SECURE"] = False
    app.run(host="127.0.0.1", port=5000, debug=True)
