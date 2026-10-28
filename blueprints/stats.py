"""Partie statistique : consultation et gestion des résultats."""
from flask import (Blueprint, Response, abort, current_app, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required

import diplomas
from models import Answer, Attempt, Formulaire, Question, Theme, db

stats_bp = Blueprint("stats", __name__, url_prefix="/statistiques")


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


def get_attempt_or_403(attempt_id):
    att = db.session.get(Attempt, attempt_id) or abort(404)
    if not current_user.can_edit_theme(att.formulaire.theme):
        abort(403)
    return att


def form_summary(form):
    attempts = form.attempts
    n = len(attempts)
    avg = round(sum(a.score for a in attempts) / n, 1) if n else 0
    passed = sum(1 for a in attempts if a.passed)
    return {
        "form": form,
        "count": n,
        "avg": avg,
        "passed": passed,
        "pass_rate": round(100 * passed / n) if n else 0,
    }


def question_stats(question):
    total = Answer.query.filter_by(question_id=question.id).count()
    good = Answer.query.filter_by(question_id=question.id, is_correct=True).count()
    return {
        "question": question,
        "total": total,
        "good": good,
        "rate": round(100 * good / total) if total else None,
    }


# --------------------------------------------------------------------------- #
# Vue d'ensemble                                                               #
# --------------------------------------------------------------------------- #
@stats_bp.route("/")
@login_required
def overview():
    themes = visible_themes()
    data = []
    for theme in themes:
        summaries = [form_summary(f) for f in theme.formulaires]
        total_attempts = sum(s["count"] for s in summaries)
        graded = [s for s in summaries if s["count"]]
        avg = round(sum(s["avg"] * s["count"] for s in graded) / total_attempts, 1) if total_attempts else 0
        data.append({
            "theme": theme,
            "summaries": summaries,
            "total_attempts": total_attempts,
            "avg": avg,
        })
    # --- Données pour les graphiques ---
    from blueprints.admin import _tests_par_mois
    attempts = _visible_attempts_query().all()
    total = len(attempts)
    passed = sum(1 for a in attempts if a.passed)
    avg = round(sum(a.score or 0 for a in attempts) / total, 1) if total else 0
    kpis = {
        "total": total,
        "passed": passed,
        "pass_rate": round(100 * passed / total) if total else 0,
        "avg": avg,
        "stagiaires": len({a.email for a in attempts}),
    }
    monthly = _tests_par_mois()
    monthly_max = max((m["count"] for m in monthly), default=0)
    # Répartition par logiciel
    per = {}
    for a in attempts:
        t = a.formulaire.theme
        p = per.setdefault(t.id, {"name": t.name, "count": 0, "passed": 0, "sum": 0.0})
        p["count"] += 1
        p["sum"] += a.score or 0
        if a.passed:
            p["passed"] += 1
    per_theme = sorted(
        ({"name": p["name"], "count": p["count"],
          "pass_rate": round(100 * p["passed"] / p["count"]) if p["count"] else 0,
          "avg": round(p["sum"] / p["count"], 1) if p["count"] else 0}
         for p in per.values()),
        key=lambda x: x["count"], reverse=True)
    per_max = max((p["count"] for p in per_theme), default=0)
    # 10 derniers tests réalisés (toutes formations confondues)
    recents = sorted(attempts, key=lambda a: a.created_at, reverse=True)[:10]
    return render_template("stats/overview.html", data=data, kpis=kpis,
                           monthly=monthly, monthly_max=monthly_max,
                           per_theme=per_theme, per_max=per_max,
                           recents=recents)


# --------------------------------------------------------------------------- #
# Par logiciel                                                                    #
# --------------------------------------------------------------------------- #
@stats_bp.route("/theme/<int:theme_id>")
@login_required
def by_theme(theme_id):
    theme = get_theme_or_403(theme_id)
    summaries = [form_summary(f) for f in theme.formulaires]
    return render_template("stats/theme.html", theme=theme, summaries=summaries)


# --------------------------------------------------------------------------- #
# Par formulaire                                                               #
# --------------------------------------------------------------------------- #
@stats_bp.route("/formulaire/<int:form_id>")
@login_required
def by_form(form_id):
    form = get_form_or_403(form_id)
    summary = form_summary(form)
    q_stats = [question_stats(q) for q in form.questions]

    # Distribution des scores par tranche de 10 %
    buckets = [0] * 10
    for a in form.attempts:
        i = min(int(a.score // 10), 9)
        buckets[i] += 1
    distribution = [{"label": f"{i*10}-{i*10+10}", "count": c} for i, c in enumerate(buckets)]

    attempts = sorted(form.attempts, key=lambda a: a.created_at, reverse=True)
    return render_template(
        "stats/form.html",
        form=form, summary=summary, q_stats=q_stats,
        distribution=distribution, attempts=attempts,
    )


# --------------------------------------------------------------------------- #
# Détail d'une question                                                        #
# --------------------------------------------------------------------------- #
@stats_bp.route("/question/<int:question_id>")
@login_required
def by_question(question_id):
    q = db.session.get(Question, question_id) or abort(404)
    if not current_user.can_edit_theme(q.formulaire.theme):
        abort(403)
    answers = Answer.query.filter_by(question_id=q.id).all()
    total = len(answers)
    good = sum(1 for a in answers if a.is_correct)
    # Fréquence de sélection de chaque proposition
    choice_counts = {c.id: 0 for c in q.choices}
    for a in answers:
        for c in a.selected:
            if c.id in choice_counts:
                choice_counts[c.id] += 1
    choice_data = [{
        "choice": c,
        "count": choice_counts[c.id],
        "rate": round(100 * choice_counts[c.id] / total) if total else 0,
    } for c in q.choices]
    return render_template(
        "stats/question.html",
        question=q, total=total, good=good,
        rate=round(100 * good / total) if total else None,
        choice_data=choice_data,
    )


# --------------------------------------------------------------------------- #
# Toutes les réponses classées par logiciel et formulaire                        #
# --------------------------------------------------------------------------- #
@stats_bp.route("/reponses")
@login_required
def all_answers():
    themes = visible_themes()
    tree = []
    for theme in themes:
        forms = []
        for form in theme.formulaires:
            attempts = sorted(form.attempts, key=lambda a: a.created_at, reverse=True)
            if attempts:
                forms.append({"form": form, "attempts": attempts})
        if forms:
            tree.append({"theme": theme, "forms": forms})
    return render_template("stats/all_answers.html", tree=tree)


# --------------------------------------------------------------------------- #
# Détail d'une tentative + modification / suppression                         #
# --------------------------------------------------------------------------- #
@stats_bp.route("/tentative/<int:attempt_id>")
@login_required
def attempt_detail(attempt_id):
    att = get_attempt_or_403(attempt_id)
    rows = []
    for ans in att.answers:
        q = ans.question
        rows.append({
            "answer": ans,
            "question": q,
            "selected_ids": {c.id for c in ans.selected},
            "correct_ids": q.correct_ids,
        })
    issued = sorted(att.diplomas, key=lambda d: d.modele)
    return render_template("stats/attempt.html", attempt=att, rows=rows,
                           diploma_models=diplomas.MODELS, issued=issued)


@stats_bp.route("/tentative/<int:attempt_id>/modifier", methods=["POST"])
@login_required
def attempt_edit(attempt_id):
    att = get_attempt_or_403(attempt_id)
    email = request.form.get("email", "").strip().lower()
    if email:
        att.email = email
    if "first_name" in request.form:
        att.first_name = request.form.get("first_name", "").strip()
    if "last_name" in request.form:
        att.last_name = request.form.get("last_name", "").strip()
    att.recompute()
    db.session.commit()
    flash("Tentative mise à jour.", "success")
    return redirect(url_for("stats.attempt_detail", attempt_id=att.id))


# --------------------------------------------------------------------------- #
# Fiche stagiaire : toutes ses tentatives et diplômes                          #
# --------------------------------------------------------------------------- #
def _visible_attempts_query():
    """Tentatives des logiciels visibles par l'utilisateur courant."""
    q = Attempt.query.join(Formulaire)
    if not current_user.is_super_admin:
        theme_ids = [t.id for t in current_user.themes]
        if not theme_ids:
            return q.filter(db.false())
        q = q.filter(Formulaire.theme_id.in_(theme_ids))
    return q


@stats_bp.route("/stagiaires")
@login_required
def trainees():
    """Liste des stagiaires (clé = email), avec recherche."""
    q = (request.args.get("q") or "").strip().lower()
    people = {}
    for a in _visible_attempts_query().all():
        p = people.setdefault(a.email, {
            "email": a.email, "name": "", "attempts": 0, "passed": 0, "last": a.created_at})
        p["attempts"] += 1
        if a.passed:
            p["passed"] += 1
        if a.created_at >= p["last"]:
            p["last"] = a.created_at
            if a.first_name or a.last_name:
                p["name"] = a.full_name
        elif not p["name"] and (a.first_name or a.last_name):
            p["name"] = a.full_name
    rows = list(people.values())
    if q:
        rows = [r for r in rows if q in r["email"].lower() or q in (r["name"] or "").lower()]
    rows.sort(key=lambda r: (r["name"] or r["email"]).lower())
    return render_template("stats/trainees.html", rows=rows, q=request.args.get("q", ""))


@stats_bp.route("/stagiaire/<path:email>")
@login_required
def trainee(email):
    email = email.strip().lower()
    attempts = (_visible_attempts_query()
                .filter(Attempt.email == email)
                .order_by(Attempt.created_at.desc()).all())
    if not attempts:
        abort(404)
    # Nom le plus récent renseigné pour cet email
    display = next((a.full_name for a in attempts if a.first_name or a.last_name), email)
    # Diplômes archivés du stagiaire
    from models import Diploma
    att_ids = [a.id for a in attempts]
    issued = (Diploma.query.filter(Diploma.attempt_id.in_(att_ids))
              .order_by(Diploma.updated_at.desc()).all()) if att_ids else []
    att_by_id = {a.id: a for a in attempts}
    diploma_rows = [{"d": d, "attempt": att_by_id.get(d.attempt_id)} for d in issued]
    return render_template("stats/trainee.html", email=email, display=display,
                           attempts=attempts, diploma_models=diplomas.MODELS,
                           diploma_rows=diploma_rows)


@stats_bp.route("/stagiaire/<path:email>/supprimer", methods=["POST"])
@login_required
def trainee_delete(email):
    """Supprime un stagiaire : toutes ses tentatives, réponses et diplômes
    (dans le périmètre visible par l'utilisateur)."""
    import os
    email = email.strip().lower()
    attempts = _visible_attempts_query().filter(Attempt.email == email).all()
    if not attempts:
        abort(404)
    # Suppression des PDF archivés sur disque
    for a in attempts:
        for d in list(a.diplomas):
            if d.filename:
                try:
                    os.remove(os.path.join(diplomas.diplomas_dir(current_app.root_path), d.filename))
                except OSError:
                    pass
        db.session.delete(a)
    db.session.commit()
    flash("Stagiaire supprimé : toutes ses tentatives et certifications ont été effacées.", "info")
    return redirect(url_for("stats.trainees"))


# --------------------------------------------------------------------------- #
# Classement par stagiaire (filtre par logiciel)                                 #
# --------------------------------------------------------------------------- #
@stats_bp.route("/classement")
@login_required
def ranking():
    themes = visible_themes()
    theme_id = request.args.get("theme", type=int)
    q = _visible_attempts_query()
    selected = None
    if theme_id:
        selected = get_theme_or_403(theme_id)
        q = q.filter(Formulaire.theme_id == theme_id)
    attempts = q.all()

    # Agrégation par stagiaire (clé = email)
    stats = {}
    for a in attempts:
        s = stats.setdefault(a.email, {
            "email": a.email, "name": "", "attempts": 0,
            "passed": 0, "best": 0.0, "last": a.created_at,
        })
        s["attempts"] += 1
        if a.passed:
            s["passed"] += 1
        s["best"] = max(s["best"], a.score or 0.0)
        if a.created_at >= s["last"]:
            s["last"] = a.created_at
            if a.first_name or a.last_name:
                s["name"] = a.full_name
        elif not s["name"] and (a.first_name or a.last_name):
            s["name"] = a.full_name
    rows = sorted(stats.values(),
                  key=lambda s: (-s["passed"], -s["best"], (s["name"] or s["email"]).lower()))
    return render_template("stats/ranking.html", rows=rows, themes=themes,
                           selected=selected)


# --------------------------------------------------------------------------- #
# Réédition d'un diplôme par l'administrateur                                   #
# --------------------------------------------------------------------------- #
@stats_bp.route("/tentative/<int:attempt_id>/diplome")
@login_required
def attempt_diploma(attempt_id):
    att = get_attempt_or_403(attempt_id)
    if not att.passed:
        flash("Pas de certification : cette tentative n'est pas réussie.", "error")
        return redirect(url_for("stats.attempt_detail", attempt_id=att.id))
    if not att.formulaire.diploma_enabled:
        flash("Les certifications sont désactivées pour ce test.", "error")
        return redirect(url_for("stats.attempt_detail", attempt_id=att.id))
    diplomas.ensure_certificate_number(att)
    modele = diplomas.clean_model(request.args.get("modele"))
    ctx = diplomas.certificate_context(att, current_app.root_path)
    ctx["modele"] = modele
    html = render_template("diploma/certificate.html", **ctx)
    try:
        pdf = diplomas.render_pdf(html)
    except diplomas.DiplomaRenderError as exc:
        current_app.logger.error("Diplôme PDF indisponible : %s", exc)
        flash("Génération de la certification indisponible : vérifiez l'installation de "
              "Chromium (playwright install chromium).", "error")
        return redirect(url_for("stats.attempt_detail", attempt_id=att.id))
    try:
        diplomas.record_download(att, modele, pdf, current_app.root_path)
    except Exception as exc:
        current_app.logger.warning("Archivage diplôme échoué : %s", exc)
    resp = Response(pdf, mimetype="application/pdf")
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="{diplomas.safe_filename(att)}"')
    return resp


@stats_bp.route("/diplome/<int:diploma_id>/fichier")
@login_required
def diploma_file(diploma_id):
    """Télécharge le PDF archivé d'un diplôme déjà émis."""
    import os
    from models import Diploma
    dip = db.session.get(Diploma, diploma_id) or abort(404)
    att = dip.attempt
    if att is None or not current_user.can_edit_theme(att.formulaire.theme):
        abort(403)
    path = os.path.join(diplomas.diplomas_dir(current_app.root_path), dip.filename or "")
    if not dip.filename or not os.path.exists(path):
        flash("Fichier archivé introuvable. Régénérez la certification.", "error")
        return redirect(url_for("stats.attempt_detail", attempt_id=att.id))
    with open(path, "rb") as fh:
        pdf = fh.read()
    resp = Response(pdf, mimetype="application/pdf")
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="{diplomas.safe_filename(att)}"')
    return resp


@stats_bp.route("/tentative/<int:attempt_id>/supprimer", methods=["POST"])
@login_required
def attempt_delete(attempt_id):
    att = get_attempt_or_403(attempt_id)
    form_id = att.formulaire_id
    db.session.delete(att)
    db.session.commit()
    flash("Tentative supprimée.", "info")
    return redirect(url_for("stats.by_form", form_id=form_id))


@stats_bp.route("/reponse/<int:answer_id>/basculer", methods=["POST"])
@login_required
def answer_toggle(answer_id):
    ans = db.session.get(Answer, answer_id) or abort(404)
    if not current_user.can_edit_theme(ans.attempt.formulaire.theme):
        abort(403)
    ans.is_correct = not ans.is_correct
    ans.attempt.recompute()
    db.session.commit()
    flash("Réponse modifiée.", "success")
    return redirect(url_for("stats.attempt_detail", attempt_id=ans.attempt_id))


@stats_bp.route("/reponse/<int:answer_id>/supprimer", methods=["POST"])
@login_required
def answer_delete(answer_id):
    ans = db.session.get(Answer, answer_id) or abort(404)
    if not current_user.can_edit_theme(ans.attempt.formulaire.theme):
        abort(403)
    attempt = ans.attempt
    db.session.delete(ans)
    db.session.flush()
    attempt.recompute()
    db.session.commit()
    flash("Réponse supprimée.", "info")
    return redirect(url_for("stats.attempt_detail", attempt_id=attempt.id))
