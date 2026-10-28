"""Partie administration : utilisateurs, logiciels, formulaires, questions."""
from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required

from models import Choice, Formulaire, Question, Theme, User, db

from .utils import (delete_question_image, save_question_image,
                    super_admin_required)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def visible_themes():
    if current_user.is_super_admin:
        return Theme.query.order_by(Theme.name).all()
    return sorted(current_user.themes, key=lambda t: t.name.lower())


def get_theme_or_403(theme_id):
    theme = db.session.get(Theme, theme_id) or abort(404)
    if not current_user.can_edit_theme(theme):
        abort(403)
    return theme


def get_form_or_403(form_id):
    form = db.session.get(Formulaire, form_id) or abort(404)
    if not current_user.can_edit_theme(form.theme):
        abort(403)
    return form


def get_question_or_403(question_id):
    q = db.session.get(Question, question_id) or abort(404)
    if not current_user.can_edit_theme(q.formulaire.theme):
        abort(403)
    return q


def parse_choices():
    """Renvoie (liste de (texte, is_correct), message d'erreur ou None)."""
    texts = request.form.getlist("choice_text")
    flags = request.form.getlist("choice_is_correct")
    rows = []
    for text, flag in zip(texts, flags):
        text = text.strip()
        if text:
            rows.append((text, flag == "1"))
    if len(rows) < 2:
        return rows, "Une question doit proposer au moins deux réponses."
    if not any(is_ok for _, is_ok in rows):
        return rows, "Au moins une réponse doit être marquée comme correcte."
    if len(rows) == 2 and all(is_ok for _, is_ok in rows):
        return rows, "Avec deux réponses, une seule peut être marquée comme correcte."
    return rows, None


# --------------------------------------------------------------------------- #
# Tableau de bord                                                              #
# --------------------------------------------------------------------------- #
@admin_bp.route("/")
@login_required
def dashboard():
    themes = visible_themes()
    monthly = _tests_par_mois()
    return render_template(
        "admin/dashboard.html", themes=themes, monthly=monthly,
        monthly_total=sum(d["count"] for d in monthly),
        monthly_max=max((d["count"] for d in monthly), default=0))


