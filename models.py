"""Modèles de données : utilisateurs, thèmes, formulaires, questions, résultats."""
import secrets
from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


# --- Table d'association : un utilisateur administre plusieurs thèmes ---------
user_themes = db.Table(
    "user_themes",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    db.Column("theme_id", db.Integer, db.ForeignKey("theme.id", ondelete="CASCADE"), primary_key=True),
)

# --- Table d'association : réponse d'un stagiaire -> cases cochées ------------
answer_choices = db.Table(
    "answer_choices",
    db.Column("answer_id", db.Integer, db.ForeignKey("answer.id", ondelete="CASCADE"), primary_key=True),
    db.Column("choice_id", db.Integer, db.ForeignKey("choice.id", ondelete="CASCADE"), primary_key=True),
)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_super_admin = db.Column(db.Boolean, default=False, nullable=False)
    reset_token = db.Column(db.String(80), nullable=True)
    reset_token_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    themes = db.relationship(
        "Theme", secondary=user_themes, back_populates="admins", lazy="joined"
    )

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw, method="pbkdf2:sha256")

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    def new_reset_token(self):
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_at = datetime.utcnow()
        return self.reset_token

    def clear_reset_token(self):
        self.reset_token = None
        self.reset_token_at = None

    def can_edit_theme(self, theme):
        return self.is_super_admin or theme in self.themes


class Setting(db.Model):
    """Paramètre applicatif global (clé/valeur), ex. filtre IP."""
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, nullable=True)


class Theme(db.Model):
    """Une famille qui regroupe plusieurs formulaires."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    admins = db.relationship("User", secondary=user_themes, back_populates="themes")
    formulaires = db.relationship(
        "Formulaire", back_populates="theme",
        cascade="all, delete-orphan", order_by="Formulaire.title",
    )


class Formulaire(db.Model):
    """Un formulaire qui regroupe plusieurs questions."""
    id = db.Column(db.Integer, primary_key=True)
    theme_id = db.Column(db.Integer, db.ForeignKey("theme.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    success_threshold = db.Column(db.Integer, default=70)  # % de réussite requis
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    public_token = db.Column(db.String(40), unique=True, index=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    theme = db.relationship("Theme", back_populates="formulaires")
    questions = db.relationship(
        "Question", back_populates="formulaire",
        cascade="all, delete-orphan", order_by="Question.position",
    )
    attempts = db.relationship(
        "Attempt", back_populates="formulaire", cascade="all, delete-orphan"
    )

    @staticmethod
    def make_token():
        return secrets.token_urlsafe(24)


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    formulaire_id = db.Column(db.Integer, db.ForeignKey("formulaire.id", ondelete="CASCADE"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    explanation = db.Column(db.Text, default="")  # détail affiché sur les résultats
    image_filename = db.Column(db.String(255), nullable=True)
    position = db.Column(db.Integer, default=0)

    formulaire = db.relationship("Formulaire", back_populates="questions")
    choices = db.relationship(
        "Choice", back_populates="question",
        cascade="all, delete-orphan", order_by="Choice.id",
    )

    @property
    def correct_ids(self):
        return {c.id for c in self.choices if c.is_correct}


class Choice(db.Model):
    """Une proposition de réponse (choix multiple)."""
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id", ondelete="CASCADE"), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    is_correct = db.Column(db.Boolean, default=False, nullable=False)

    question = db.relationship("Question", back_populates="choices")


class Attempt(db.Model):
    """Une exécution d'un formulaire par un stagiaire."""
    id = db.Column(db.Integer, primary_key=True)
    formulaire_id = db.Column(db.Integer, db.ForeignKey("formulaire.id", ondelete="CASCADE"), nullable=False)
    email = db.Column(db.String(180), nullable=False, index=True)
    score = db.Column(db.Float, default=0.0)  # pourcentage
    passed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    formulaire = db.relationship("Formulaire", back_populates="attempts")
    answers = db.relationship(
        "Answer", back_populates="attempt", cascade="all, delete-orphan"
    )

    def recompute(self):
        total = len(self.answers)
        good = sum(1 for a in self.answers if a.is_correct)
        self.score = round(100 * good / total, 1) if total else 0.0
        threshold = self.formulaire.success_threshold if self.formulaire else 0
        self.passed = self.score >= threshold


class Answer(db.Model):
    """Réponse d'un stagiaire à une question, dans une exécution donnée."""
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("attempt.id", ondelete="CASCADE"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id", ondelete="CASCADE"), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)

    attempt = db.relationship("Attempt", back_populates="answers")
    question = db.relationship("Question")
    selected = db.relationship("Choice", secondary=answer_choices)
