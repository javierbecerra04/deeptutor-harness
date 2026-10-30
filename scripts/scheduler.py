"""Spaced-repetition scheduling: exponential forgetting with per-type priors.

Ported from DeepTutor's deeptutor/learning/scheduler.py (Apache-2.0). The maths
is unchanged, and tests/test_scheduler.py checks parity against upstream. State
is a plain dict so it can be stored as JSON.
"""
import math

INTERVALS = {
    "memory": [0, 1, 3, 7, 14, 30, 60],
    "concept": [3, 7, 14, 30],
    "procedure": [3, 7, 14],
    "design": [14, 28],
}
TYPE_PRIORITY = {"memory": 2, "concept": 3, "procedure": 4, "design": 5}
TYPE_DIFFICULTY = {"memory": 0.3, "concept": 0.4, "procedure": 0.5, "design": 0.6}

DEFAULT_RETENTION = 0.9
MIN_STABILITY = 0.5
FAIL_QUALITY = 0.5
SAME_SESSION_DAYS = 0.25
EPS = 1e-6
DAY = 86400.0


def _stability_from_interval(interval_days, retention):
    retention = min(max(retention, EPS), 1.0 - EPS)
    if interval_days <= 0:
        return MIN_STABILITY
    return max(MIN_STABILITY, interval_days / -math.log(retention))


def _interval_from_stability(stability, retention):
    retention = min(max(retention, EPS), 1.0 - EPS)
    return max(EPS, max(stability, EPS) * -math.log(retention))


def initial_state(kind, now):
    first = float(INTERVALS[kind][0])
    stability = _stability_from_interval(first, DEFAULT_RETENTION)
    interval = first if first == 0 else _interval_from_stability(stability, DEFAULT_RETENTION)
    return {
        "consecutive_correct": 0,
        "consecutive_wrong": 0,
        "next_review_at": now + interval * DAY,
        "difficulty": TYPE_DIFFICULTY[kind],
        "stability": stability,
        "retrievability": 1.0,
        "desired_retention": DEFAULT_RETENTION,
        "review_count": 0,
        "lapse_count": 0,
        "last_review_at": None,
        "last_scheduled_at": now,
        "scheduled_after_failure": False,
    }


def retrievability(state, now):
    stability = max(state["stability"], EPS)
    last = state.get("last_review_at")
    anchor = last if last is not None else state["next_review_at"]
    elapsed = max(0.0, (now - anchor) / DAY)
    return float(min(1.0, max(0.0, math.exp(-elapsed / stability))))


def _scheduled_interval(state, kind):
    if state["review_count"] == 0 and INTERVALS[kind][0] == 0:
        return 0.0
    interval = _interval_from_stability(state["stability"], state["desired_retention"])
    if state["scheduled_after_failure"]:
        interval = min(interval, max(interval * 0.5, MIN_STABILITY * 0.2))
    return interval


def schedule_review(state, kind, quality, now, result=None, assessment_type="review"):
    last = state["last_review_at"]
    moment = max(now, last) if last is not None else now
    previous_stability = max(state["stability"], EPS)
    previous_recall = retrievability(state, moment)
    elapsed = max(0.0, moment - last) / DAY if last is not None else 0.0
    same_session = min(
        SAME_SESSION_DAYS,
        _interval_from_stability(previous_stability, DEFAULT_RETENTION) * 0.5,
    )
    if last is not None and elapsed < same_session:
        if quality >= FAIL_QUALITY:
            # Repeated practice refreshes recall but must not multiply stability
            # or push back the original review deadline.
            state["review_count"] += 1
            state["last_review_at"] = moment
            state["retrievability"] = 1.0
            state["consecutive_wrong"] = 0
            return state
        if state["scheduled_after_failure"] and (
            result == "partial" or assessment_type == "qualitative"
        ):
            state["review_count"] += 1
            state["last_review_at"] = moment
            state["retrievability"] = max(quality, 0.2)
            return state
    spacing_ratio = min(elapsed / previous_stability, 4.0)

    outcome_error = (1.0 - quality) - state["difficulty"]
    surprise = previous_recall - quality
    state["difficulty"] = float(
        min(0.95, max(0.05, state["difficulty"] + 0.12 * outcome_error + 0.08 * surprise))
    )

    if quality < FAIL_QUALITY:
        state["consecutive_wrong"] += 1
        state["consecutive_correct"] = 0
        state["lapse_count"] += 1
        retention_factor = 0.55 - 0.25 * previous_recall
        difficulty_factor = 1.0 - 0.25 * state["difficulty"]
        state["stability"] = max(
            MIN_STABILITY * 0.1,
            previous_stability * retention_factor * difficulty_factor,
        )
        state["retrievability"] = max(quality, 0.2)
        if state["consecutive_wrong"] >= 2:
            state["consecutive_wrong"] = 0
    else:
        state["consecutive_wrong"] = 0
        state["consecutive_correct"] += 1
        retrieval_effort = 1.0 + (1.0 - previous_recall) * 1.5
        spacing_bonus = 1.0 + spacing_ratio * 0.15
        learnability = 1.35 - 0.6 * state["difficulty"]
        strength = max(0.0, (quality - FAIL_QUALITY) / (1.0 - FAIL_QUALITY))
        growth = 1.0 + strength * learnability * retrieval_effort * spacing_bonus
        if quality >= 0.8 and state["consecutive_correct"] >= 2:
            growth *= 1.15
        state["stability"] = max(MIN_STABILITY, previous_stability * growth)
        state["retrievability"] = 1.0
        if state["consecutive_correct"] >= 2:
            state["consecutive_correct"] = 0

    state["review_count"] += 1
    state["last_review_at"] = moment
    state["last_scheduled_at"] = moment
    state["scheduled_after_failure"] = quality < FAIL_QUALITY
    state["next_review_at"] = moment + _scheduled_interval(state, kind) * DAY
    return state


def forgetting_risk(state, has_active_error, now):
    risk = 1.0 - retrievability(state, now)
    if now > state["next_review_at"]:
        risk += min((now - state["next_review_at"]) / DAY / 7.0, 0.25)
    if has_active_error:
        risk += 0.2
    if state.get("lapse_count"):
        risk += min(0.1 * state["lapse_count"], 0.2)
    return float(min(1.0, max(0.0, risk)))


def review_reason(state, now):
    recall = retrievability(state, now)
    delta = now - state["next_review_at"]
    parts = ["due now" if delta < DAY else f"due {delta / DAY:.0f}d ago"]
    desired = state.get("desired_retention") or DEFAULT_RETENTION
    if recall + 1e-9 < desired:
        parts.append(f"retrievability {recall:.0%} below {desired:.0%} target")
    else:
        parts.append(f"retrievability {recall:.0%}")
    if state.get("lapse_count"):
        parts.append(f"{state['lapse_count']} lapse(s)")
    return "; ".join(parts) + "."