_MOIS_ABBR = ["", "janv.", "févr.", "mars", "avr.", "mai", "juin",
              "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def _derniers_12_mois():
    from datetime import datetime
    now = datetime.utcnow()
    seq, yy, mm = [], now.year, now.month
    for _ in range(12):
        seq.append((yy, mm))
        mm -= 1
        if mm == 0:
            mm, yy = 12, yy - 1
    seq.reverse()
    return seq


def _tests_par_mois():
    """Nombre de tests réalisés par mois sur les 12 derniers mois glissants."""
    from datetime import datetime
    from models import Attempt
    seq = _derniers_12_mois()
    start = datetime(seq[0][0], seq[0][1], 1)
    counts = {ym: 0 for ym in seq}
    q = Attempt.query.join(Formulaire).filter(Attempt.created_at >= start)
    if not current_user.is_super_admin:
        theme_ids = [t.id for t in current_user.themes]
        q = q.filter(Formulaire.theme_id.in_(theme_ids)) if theme_ids else q.filter(db.false())
    for a in q.all():
        key = (a.created_at.year, a.created_at.month)
        if key in counts:
            counts[key] += 1
    return [{"label": _MOIS_ABBR[mm], "ym": f"{_MOIS_ABBR[mm]} {str(yy)[2:]}",
             "count": counts[(yy, mm)]} for (yy, mm) in seq]


# --------------------------------------------------------------------------- #
# Logiciels                                                                       #
# --------------------------------------------------------------------------- #
@admin_bp.route("/themes/nouveau", methods=["GET", "POST"])
@login_required
@super_admin_required
def theme_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Le nom du logiciel est obligatoire.", "error")
        else:
            theme = Theme(
                name=name,
                description=request.form.get("description", "").strip(),
                diploma_line1=request.form.get("diploma_line1", "").strip(),
            )
            admin_ids = request.form.getlist("admins")
            theme.admins = User.query.filter(User.id.in_(admin_ids)).all()
            db.session.add(theme)
            db.session.commit()
            flash("Logiciel créé.", "success")
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/theme_form.html", theme=None, users=User.query.order_by(User.name).all())


@admin_bp.route("/themes/<int:theme_id>/modifier", methods=["GET", "POST"])
@login_required
def theme_edit(theme_id):
    theme = get_theme_or_403(theme_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Le nom du logiciel est obligatoire.", "error")
        else:
            theme.name = name
            theme.description = request.form.get("description", "").strip()
            theme.diploma_line1 = request.form.get("diploma_line1", "").strip()
            if current_user.is_super_admin:
                admin_ids = request.form.getlist("admins")
                theme.admins = User.query.filter(User.id.in_(admin_ids)).all()
            db.session.commit()
            flash("Logiciel mis à jour.", "success")
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/theme_form.html", theme=theme, users=User.query.order_by(User.name).all())


@admin_bp.route("/themes/<int:theme_id>/supprimer", methods=["POST"])
@login_required
@super_admin_required
def theme_delete(theme_id):
    theme = db.session.get(Theme, theme_id) or abort(404)
    for form in theme.formulaires:
        for q in form.questions:
            delete_question_image(q.image_filename)
    db.session.delete(theme)
    db.session.commit()
    flash("Logiciel supprimé.", "info")
    return redirect(url_for("admin.dashboard"))


# --------------------------------------------------------------------------- #
# Formulaires                                                                  #
# --------------------------------------------------------------------------- #
@admin_bp.route("/themes/<int:theme_id>/formulaires/nouveau", methods=["GET", "POST"])
@login_required
def form_create(theme_id):
    theme = get_theme_or_403(theme_id)
    if request.method == "POST":
        title = request.form.get("title", "").strip()  # = Description (nom du test)
        if not title:
            flash("La description (nom du test) est obligatoire.", "error")
        else:
            form = Formulaire(
                theme=theme,
                title=title,
                diploma_line1=request.form.get("diploma_line1", "").strip(),  # Logiciel
                diploma_label=request.form.get("diploma_label", "").strip(),  # Formation
                diploma_enabled=bool(request.form.get("diploma_enabled")),
                success_threshold=_clamp_threshold(request.form.get("success_threshold")),
                is_active=bool(request.form.get("is_active")),
                public_token=Formulaire.make_token(),
            )
            db.session.add(form)
            db.session.commit()
            flash("Formulaire créé. Ajoutez maintenant des questions.", "success")
            return redirect(url_for("admin.form_detail", form_id=form.id))
    return render_template("admin/form_edit.html", form=None, theme=theme)


@admin_bp.route("/formulaires/<int:form_id>")
@login_required
def form_detail(form_id):
    form = get_form_or_403(form_id)
    public_url = url_for("public.start", token=form.public_token, _external=True)
    # Données de l'onglet Statistiques (mêmes calculs que la page stats)
    from blueprints.stats import form_summary, question_stats
    summary = form_summary(form)
    q_stats = [question_stats(q) for q in form.questions]
    buckets = [0] * 10
    for a in form.attempts:
        buckets[min(int((a.score or 0) // 10), 9)] += 1
    distribution = [{"label": f"{i*10}-{i*10+10}", "count": c}
                    for i, c in enumerate(buckets)]
    attempts = sorted(form.attempts, key=lambda a: a.created_at, reverse=True)
    return render_template(
        "admin/form_detail.html", form=form, public_url=public_url,
        summary=summary, q_stats=q_stats, distribution=distribution,
        attempts=attempts,
    )


@admin_bp.route("/formulaires/<int:form_id>/modifier", methods=["GET", "POST"])
@login_required
def form_edit(form_id):
    form = get_form_or_403(form_id)
    if request.method == "POST":
        title = request.form.get("title", "").strip()  # = Description (nom du test)
        if not title:
            flash("La description (nom du test) est obligatoire.", "error")
        else:
            form.title = title
            form.diploma_line1 = request.form.get("diploma_line1", "").strip()  # Logiciel
            form.diploma_label = request.form.get("diploma_label", "").strip()  # Formation
            form.diploma_enabled = bool(request.form.get("diploma_enabled"))
            form.success_threshold = _clamp_threshold(request.form.get("success_threshold"))
            form.is_active = bool(request.form.get("is_active"))
            db.session.commit()
            flash("Formulaire mis à jour.", "success")
            return redirect(url_for("admin.form_detail", form_id=form.id))
    return render_template("admin/form_edit.html", form=form, theme=form.theme)


@admin_bp.route("/formulaires/<int:form_id>/supprimer", methods=["POST"])
@login_required
def form_delete(form_id):
    form = get_form_or_403(form_id)
    theme_id = form.theme_id
    for q in form.questions:
        delete_question_image(q.image_filename)
    db.session.delete(form)
    db.session.commit()
    flash("Formulaire supprimé.", "info")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/formulaires/<int:form_id>/token", methods=["POST"])
@login_required
def form_regen_token(form_id):
    form = get_form_or_403(form_id)
    # Mot de passe exigé, configurable via .env2 (REGEN_PASSWORD), défaut « aaaaaa »
    attendu = current_app.config.get("REGEN_PASSWORD", "aaaaaa")
    if request.form.get("regen_password", "") != attendu:
        flash("Mot de passe incorrect : le lien n'a pas été régénéré.", "error")
        return redirect(url_for("admin.form_detail", form_id=form.id))
    form.public_token = Formulaire.make_token()
    db.session.commit()
    flash("Nouveau lien généré. L'ancien lien ne fonctionne plus.", "info")
    return redirect(url_for("admin.form_detail", form_id=form.id))


def _clamp_threshold(value):
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 70
    return max(0, min(100, v))


# --------------------------------------------------------------------------- #
# Questions                                                                    #
# --------------------------------------------------------------------------- #
@admin_bp.route("/formulaires/<int:form_id>/questions/nouvelle", methods=["GET", "POST"])
@login_required
def question_create(form_id):
    form = get_form_or_403(form_id)
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        rows, err = parse_choices()
        if not text:
            err = "L'intitulé de la question est obligatoire."
        if err:
            flash(err, "error")
            return render_template("admin/question_form.html", form=form, question=None,
                                   posted={"text": text, "explanation": request.form.get("explanation", "")})
        position = (max((q.position for q in form.questions), default=0) + 1)
        q = Question(
            formulaire=form, text=text,
            explanation=request.form.get("explanation", "").strip(),
            position=position,
            image_filename=save_question_image(request.files.get("image")),
        )
        for ctext, is_ok in rows:
            q.choices.append(Choice(text=ctext, is_correct=is_ok))
        db.session.add(q)
        db.session.commit()
        flash("Question ajoutée.", "success")
        return redirect(url_for("admin.form_detail", form_id=form.id))
    return render_template("admin/question_form.html", form=form, question=None, posted=None)


@admin_bp.route("/questions/<int:question_id>/modifier", methods=["GET", "POST"])
@login_required
def question_edit(question_id):
    q = get_question_or_403(question_id)
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        rows, err = parse_choices()
        if not text:
            err = "L'intitulé de la question est obligatoire."
        if err:
            flash(err, "error")
            return render_template("admin/question_form.html", form=q.formulaire, question=q, posted=None)
        q.text = text
        q.explanation = request.form.get("explanation", "").strip()
        # Gestion de l'image
        if request.form.get("remove_image"):
            delete_question_image(q.image_filename)
            q.image_filename = None
        new_image = save_question_image(request.files.get("image"))
        if new_image:
            delete_question_image(q.image_filename)
            q.image_filename = new_image
        # Remplacement des réponses
        q.choices.clear()
        for ctext, is_ok in rows:
            q.choices.append(Choice(text=ctext, is_correct=is_ok))
        db.session.commit()
        flash("Question mise à jour.", "success")
        return redirect(url_for("admin.form_detail", form_id=q.formulaire_id))
    return render_template("admin/question_form.html", form=q.formulaire, question=q, posted=None)


@admin_bp.route("/questions/<int:question_id>/supprimer", methods=["POST"])
@login_required
def question_delete(question_id):
    q = get_question_or_403(question_id)
    form_id = q.formulaire_id
    delete_question_image(q.image_filename)
    db.session.delete(q)
    db.session.commit()
    flash("Question supprimée.", "info")
    return redirect(url_for("admin.form_detail", form_id=form_id))


# --------------------------------------------------------------------------- #
# Utilisateurs (super administrateur uniquement)                              #
# --------------------------------------------------------------------------- #
@admin_bp.route("/utilisateurs")
@login_required
@super_admin_required
def users():
    return render_template("admin/users.html", users=User.query.order_by(User.name).all())


@admin_bp.route("/utilisateurs/nouveau", methods=["GET", "POST"])
@login_required
@super_admin_required
def user_create():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        if not email or not name:
            flash("Email et nom sont obligatoires.", "error")
        elif len(password) < 8:
            flash("Le mot de passe doit contenir au moins 8 caractères.", "error")
        elif User.query.filter_by(email=email).first():
            flash("Un utilisateur avec cet email existe déjà.", "error")
        else:
            user = User(email=email, name=name,
                        is_super_admin=bool(request.form.get("is_super_admin")))
            user.set_password(password)
            user.themes = Theme.query.filter(Theme.id.in_(request.form.getlist("themes"))).all()
            db.session.add(user)
            db.session.commit()
            flash("Utilisateur créé.", "success")
            return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", user=None, themes=Theme.query.order_by(Theme.name).all())


@admin_bp.route("/utilisateurs/<int:user_id>/modifier", methods=["GET", "POST"])
@login_required
@super_admin_required
def user_edit(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            user.name = name
        password = request.form.get("password", "")
        if password:
            if len(password) < 8:
                flash("Le mot de passe doit contenir au moins 8 caractères.", "error")
                return render_template("admin/user_form.html", user=user, themes=Theme.query.order_by(Theme.name).all())
            user.set_password(password)
        # On évite de retirer le dernier super administrateur
        wants_super = bool(request.form.get("is_super_admin"))
        if not wants_super and user.is_super_admin and User.query.filter_by(is_super_admin=True).count() <= 1:
            flash("Impossible : il doit rester au moins un super administrateur.", "error")
        else:
            user.is_super_admin = wants_super
        user.themes = Theme.query.filter(Theme.id.in_(request.form.getlist("themes"))).all()
        db.session.commit()
        flash("Utilisateur mis à jour.", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", user=user, themes=Theme.query.order_by(Theme.name).all())


@admin_bp.route("/securite", methods=["GET", "POST"])
@login_required
@super_admin_required
def securite():
    """Filtre d'accès par IP publique : activation + liste blanche (IP/CIDR)."""
    import parametres as P
    if request.method == "POST":
        actif = "1" if request.form.get("ip_filtre_actif") == "on" else "0"
        # Éditeur à deux colonnes : une ligne par IP (champ « ip » + « desc »).
        ips = request.form.getlist("ip")
        descs = request.form.getlist("desc")
        lignes = []
        for i, ip in enumerate(ips):
            ip = (ip or "").strip()
            if not ip:
                continue
            desc = (descs[i] if i < len(descs) else "").strip()
            lignes.append(f"{ip} | {desc}" if desc else ip)
        liste = "\n".join(lignes)
        P.set_param("ip_filtre_actif", actif)
        P.set_param("ip_autorisees", liste)
        if actif == "1" and not P.parse_liste_ips(liste):
            flash("Filtre activé mais aucune adresse autorisée : aucun blocage "
                  "n'est appliqué tant que la liste est vide.", "error")
        else:
            flash("Filtre IP enregistré.", "success")
        return redirect(url_for("admin.securite"))
    actif = P.get_param("ip_filtre_actif", "0") == "1"
    liste = P.get_param("ip_autorisees", "") or ""
    ip_courante = P.ip_client()
    return render_template("admin/securite.html", actif=actif, liste=liste,
                           ip_courante=ip_courante,
                           entrees=P.parse_entrees(liste))


@admin_bp.route("/utilisateurs/<int:user_id>/supprimer", methods=["POST"])
@login_required
@super_admin_required
def user_delete(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.id == current_user.id:
        flash("Vous ne pouvez pas supprimer votre propre compte.", "error")
    elif user.is_super_admin and User.query.filter_by(is_super_admin=True).count() <= 1:
        flash("Impossible : il doit rester au moins un super administrateur.", "error")
    else:
        db.session.delete(user)
        db.session.commit()
        flash("Utilisateur supprimé.", "info")
    return redirect(url_for("admin.users"))
