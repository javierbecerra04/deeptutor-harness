"""Mastery policy: pure decisions over a topic's path. No I/O.

Ported from DeepTutor's deeptutor/learning/policy.py and mastery.py (Apache-2.0).
The gate is decided here, never by the model's impression: advancement is computed
from what is mastered, and next_step keeps returning the same objective until it
clears.
"""
import scheduler

RECENCY_WEIGHTS = (0.5, 0.7, 0.85, 0.95, 1.0)
CONFIDENCE_CAP = {1: 0.5, 2: 0.8}
QUANTITATIVE_GATE = 0.9
QUALITATIVE_TYPES = ("concept", "design")
KNOWLEDGE_TYPES = ("memory", "procedure", "concept", "design")


def compute_mastery(correctness):
    """Recency-weighted accuracy, capped so one or two answers cannot master a point."""
    if not correctness:
        return 0.0
    recent = correctness[-len(RECENCY_WEIGHTS) :]
    weights = RECENCY_WEIGHTS[-len(recent) :]
    score = sum(w * max(0.0, min(1.0, float(c))) for c, w in zip(recent, weights)) / sum(weights)
    return min(score, CONFIDENCE_CAP.get(len(recent), 1.0))


def iter_kps(path):
    for module in path["modules"]:
        for kp in module["knowledge_points"]:
            yield module, kp


def find_kp(path, kp_id):
    for module, kp in iter_kps(path):
        if kp["id"] == kp_id:
            return module, kp
    return None, None


def live_attempts(path, kp_id):
    return [a for a in path["attempts"] if a["kp"] == kp_id and not a.get("voided")]


def mastery_of(path, kp_id):
    return compute_mastery([a["credit"] for a in live_attempts(path, kp_id)])


def gate_kind(kp):
    return "qualitative" if kp["type"] in QUALITATIVE_TYPES else "quantitative"


def threshold_of(kp):
    return 1.0 if kp["type"] in QUALITATIVE_TYPES else QUANTITATIVE_GATE


def is_assessed_mastered(path, kp):
    if kp["type"] in QUALITATIVE_TYPES:
        return bool(path["qualitative"].get(kp["id"]))
    return mastery_of(path, kp["id"]) >= QUANTITATIVE_GATE


def mastery_source(path, kp):
    """'system' for a cleared gate, 'learner' for an explicit claim, '' otherwise."""
    if is_assessed_mastered(path, kp):
        return "system"
    if kp["id"] in path["overrides"]:
        return "learner"
    return ""


def is_mastered(path, kp):
    return bool(mastery_source(path, kp))


def display_mastery(path, kp):
    if kp["type"] in QUALITATIVE_TYPES and path["qualitative"].get(kp["id"]):
        return 1.0
    return round(mastery_of(path, kp["id"]), 4)


def objective_status(path, kp):
    if is_mastered(path, kp):
        return "mastered"
    seen = any(a["kp"] == kp["id"] for a in path["attempts"]) or kp["id"] in path["qualitative"]
    return "learning" if seen else "new"


def learning_stage(path, kp_id):
    attempts = live_attempts(path, kp_id)
    if path["qualitative"].get(kp_id):
        return "independently_demonstrated"
    if any(a.get("independent") and a["credit"] >= 0.8 for a in attempts):
        return "independently_demonstrated"
    if any(not a.get("independent") for a in attempts):
        return "practiced_with_help"
    if attempts or kp_id in path["qualitative"]:
        return "practiced_not_demonstrated"
    return "partially_explained" if path["explained"].get(kp_id) else "not_yet_covered"


def active_errors(path):
    return [e for e in path["errors"] if e.get("status") == "active"]


