"""Partie utilisation : le stagiaire répond au questionnaire depuis une URL."""
import random
import re

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   session, url_for)

from models import Answer, Attempt, Choice, Formulaire, Question, db

public_bp = Blueprint("public", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _get_form(token):
    form = Formulaire.query.filter_by(public_token=token).first() or abort(404)
    return form


def _state():
    return session.get("quiz")


def _question_success_rate(question_id):
    """Pourcentage de réussite de tous les stagiaires sur une question."""
    total = Answer.query.filter_by(question_id=question_id).count()
    if not total:
        return None
    good = Answer.query.filter_by(question_id=question_id, is_correct=True).count()
    return round(100 * good / total)


@public_bp.route("/f/<token>", methods=["GET"])
def start(token):
    form = _get_form(token)
    if not form.is_active:
        return render_template("public/closed.html", form=form)
    if not form.questions:
        return render_template("public/closed.html", form=form, empty=True)
    return render_template("public/start.html", form=form)


@public_bp.route("/f/<token>/demarrer", methods=["POST"])
def begin(token):
    form = _get_form(token)
    if not form.is_active or not form.questions:
        return redirect(url_for("public.start", token=token))
    email = request.form.get("email", "").strip().lower()
    if not EMAIL_RE.match(email):
        flash("Merci de saisir une adresse email valide.", "error")
        return redirect(url_for("public.start", token=token))

    order = [q.id for q in form.questions]
    random.shuffle(order)
    session["quiz"] = {
        "token": token,
        "email": email,
        "order": order,
        "idx": 0,
        "answers": {},
        "attempt_id": None,
    }
    session.modified = True
    return redirect(url_for("public.question", token=token))


@public_bp.route("/f/<token>/question", methods=["GET"])
def question(token):
    form = _get_form(token)
    state = _state()
    if not state or state.get("token") != token:
        return redirect(url_for("public.start", token=token))
    idx = state["idx"]
    if idx >= len(state["order"]):
        return redirect(url_for("public.result", token=token))

    q = db.session.get(Question, state["order"][idx])
    if not q:  # question supprimée entre-temps
        state["order"].pop(idx)
        session.modified = True
        return redirect(url_for("public.question", token=token))

    choices = list(q.choices)
    random.shuffle(choices)
    return render_template(
        "public/question.html",
        form=form, question=q, choices=choices,
        number=idx + 1, total=len(state["order"]),
    )


@public_bp.route("/f/<token>/reponse", methods=["POST"])
def answer(token):
    _get_form(token)
    state = _state()
    if not state or state.get("token") != token:
        return redirect(url_for("public.start", token=token))
    idx = state["idx"]
    if idx >= len(state["order"]):
        return redirect(url_for("public.result", token=token))

    qid = state["order"][idx]
    selected = request.form.getlist("choice")  # ids des cases cochées
    q = db.session.get(Question, qid)
    if q and len(q.choices) == 2:
        selected = selected[:1]  # deux propositions : une seule réponse admise
    state["answers"][str(qid)] = selected
    state["idx"] = idx + 1
    session.modified = True

    if state["idx"] >= len(state["order"]):
        return redirect(url_for("public.result", token=token))
    return redirect(url_for("public.question", token=token))


@public_bp.route("/f/<token>/resultat", methods=["GET"])
def result(token):
    form = _get_form(token)
    state = _state()
    if not state or state.get("token") != token:
        return redirect(url_for("public.start", token=token))

    # Persistance une seule fois (résiste au rafraîchissement de la page)
    attempt = None
    if state.get("attempt_id"):
        attempt = db.session.get(Attempt, state["attempt_id"])
    if attempt is None:
        attempt = _persist_attempt(form, state)
        state["attempt_id"] = attempt.id
        session.modified = True

    # Construction de l'affichage détaillé
    details = []
    for ans in attempt.answers:
        q = ans.question
        details.append({
            "question": q,
            "selected_ids": {c.id for c in ans.selected},
            "correct_ids": q.correct_ids,
            "is_correct": ans.is_correct,
            "success_rate": _question_success_rate(q.id),
        })

    return render_template(
        "public/result.html",
        form=form, attempt=attempt, details=details,
        threshold=form.success_threshold,
    )


def _persist_attempt(form, state):
    attempt = Attempt(formulaire_id=form.id, email=state["email"])
    db.session.add(attempt)
    for qid in state["order"]:
        q = db.session.get(Question, qid)
        if not q:
            continue
        selected_ids = {int(c) for c in state["answers"].get(str(qid), []) if str(c).isdigit()}
        valid_ids = {c.id for c in q.choices}
        selected_ids &= valid_ids
        is_correct = (selected_ids == q.correct_ids) and bool(q.correct_ids)
        ans = Answer(question_id=q.id, is_correct=is_correct)
        ans.selected = Choice.query.filter(Choice.id.in_(selected_ids)).all() if selected_ids else []
        attempt.answers.append(ans)
    db.session.flush()
    attempt.recompute()
    db.session.commit()
    return attempt
