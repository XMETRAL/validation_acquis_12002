"""Génération des diplômes PDF.

Le diplôme est une page HTML (templates/diploma/certificate.html) au format
paysage 1.9:1, déclinée en 15 modèles isométriques (charte AXE). Le rendu PDF
est confié à Chromium via Playwright : fidélité totale aux maquettes (SVG, flex,
polices Google), au prix d'un navigateur à installer sur le serveur.

Installation sur le serveur (une seule fois) :
    pip install playwright
    playwright install chromium
"""
from __future__ import annotations

import base64
import os
import unicodedata
from datetime import datetime

# Dimensions de la carte (identiques au template CSS .card) -> page PDF (A4 paysage)
_CARD_W = "1000px"
_CARD_H = "707px"

# Modèles de certificat (numéro, libellé affiché dans le sélecteur)
MODELS = [
    (1, "Moderne — cube"),
    (5, "Moderne — navy"),
    (2, "Moderne — centré"),
]
MODEL_NUMBERS = {n for n, _ in MODELS}
DEFAULT_MODEL = 1

_MOIS = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
         "août", "septembre", "octobre", "novembre", "décembre"]

_logo_cache: dict[str, str] = {}


def clean_model(value) -> int:
    """Numéro de modèle valide, sinon le modèle par défaut."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MODEL
    return n if n in MODEL_NUMBERS else DEFAULT_MODEL


def date_fr(dt) -> str:
    """'22 octobre 2026' sans dépendre de la locale système."""
    return f"{dt.day} {_MOIS[dt.month]} {dt.year}"


def logo_data_uri(root_path: str) -> str:
    """Logo AXE (static/img/logo.png) encodé en data URI, mis en cache."""
    if root_path in _logo_cache:
        return _logo_cache[root_path]
    path = os.path.join(root_path, "static", "img", "logo.png")
    try:
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        uri = "data:image/png;base64," + b64
    except OSError:
        uri = ""  # pas de logo : la carte reste valide
    _logo_cache[root_path] = uri
    return uri


# Décalage du compteur : les numéros ne démarrent pas à 1 (laisse penser
# qu'un historique de diplômes existe déjà). Unique et stable malgré tout.
CERT_NUMBER_OFFSET = 3147


def make_certificate_number(attempt) -> str:
    """Numéro de certificat unique et stable : AXE-<année>-<séquence>."""
    year = (attempt.created_at or datetime.utcnow()).year
    return f"AXE-{year}-{CERT_NUMBER_OFFSET + attempt.id:06d}"


def ensure_certificate_number(attempt) -> str | None:
    """Attribue (une seule fois) et persiste le numéro si la tentative est réussie."""
    from models import db
    if attempt.passed and not attempt.certificate_number:
        attempt.certificate_number = make_certificate_number(attempt)
        db.session.commit()
    return attempt.certificate_number


def diplomas_dir(root_path: str) -> str:
    d = os.path.join(root_path, "instance", "diplomes")
    os.makedirs(d, exist_ok=True)
    return d


def record_download(attempt, modele: int, pdf_bytes: bytes, root_path: str):
    """Sauvegarde le PDF sur disque et archive l'émission en base (upsert)."""
    from models import db, Diploma
    num = attempt.certificate_number or f"attempt-{attempt.id}"
    fname = f"{num}_m{modele}.pdf"
    with open(os.path.join(diplomas_dir(root_path), fname), "wb") as fh:
        fh.write(pdf_bytes)
    now = datetime.utcnow()
    row = Diploma.query.filter_by(attempt_id=attempt.id, modele=modele).first()
    if row:
        row.filename = fname
        row.certificate_number = attempt.certificate_number
        row.count = (row.count or 0) + 1
        row.updated_at = now
    else:
        row = Diploma(attempt_id=attempt.id, certificate_number=attempt.certificate_number,
                      modele=modele, filename=fname, count=1, created_at=now, updated_at=now)
        db.session.add(row)
    db.session.commit()
    return row


def certificate_context(attempt, root_path: str) -> dict:
    """Contexte du template à partir d'une tentative réussie.

    - ligne 1 (Logiciel) : Logiciel du test, sinon Logiciel du thème,
                           sinon nom du thème
    - ligne 2 (Formation) : Formation du test, sinon description/nom du test
    """
    form = attempt.formulaire
    theme = form.theme if form else None
    ligne1 = ((form.diploma_line1 if form else "")
              or (theme.diploma_line1 if theme else "")
              or (theme.name if theme else ""))
    ligne2 = ((form.diploma_label if form else "")
              or (form.title if form else ""))
    return {
        "modele": DEFAULT_MODEL,
        "logo_data_uri": logo_data_uri(root_path),
        "nom_complet": attempt.full_name,
        "prenom": attempt.first_name or "",
        "nom": attempt.last_name or "",
        "ligne1": ligne1,
        "ligne2": ligne2,
        "date_txt": date_fr(attempt.created_at),
        "numero": attempt.certificate_number or "—",
    }


def safe_filename(attempt) -> str:
    """Nom de fichier ASCII pour l'en-tête Content-Disposition."""
    base = f"diplome_{attempt.last_name}_{attempt.first_name}".strip("_") or "diplome"
    ascii_base = (unicodedata.normalize("NFKD", base)
                  .encode("ascii", "ignore").decode("ascii"))
    keep = [c if (c.isalnum() or c in "-_") else "_" for c in ascii_base]
    return "".join(keep) + ".pdf"


class DiplomaRenderError(RuntimeError):
    """Rendu PDF indisponible (Playwright/Chromium non installé)."""


def render_pdf(html: str) -> bytes:
    """Convertit le HTML du diplôme en PDF paysage via Chromium (Playwright)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # paquet non installé
        raise DiplomaRenderError(
            "Playwright n'est pas installé : exécuter `pip install playwright` "
            "puis `playwright install chromium`."
        ) from exc

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            try:
                page = browser.new_page()
                # On attend le chargement des polices Google avant la capture.
                page.set_content(html, wait_until="networkidle")
                try:
                    page.evaluate("() => document.fonts.ready.then(() => true)")
                except Exception:
                    pass
                pdf = page.pdf(
                    width=_CARD_W, height=_CARD_H, print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
            finally:
                browser.close()
        return pdf
    except DiplomaRenderError:
        raise
    except Exception as exc:  # navigateur absent ou erreur de rendu
        raise DiplomaRenderError(
            "Impossible de générer le PDF : vérifier que Chromium est installé "
            "(`playwright install chromium`). Détail : " + str(exc)
        ) from exc
