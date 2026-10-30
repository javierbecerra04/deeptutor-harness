"""Deterministic grading. Ported from DeepTutor's deeptutor/learning/grading.py (Apache-2.0)."""
from difflib import SequenceMatcher

ENGINE_GRADED = ("choice", "true_false")
OPEN_TYPES = ("short_answer", "written", "coding")
TRUE_WORDS = {"true", "t", "yes", "y"}
FALSE_WORDS = {"false", "f", "no", "n"}


def _norm(text):
    return " ".join(str(text).strip().lower().split())


def grade_choice(options, expected, answer):
    """True or False, or None when the answer names no option."""
    given = _norm(answer)
    if not given:
        return False
    for opt in options:
        if given in (_norm(opt["label"]), _norm(opt["body"])):
            return opt["label"] == expected
    return None


def grade_true_false(expected, answer):
    given = _norm(answer)
    if not given:
        return False
    if given in TRUE_WORDS:
        return expected == "true"
    if given in FALSE_WORDS:
        return expected == "false"
    return None


def fuzzy_match(expected, answer):
    user, want = _norm(answer), _norm(expected)
    if not want:
        return False
    if user == want:
        return True
    return len(want) <= 30 and SequenceMatcher(None, user, want).ratio() >= 0.85


def classify_error(answer):
    """A blank answer means the learner did not know; the rest is a wrong application."""
    return "metacognitive" if not str(answer).strip() else "application"
