import json
import os
import subprocess
from pathlib import Path

import pytest
import scheduler

DAY = 86400.0


def test_memory_starts_due_and_stability_grows_on_spaced_success():
    state = scheduler.initial_state("memory", now=0.0)
    assert state["next_review_at"] == 0.0
    scheduler.schedule_review(state, "memory", quality=1.0, now=0.0)
    first = state["stability"]
    assert first > 0.5 and state["next_review_at"] > 0.0
    scheduler.schedule_review(state, "memory", quality=1.0, now=3 * DAY)
    assert state["stability"] > first


def test_same_session_repeat_does_not_inflate_stability():
    state = scheduler.initial_state("concept", now=0.0)
    scheduler.schedule_review(state, "concept", quality=1.0, now=0.0)
    before = (state["stability"], state["next_review_at"])
    scheduler.schedule_review(state, "concept", quality=1.0, now=60.0)
    assert (state["stability"], state["next_review_at"]) == before
    assert state["review_count"] == 2


def test_failure_shrinks_stability_and_counts_a_lapse():
    state = scheduler.initial_state("procedure", now=0.0)
    scheduler.schedule_review(state, "procedure", quality=1.0, now=0.0)
    before = state["stability"]
    scheduler.schedule_review(state, "procedure", quality=0.0, now=10 * DAY)
    assert state["stability"] < before
    assert state["lapse_count"] == 1 and state["scheduled_after_failure"] is True


def test_forgetting_risk_rises_with_overdue_errors_and_lapses():
    state = scheduler.initial_state("memory", now=0.0)
    scheduler.schedule_review(state, "memory", quality=1.0, now=0.0)
    fresh = scheduler.forgetting_risk(state, has_active_error=False, now=0.0)
    late = scheduler.forgetting_risk(state, has_active_error=False, now=5 * DAY)
    flagged = scheduler.forgetting_risk(state, has_active_error=True, now=0.0)
    assert fresh < late and fresh < flagged


REFERENCE = """
import json, sys
from deeptutor.learning.mastery import compute_mastery
from deeptutor.learning.models import KnowledgeType, LearningEvidence
from deeptutor.learning.scheduler import SpacedRepetitionScheduler
cases = json.load(sys.stdin)
out = {"mastery": [compute_mastery(h) for h in cases["mastery"]], "schedules": []}
s = SpacedRepetitionScheduler()
for kind, events in cases["schedules"]:
    kt = KnowledgeType(kind)
    st = s.get_initial_state(kt, now=events[0][0])
    rows = []
    for at, q in events:
        ev = LearningEvidence(knowledge_point_id="k", assessment_type="review",
                              result="correct" if q >= 0.5 else "incorrect", quality=q, timestamp=at)
        s.schedule_review(st, kt, ev, now=at)
        rows.append([st.stability, st.difficulty, st.next_review_at, st.lapse_count, st.review_count])
    out["schedules"].append(rows)
json.dump(out, sys.stdout)
"""

CASES = {
    "mastery": [[1], [1, 0], [0, 1, 1], [1, 1, 1, 1, 0], [0.5, 1, 1, 0.5, 1, 1, 1]],
    "schedules": [
        ["memory", [[0.0, 1.0], [3 * DAY, 1.0], [10 * DAY, 0.0], [12 * DAY, 1.0], [40 * DAY, 0.7]]],
        ["concept", [[0.0, 1.0], [60.0, 1.0], [5 * DAY, 0.3], [9 * DAY, 1.0]]],
        ["procedure", [[0.0, 0.0], [DAY, 0.0], [2 * DAY, 1.0], [9 * DAY, 1.0], [30 * DAY, 1.0]]],
        ["design", [[0.0, 1.0], [15 * DAY, 1.0], [50 * DAY, 0.4], [51 * DAY, 0.9]]],
    ],
}


@pytest.mark.skipif(
    not os.environ.get("DEEPTUTOR_PYTHON"),
    reason="set DEEPTUTOR_PYTHON to a Python that has the deeptutor package",
)
def test_numeric_parity_with_upstream_deeptutor():
    import policy

    proc = subprocess.run(
        [os.environ["DEEPTUTOR_PYTHON"], "-c", REFERENCE],
        input=json.dumps(CASES),
        capture_output=True,
        text=True,
        cwd=Path(os.environ.get("TMPDIR", "/tmp")),
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    ref = json.loads(proc.stdout)
    assert [policy.compute_mastery(h) for h in CASES["mastery"]] == pytest.approx(ref["mastery"])
    for (kind, events), expected in zip(CASES["schedules"], ref["schedules"]):
        state = scheduler.initial_state(kind, now=events[0][0])
        for (at, quality), row in zip(events, expected):
            scheduler.schedule_review(state, kind, quality=quality, now=at)
            got = [
                state["stability"],
                state["difficulty"],
                state["next_review_at"],
                state["lapse_count"],
                state["review_count"],
            ]
            assert got == pytest.approx(row), (kind, at)
