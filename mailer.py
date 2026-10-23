"""Envoi d'emails via SMTP (bibliothèque standard, aucune dépendance externe).

L'envoi est activé dès que MAIL_SERVER est renseigné dans la configuration
(voir config.py / .env). Sinon, l'application se rabat sur l'affichage du lien
de réinitialisation à l'écran.
"""
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


def mail_configured():
    """Vrai si un serveur SMTP est configuré."""
    return bool(current_app.config.get("MAIL_SERVER"))


def send_email(subject, recipient, body_text, body_html=None):
    """Envoie un email. Renvoie True si l'envoi a réussi, False sinon."""
    cfg = current_app.config
    server = cfg.get("MAIL_SERVER")
    if not server:
        return False

    port = int(cfg.get("MAIL_PORT", 587))
    use_ssl = cfg.get("MAIL_USE_SSL", False)
    use_tls = cfg.get("MAIL_USE_TLS", True)
    username = cfg.get("MAIL_USERNAME") or ""
    password = cfg.get("MAIL_PASSWORD") or ""
    sender = cfg.get("MAIL_SENDER") or username or "no-reply@axe-informatique.fr"
    timeout = int(cfg.get("MAIL_TIMEOUT", 15))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    try:
        if use_ssl:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(server, port, timeout=timeout, context=ctx) as s:
                if username:
                    s.login(username, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(server, port, timeout=timeout) as s:
                s.ehlo()
                if use_tls:
                    s.starttls(context=ssl.create_default_context())
                    s.ehlo()
                if username:
                    s.login(username, password)
                s.send_message(msg)
        return True
    except Exception as exc:  # OSError, SMTPException, ssl.SSLError…
        current_app.logger.error("Échec de l'envoi de l'email à %s : %s", recipient, exc)
        return False


def send_reset_email(user, reset_link):
    """Envoie le lien de réinitialisation de mot de passe à l'utilisateur."""
    subject = "Réinitialisation de votre mot de passe — Validation d'acquis"
    text = (
        f"Bonjour {user.name},\n\n"
        f"Vous avez demandé la réinitialisation de votre mot de passe.\n"
        f"Cliquez sur le lien ci-dessous (valable 1 heure) :\n\n"
        f"{reset_link}\n\n"
        f"Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n\n"
        f"Axe Informatique — Validation d'acquis"
    )
    html = (
        f"<p>Bonjour {user.name},</p>"
        f"<p>Vous avez demandé la réinitialisation de votre mot de passe. "
        f"Ce lien est valable une heure :</p>"
        f'<p><a href="{reset_link}">Réinitialiser mon mot de passe</a></p>'
        f"<p style=\"color:#666;font-size:.9em\">Si vous n'êtes pas à l'origine "
        f"de cette demande, ignorez ce message.</p>"
        f"<p>Axe Informatique — Validation d'acquis</p>"
    )
    return send_email(subject, user.email, text, html)
