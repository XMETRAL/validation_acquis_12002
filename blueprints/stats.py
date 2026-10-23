"""Partie statistique : consultation et gestion des résultats."""
from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required

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
    return render_template("stats/overview.html", data=data)


# --------------------------------------------------------------------------- #
# Par thème                                                                    #
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
# Toutes les réponses classées par thème et formulaire                        #
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
    return render_template("stats/attempt.html", attempt=att, rows=rows)


@stats_bp.route("/tentative/<int:attempt_id>/modifier", methods=["POST"])
@login_required
def attempt_edit(attempt_id):
    att = get_attempt_or_403(attempt_id)
    email = request.form.get("email", "").strip().lower()
    if email:
        att.email = email
    att.recompute()
    db.session.commit()
    flash("Tentative mise à jour.", "success")
    return redirect(url_for("stats.attempt_detail", attempt_id=att.id))


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
