import policy
import pytest


@pytest.mark.parametrize(
    "history,expected",
    [
        ([], 0.0),
        ([1], 0.5),
        ([1, 1], 0.8),
        ([1, 1, 1], 1.0),
        ([0, 1, 1, 1, 1], 0.875),
        ([0, 1, 1, 1, 1, 1], 1.0),
        ([1, 1, 1, 1, 0], 3.0 / 4.0),
        ([1.5, -1], 0.5 / 1.95 * 0.95 / 0.95),
    ],
)
def test_compute_mastery_recency_and_cap(history, expected):
    if history == [1.5, -1]:
        # Credit is bounded to 0..1 before weighting.
        assert policy.compute_mastery(history) == pytest.approx(0.95 / 1.95)
    else:
        assert policy.compute_mastery(history) == pytest.approx(expected)


def _path(modules=None, **extra):
    base = {
        "modules": modules
        if modules is not None
        else [
            {
                "id": "m1",
                "name": "One",
                "objective": "do",
                "knowledge_points": [
                    {"id": "a", "name": "A", "type": "memory"},
                    {"id": "b", "name": "B", "type": "concept"},
                ],
            }
        ],
        "attempts": [],
        "pending": None,
        "qualitative": {},
        "repetition": {},
        "deferred": [],
        "overrides": {},
        "errors": [],
        "explained": {},
        "profile": {},
    }
    base.update(extra)
    return base


def _attempts(kp, credits):
    return [{"kp": kp, "credit": c, "voided": False, "independent": True} for c in credits]


def test_empty_outline_asks_for_design():
    assert policy.next_step(_path(modules=[]), now=0)["action"] == "design_outline"


def test_new_objective_probes_by_default_and_teaches_on_request():
    assert policy.next_step(_path(), now=0)["action"] == "probe"
    path = _path(profile={"teaching_strategy": "teach_first"})
    assert policy.next_step(path, now=0)["action"] == "teach"


def test_two_correct_answers_do_not_clear_a_memory_gate():
    path = _path(attempts=_attempts("a", [1, 1]))
    step = policy.next_step(path, now=0)
    assert step["kp_id"] == "a" and step["action"] == "practice"
    assert step["mastery"] == pytest.approx(0.8) and step["threshold"] == 0.9


def test_three_correct_clears_gate_and_moves_to_qualitative_objective():
    path = _path(attempts=_attempts("a", [1, 1, 1]))
    step = policy.next_step(path, now=0)
    assert step["kp_id"] == "b" and step["action"] == "probe" and step["gate"] == "qualitative"


def test_voided_attempts_are_ignored():
    attempts = _attempts("a", [1, 1, 1])
    attempts[0]["voided"] = True
    assert not policy.is_assessed_mastered(_path(attempts=attempts), {"id": "a", "type": "memory"})


def test_concept_needs_recorded_pass_not_score():
    path = _path(attempts=_attempts("a", [1, 1, 1]), qualitative={"b": True})
    assert policy.next_step(path, now=0)["action"] == "complete"


def test_pending_question_comes_first():
    pending = {"id": "q1", "kp": "b", "question": "Q?", "type": "short_answer", "expected": "secret"}
    step = policy.next_step(_path(pending=pending), now=0)
    assert step["action"] == "answer_pending"
    assert "secret" not in str(step)


def test_due_review_precedes_new_work_only_for_mastered_objectives():
    rep = {"next_review_at": 10.0, "last_review_at": 0.0, "stability": 1.0, "lapse_count": 0}
    mastered = _path(attempts=_attempts("a", [1, 1, 1]), repetition={"a": rep})
    assert policy.next_step(mastered, now=100.0)["action"] == "review"
    unmastered = _path(attempts=_attempts("a", [1]), repetition={"a": rep})
    assert policy.next_step(unmastered, now=100.0)["action"] == "practice"


def test_deferred_is_passed_over_but_returns_as_fallback():
    path = _path(deferred=["a"])
    assert policy.next_step(path, now=0)["kp_id"] == "b"
    path = _path(deferred=["a"], qualitative={"b": True})
    assert policy.next_step(path, now=0)["kp_id"] == "a"


def test_learner_override_advances_with_separate_provenance():
    path = _path(overrides={"a": {"quote": "I know this", "at": 0}})
    kp = {"id": "a", "type": "memory"}
    assert policy.mastery_source(path, kp) == "learner"
    assert not policy.is_assessed_mastered(path, kp)
    assert policy.next_step(path, now=0)["kp_id"] == "b"
    row = policy.map_summary(path, now=0)["modules"][0]["knowledge_points"][0]
    assert row["status"] == "mastered" and row["source"] == "learner"


def test_learning_stage_distinguishes_help_from_independence():
    path = _path()
    assert policy.learning_stage(path, "a") == "not_yet_covered"
    path = _path(explained={"a": {"quote": "x"}})
    assert policy.learning_stage(path, "a") == "partially_explained"
    path = _path(attempts=[{"kp": "a", "credit": 0.5, "independent": False, "voided": False}])
    assert policy.learning_stage(path, "a") == "practiced_with_help"
    path = _path(attempts=[{"kp": "a", "credit": 1, "independent": True, "voided": False}])
    assert policy.learning_stage(path, "a") == "independently_demonstrated"