def due_reviews(path, now):
    error_kps = {e["kp"] for e in active_errors(path)}
    tasks = []
    for _, kp in iter_kps(path):
        state = path["repetition"].get(kp["id"])
        if not state or not is_mastered(path, kp) or state["next_review_at"] > now:
            continue
        has_error = kp["id"] in error_kps
        tasks.append(
            {
                "kp_id": kp["id"],
                "kp_name": kp["name"],
                "kp_type": kp["type"],
                "due_at": state["next_review_at"],
                "priority": 1 if has_error else scheduler.TYPE_PRIORITY[kp["type"]],
                "forgetting_risk": round(scheduler.forgetting_risk(state, has_error, now), 4),
                "reason": scheduler.review_reason(state, now),
            }
        )
    tasks.sort(key=lambda t: (-t["forgetting_risk"], t["due_at"], t["priority"]))
    return tasks


def public_pending(pending):
    """A pending question without its private answer contract."""
    if not pending:
        return None
    keep = ("id", "kp", "type", "question", "options", "difficulty", "posed_at")
    return {k: pending[k] for k in keep if k in pending}


def _step(path, action, module, kp, reason, **extra):
    return {
        "action": action,
        "module_id": module["id"],
        "module_name": module["name"],
        "module_objective": module.get("objective", ""),
        "kp_id": kp["id"],
        "kp_name": kp["name"],
        "kp_type": kp["type"],
        "status": objective_status(path, kp),
        "gate": gate_kind(kp),
        "mastery": display_mastery(path, kp),
        "threshold": threshold_of(kp),
        "learning_stage": learning_stage(path, kp["id"]),
        "reason": reason,
        **extra,
    }


def next_step(path, now):
    """Pending answer, then due review, then first unmastered objective, then done."""
    if not path["modules"]:
        return {"action": "design_outline", "reason": "This goal has no outline yet."}
    pending = path.get("pending")
    if pending:
        module, kp = find_kp(path, pending["kp"])
        if kp:
            return _step(
                path,
                "answer_pending",
                module,
                kp,
                "A posed question is waiting for the learner's answer.",
                pending=public_pending(pending),
            )
    deferred = set(path["deferred"])
    due = [t for t in due_reviews(path, now) if t["kp_id"] not in deferred]
    if due:
        module, kp = find_kp(path, due[0]["kp_id"])
        return _step(
            path, "review", module, kp, due[0]["reason"], forgetting_risk=due[0]["forgetting_risk"]
        )
    fallback = None
    for module, kp in iter_kps(path):
        if is_mastered(path, kp):
            continue
        status = objective_status(path, kp)
        if status == "new":
            action = "teach" if path["profile"].get("teaching_strategy") == "teach_first" else "probe"
            reason = (
                "Untouched objective: teach before assessing, as the learner asked."
                if action == "teach"
                else "Untouched objective: probe first so the learner can test out."
            )
        else:
            action = "assess" if gate_kind(kp) == "qualitative" else "practice"
            reason = "Objective is below its gate: keep working it until it clears."
        step = _step(path, action, module, kp, reason)
        if kp["id"] not in deferred:
            return step
        fallback = fallback or step
    return fallback or {"action": "complete", "reason": "All objectives are mastered and no reviews are due."}


def map_summary(path, now):
    modules = []
    for module in path["modules"]:
        rows = [
            {
                "id": kp["id"],
                "name": kp["name"],
                "type": kp["type"],
                "status": objective_status(path, kp),
                "source": mastery_source(path, kp),
                "mastery": display_mastery(path, kp),
                "learning_stage": learning_stage(path, kp["id"]),
                "deferred": kp["id"] in path["deferred"],
            }
            for kp in module["knowledge_points"]
        ]
        modules.append(
            {
                "id": module["id"],
                "name": module["name"],
                "objective": module.get("objective", ""),
                "materials": module.get("materials", []),
                "knowledge_points": rows,
            }
        )
    total = sum(len(m["knowledge_points"]) for m in modules)
    done = sum(r["status"] == "mastered" for m in modules for r in m["knowledge_points"])
    return {"mastered": done, "total": total, "due": len(due_reviews(path, now)), "modules": modules}
