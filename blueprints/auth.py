"""Authentification : connexion sécurisée, déconnexion, réinitialisation du mot de passe."""
import threading
import time
from datetime import datetime, timedelta

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required, login_user, logout_user

from mailer import mail_configured, send_reset_email
from models import User, db
from parametres import ip_client

auth_bp = Blueprint("auth", __name__)


# --------------------------------------------------------------------------- #
# Anti brute-force : échecs de connexion comptés par IP et par email          #
# (en mémoire : remis à zéro au redémarrage du serveur)                        #
# --------------------------------------------------------------------------- #
FENETRE = 15 * 60          # durée d'observation et de blocage (secondes)
MAX_ECHECS_IP = 5          # échecs tolérés par IP dans la fenêtre
MAX_ECHECS_EMAIL = 10      # échecs tolérés par compte, toutes IP confondues

_echecs: dict[str, list[float]] = {}
_verrou = threading.Lock()


def _recents(cle, maintenant):
    """Échecs encore dans la fenêtre pour `cle` (purge les anciens)."""
    liste = [t for t in _echecs.get(cle, []) if maintenant - t < FENETRE]
    if liste:
        _echecs[cle] = liste
    else:
        _echecs.pop(cle, None)
    return liste


def _bloque(ip, email):
    """Secondes d'attente restantes si l'IP ou le compte est bloqué, sinon 0."""
    maintenant = time.monotonic()
    attente = 0
    with _verrou:
        for cle, maxi in ((f"ip:{ip}", MAX_ECHECS_IP), (f"email:{email}", MAX_ECHECS_EMAIL)):
            liste = _recents(cle, maintenant)
            if len(liste) >= maxi:
                attente = max(attente, int(FENETRE - (maintenant - liste[-maxi])) + 1)
    return attente


def _noter_echec(ip, email):
    maintenant = time.monotonic()
    with _verrou:
        for cle in (f"ip:{ip}", f"email:{email}"):
            _echecs.setdefault(cle, []).append(maintenant)


def _effacer_echecs(ip, email):
    with _verrou:
        _echecs.pop(f"ip:{ip}", None)
        _echecs.pop(f"email:{email}", None)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        ip = ip_client()
        attente = _bloque(ip, email)
        if attente:
            current_app.logger.warning("Connexion bloquée (brute-force) : ip=%s email=%s", ip, email)
            flash(f"Trop de tentatives échouées. Réessayez dans {attente // 60 + 1} minute(s).", "error")
            return render_template("auth/login.html"), 429
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            _effacer_echecs(ip, email)
            login_user(user, remember=bool(request.form.get("remember")))
            next_page = request.args.get("next")
            if next_page and next_page.startswith("/"):
                return redirect(next_page)
            return redirect(url_for("admin.dashboard"))
        _noter_echec(ip, email)
        current_app.logger.warning("Échec de connexion : ip=%s email=%s", ip, email)
        flash("Email ou mot de passe incorrect.", "error")
    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Vous êtes déconnecté.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/mot-de-passe-oublie", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = user.new_reset_token()
            db.session.commit()
            link = url_for("auth.reset_password", token=token, _external=True)
            if mail_configured():
                if send_reset_email(user, link):
                    flash("Si un compte existe pour cet email, un lien de "
                          "réinitialisation vient d'être envoyé.", "info")
                else:
                    # Envoi impossible : on journalise le lien pour récupération
                    current_app.logger.error(
                        "Lien de réinitialisation (envoi échoué) pour %s : %s", email, link)
                    flash("L'envoi de l'email a échoué. Réessayez plus tard ou "
                          "contactez l'administrateur.", "error")
                return render_template("auth/forgot_password.html")
            # SMTP non configuré : le lien n'est JAMAIS affiché à l'écran (sinon
            # n'importe qui connaissant un email prendrait le compte) ; il est
            # seulement journalisé côté serveur.
            current_app.logger.warning(
                "Lien de réinitialisation (SMTP non configuré) pour %s : %s", email, link)
        # Message identique que l'email existe ou non (anti-énumération)
        flash("Si un compte existe pour cet email, la demande a été transmise. "
              "Sans email reçu, contactez l'administrateur.", "info")
    return render_template("auth/forgot_password.html")


@auth_bp.route("/reinitialiser/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    max_age = current_app.config["RESET_TOKEN_MAX_AGE"]
    valid = (
        user is not None
        and user.reset_token_at is not None
        and datetime.utcnow() - user.reset_token_at < timedelta(seconds=max_age)
    )
    if not valid:
        flash("Ce lien de réinitialisation est invalide ou expiré.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        pw1 = request.form.get("password", "")
        pw2 = request.form.get("password2", "")
        if len(pw1) < 8:
            flash("Le mot de passe doit contenir au moins 8 caractères.", "error")
        elif pw1 != pw2:
            flash("Les deux mots de passe ne correspondent pas.", "error")
        else:
            user.set_password(pw1)
            user.clear_reset_token()
            db.session.commit()
            flash("Mot de passe mis à jour. Vous pouvez vous connecter.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", token=token)


@auth_bp.route("/mon-compte", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            current_user.name = name
        pw1 = request.form.get("password", "")
        if pw1:
            pw2 = request.form.get("password2", "")
            if len(pw1) < 8:
                flash("Le mot de passe doit contenir au moins 8 caractères.", "error")
                return render_template("auth/account.html")
            if pw1 != pw2:
                flash("Les deux mots de passe ne correspondent pas.", "error")
                return render_template("auth/account.html")
            current_user.set_password(pw1)
        db.session.commit()
        flash("Vos informations ont été mises à jour.", "success")
        return redirect(url_for("auth.account"))
    return render_template("auth/account.html")
