"""Fonctions et décorateurs partagés entre les blueprints."""
import os
import secrets
from functools import wraps

from flask import abort, current_app
from flask_login import current_user
from werkzeug.utils import secure_filename


def super_admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_super_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


def save_question_image(file_storage):
    """Enregistre une image de question et renvoie son nom de fichier, ou None."""
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    name = f"{secrets.token_hex(16)}.{ext}"
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], name)
    file_storage.save(path)
    return name


def delete_question_image(filename):
    if not filename:
        return
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    try:
        os.remove(path)
    except OSError:
        pass
