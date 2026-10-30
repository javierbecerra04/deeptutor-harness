"""dtutor: the deterministic state engine behind the DeepTutor harness.

Skills run the conversation; this CLI owns everything that must not depend on the
model's impression: mastery gates, grading of closed questions, review scheduling,
question validation and memory rules. Every command prints one JSON object. A refused
command prints {"ok": false, "error": code, ...} and exits 2, so the model can read the
reason and act on it.
"""
import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

import store
from store import Refusal

DIFFICULTIES = ("easy", "medium", "hard")
QUESTION_TYPES = ("choice", "true_false", "fill_in_blank", "short_answer", "written", "coding")
ERROR_TYPES = ("structural", "deviation", "application", "metacognitive")
PROFILE_FIELDS = (
    "prior_knowledge",
    "finish_line",
    "time",
    "teaching_style",
    "teaching_strategy",
    "language",
)
OPTION_LETTER = re.compile(r"\b(?:option|choice|answer)\s+[A-D]\b|\b[A-D]\s+is\s+(?:right|correct|wrong)\b")
LETTERS = "ABCD"


def _read_file(path):
    try:
        return Path(path).expanduser().read_text(encoding="utf-8")
    except OSError as exc:
        raise Refusal("file_not_found", f"Cannot read {path}: {exc}")


def _read_json(args):
    if args.json is not None:
        raw = args.json
    elif args.json_file:
        raw = _read_file(args.json_file)
    else:
        raw = sys.stdin.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Refusal("invalid_json", f"That is not valid JSON: {exc}")


def _read_text(args):
    if args.body is not None:
        # Claude Code's permission check denies a quoted newline followed by "#".
        return re.sub(r"(?m)^(\s*)\\#", r"\1#", args.body)
    if getattr(args, "file", None):
        return _read_file(args.file)
    return sys.stdin.read()


def _require_mode(path, *modes):
    if path["mode"] not in modes:
        raise Refusal(
            "mode_required",
            f"This needs {modes[0]} mode. Run `dtutor mode {modes[0]}`, and tell the learner you switched.",
            needs_mode=modes[0],
            mode=path["mode"],
        )


# ---------------------------------------------------------------- topics


def cmd_topic_new(args):
    base = store.slugify(args.name)
    slug, n = base, 1
    while store.topic_file(slug).exists():
        n += 1
        slug = f"{base}-{n}"
    store.save_path(store.new_path(slug, args.name, args.goal or ""))
    store.save_state({**store.state(), "active": slug})
    return {"slug": slug, "name": args.name, "mode": "outline"}


def cmd_topic_list(args):
    import policy

    rows = []
    for slug in store.list_topics():
        path = store.read_json(store.topic_file(slug))
        summary = policy.map_summary(path, store.now())
        rows.append(
            {
                "slug": slug,
                "name": path["name"],
                "goal": path["goal"],
                "mode": path["mode"],
                "mastered": summary["mastered"],
                "total": summary["total"],
                "due": summary["due"],
            }
        )
    return {"active": store.state().get("active"), "topics": rows}


def cmd_topic_use(args):
    slug = store.resolve_topic(args.slug)
    store.save_state({**store.state(), "active": slug})
    return {"active": slug}


def cmd_topic_leave(args):
    store.save_state({**store.state(), "active": None})
    return {"active": None}


def cmd_topic_materials(args):
    import sources

    path = store.load_path(args.topic)
    for source_id in args.ids:
        sources.get(source_id)
        if source_id not in path["materials"]:
            path["materials"].append(source_id)
    store.save_path(path)
    return {"materials": path["materials"]}


def cmd_mode(args):
    path = store.load_path(args.topic)
    if args.mode != "outline" and not path["modules"]:
        raise Refusal("outline_required", "Design the outline first, in outline mode.")
    path["mode"] = args.mode
    store.save_path(path)
    return {"mode": args.mode}


def cmd_status(args):
    import policy
    import sources

    path = store.load_path(args.topic)
    now = store.now()
    step = policy.next_step(path, now)
    manifest = {row["id"]: row for row in sources.manifest()}
    out = {
        "topic": path["slug"],
        "name": path["name"],
        "goal": path["goal"],
        "mode": path["mode"],
        "intake_needed": not path["profile"] and not path["profile_declined"],
        "profile": path["profile"],
        "next": step,
        "due_count": len(policy.due_reviews(path, now)),
        "active_errors": policy.active_errors(path),
        "handoff": path["handoff"],
        "materials": [
            {k: manifest[m].get(k) for k in ("id", "title", "status", "unit", "unit_count", "reason")}
            for m in path["materials"]
            if m in manifest
        ],
    }
    if step.get("kp_id"):
        out["teaching_observations"] = path["observations"].get(step["kp_id"], [])
    if args.full:
        out["map"] = policy.map_summary(path, now)
    return out


def cmd_profile_set(args):
    path = store.load_path(args.topic)
    try:
        fields = json.loads(args.json)
    except json.JSONDecodeError as exc:
        raise Refusal("invalid_json", str(exc))
    unknown = [k for k in fields if k not in PROFILE_FIELDS]
    if unknown:
        raise Refusal("unknown_profile_field", f"Allowed fields: {PROFILE_FIELDS}.", fields=unknown)
    strategy = fields.get("teaching_strategy")
    if strategy not in (None, "probe_first", "teach_first"):
        raise Refusal("invalid_teaching_strategy", "Use probe_first or teach_first.")
    path["profile"].update(fields)
    store.save_path(path)
    return {"profile": path["profile"]}


def cmd_profile_decline(args):
    path = store.load_path(args.topic)
    path["profile_declined"] = True
    store.save_path(path)
    return {"profile_declined": True}


# --------------------------------------------------------------- outline


def _validate_outline(payload):
    modules = payload.get("modules") if isinstance(payload, dict) else None
    if not modules:
        raise Refusal("modules_required", "An outline needs at least one module.")
    import policy

    seen = set()
    for m_index, module in enumerate(modules, start=1):
        if not str(module.get("name", "")).strip():
            raise Refusal("module_name_required", f"Module {m_index} has no name.")
        if not str(module.get("objective", "")).strip():
            raise Refusal(
                "module_objective_required",
                f"Module {module['name']!r} needs an objective: what the learner can do once it clears.",
            )
        module["id"] = module.get("id") or f"m{m_index}"
        if not module.get("knowledge_points"):
            raise Refusal("knowledge_points_required", f"Module {module['name']!r} has no knowledge points.")
        for kp in module["knowledge_points"]:
            if not str(kp.get("name", "")).strip():
                raise Refusal("knowledge_point_name_required", f"A point in {module['name']!r} has no name.")
            if kp.get("type") not in policy.KNOWLEDGE_TYPES:
                raise Refusal(
                    "invalid_knowledge_type",
                    f"{kp['name']!r} must be one of {policy.KNOWLEDGE_TYPES}.",
                )
            kp["id"] = kp.get("id") or store.slugify(kp["name"])
            base, n = kp["id"], 1
            while kp["id"] in seen:
                n += 1
                kp["id"] = f"{base}-{n}"
            seen.add(kp["id"])
    return modules


def _outline_warnings(modules):
    warnings = []
    if not 3 <= len(modules) <= 8:
        warnings.append(f"Outlines usually have 3-8 modules; this one has {len(modules)}.")
    for module in modules:
        if not 2 <= len(module["knowledge_points"]) <= 7:
            warnings.append(f"Module {module['name']!r} usually needs 2-7 knowledge points.")
    return warnings


def _forget_progress(path, kp_id):
    path["attempts"] = [a for a in path["attempts"] if a["kp"] != kp_id]
    path["errors"] = [e for e in path["errors"] if e["kp"] != kp_id]
    for key in ("qualitative", "repetition", "overrides", "explained", "observations"):
        path[key].pop(kp_id, None)
    path["qualitative_log"] = [q for q in path["qualitative_log"] if q["kp"] != kp_id]
    path["deferred"] = [d for d in path["deferred"] if d != kp_id]
    if path.get("pending") and path["pending"]["kp"] == kp_id:
        path["pending"] = None


def cmd_outline_set(args):
    import policy

    path = store.load_path(args.topic)
    _require_mode(path, "outline")
    modules = _validate_outline(_read_json(args))

    used = {m for module in modules for m in module.get("materials", [])}
    missing = [m for m in path["materials"] if m not in used]
    if missing:
        raise Refusal(
            "materials_unaccounted",
            "Every material must belong to at least one module. Group them when there are many.",
            missing=missing,
        )

    old = {kp["id"]: kp for _, kp in policy.iter_kps(path)}
    new = {kp["id"]: kp for module in modules for kp in module["knowledge_points"]}
    removed = [k for k in old if k not in new]
    rewritten = [k for k in old if k in new and new[k]["name"] != old[k]["name"]]
    if not args.force_drop_mastered:
        for kp_id in removed:
            if policy.is_mastered(path, old[kp_id]):
                raise Refusal(
                    "mastered_objective_removed",
                    f"{old[kp_id]['name']!r} is mastered. Add new points instead of erasing earned work.",
                    kp=kp_id,
                )
        for kp_id in rewritten:
            if policy.is_mastered(path, old[kp_id]):
                raise Refusal(
                    "mastered_objective_rewritten",
                    f"{old[kp_id]['name']!r} is mastered. Add a new point instead of rewriting it.",
                    kp=kp_id,
                )
    reset = [k for k in rewritten if policy.objective_status(path, old[k]) != "new"]
    diff = {
        "added": [k for k in new if k not in old],
        "removed": removed,
        "renamed": rewritten,
        "reset": reset,
    }
    warnings = _outline_warnings(modules)
    if args.dry_run:
        return {"dry_run": True, "diff": diff, "warnings": warnings}
    for kp_id in removed + rewritten:
        _forget_progress(path, kp_id)
    path["modules"] = modules
    store.save_path(path)
    return {"dry_run": False, "diff": diff, "warnings": warnings, "next": policy.next_step(path, store.now())}


# --------------------------------------------------------------- questions


def _validate_question(q):
    qtype = q.get("type")
    if qtype not in QUESTION_TYPES:
        raise Refusal("invalid_question_type", f"Use one of {QUESTION_TYPES}.")
    question = str(q.get("question", "")).strip()
    if not question:
        raise Refusal("question_required", "The question has no text.")
    if not str(q.get("explanation", "")).strip():
        raise Refusal(
            "explanation_required",
            "Always pass an explanation. It is the only one the learner has when reviewing the mistake later.",
        )
    if q.get("difficulty") not in DIFFICULTIES:
        raise Refusal("invalid_difficulty", f"Use one of {DIFFICULTIES}.")
    expected = str(q.get("expected", "")).strip()
    if qtype == "choice":
        options = q.get("options") or []
        if len(options) != 4 or not all(str(o.get("body", "")).strip() for o in options):
            raise Refusal("four_options_required", "A choice question needs exactly four options with text.")
        if len({str(o["body"]).strip().lower() for o in options}) != 4:
            raise Refusal("duplicate_options", "Two options say the same thing.")
        if expected not in [o.get("label") for o in options]:
            raise Refusal("expected_not_in_options", "expected must be the label of one option.")
        for option in options:
            body = str(option["body"])
            if "recommended" in body.lower():
                raise Refusal("recommended_marker", "Never hint at the answer. Remove the marker.")
            if len(body) >= 8 and body.lower() in question.lower():
                raise Refusal("options_in_stem", "The question must hold the ask alone. Do not list options in it.")
        if OPTION_LETTER.search(q["explanation"]) or OPTION_LETTER.search(question):
            raise Refusal(
                "option_letter_in_explanation",
                "Options are shuffled, so never refer to a letter. Reason about the content.",
            )
    elif not expected:
        raise Refusal("expected_required", "Pass the expected answer.")
    if qtype == "fill_in_blank" and question.count("____") != 1:
        raise Refusal("one_blank_required", "Mark the gap with exactly one ____ in the question.")
    if qtype == "true_false" and expected not in ("true", "false"):
        raise Refusal("true_false_expected", 'expected must be "true" or "false".')


def _shuffle(q):
    """Shuffle and relabel, so a label never carries the answer's position."""
    seed = os.environ.get("DTUTOR_SEED")
    rng = random.Random(int(seed)) if seed else random.Random()
    options = list(q["options"])
    rng.shuffle(options)
    relabelled, expected = [], None
    for letter, option in zip(LETTERS, options):
        relabelled.append({"label": letter, "body": str(option["body"]).strip()})
        if option["label"] == q["expected"]:
            expected = letter
    return relabelled, expected


def cmd_pose(args):
    import policy

    path = store.load_path(args.topic)
    _require_mode(path, "study", "review")
    q = _read_json(args)
    module, kp = policy.find_kp(path, q.get("kp"))
    if kp is None:
        raise Refusal("unknown_objective", "That objective is not in the outline. Never invent one.", kp=q.get("kp"))
    if path["mode"] == "review" and not policy.is_mastered(path, kp):
        raise Refusal("review_requires_mastered", "Review only tests what is already mastered. Switch to study mode.")
    if kp["type"] in policy.QUALITATIVE_TYPES:
        raise Refusal(
            "qualitative_gate",
            "This objective has a qualitative gate.",
            hint="Ask for an explanation in the learner's own words, then record it with `dtutor assess`.",
        )
    if path.get("pending"):
        raise Refusal(
            "question_pending",
            "A question is still open. Re-present it, grade it, or `dtutor skip` if the learner asked to drop it.",
            pending=policy.public_pending(path["pending"]),
        )
    _validate_question(q)
    question_id = f"q{path['next_question']}"
    path["next_question"] += 1
    pending = {
        "id": question_id,
        "kp": kp["id"],
        "type": q["type"],
        "question": q["question"].strip(),
        "explanation": q["explanation"].strip(),
        "difficulty": q["difficulty"],
        "expected": str(q.get("expected", "")).strip(),
        "posed_at": store.now(),
    }
    warnings = []
    if q["type"] == "choice":
        correct = next(o for o in q["options"] if o["label"] == q["expected"])
        others = [len(str(o["body"])) for o in q["options"] if o is not correct]
        if len(str(correct["body"])) > 1.5 * (sum(others) / len(others)):
            warnings.append("The correct option is much longer than the rest, which gives it away.")
        pending["options"], pending["expected"] = _shuffle(q)
    path["pending"] = pending
    store.save_path(path)
    out = {"question_id": question_id, "question": pending["question"], "kp": kp["id"], "warnings": warnings}
    if "options" in pending:
        out["options"] = pending["options"]
        out["show_options_in_this_order"] = True
    return out


def cmd_pending(args):
    import policy

    path = store.load_path(args.topic)
    pending = path.get("pending")
    if args.reveal:
        return {"pending": pending}
    return {"pending": policy.public_pending(pending)}


def _replay(path, kp_id):
    """Rebuild one objective's schedule from its evidence, after a repair."""
    import policy
    import scheduler

    _, kp = policy.find_kp(path, kp_id)
    if kp is None:
        return
    events = [
        (a["at"], a.get("quality", a["credit"]), _result(a["credit"]), "quiz")
        for a in policy.live_attempts(path, kp_id)
    ] + [
        (q["at"], 1.0 if q["passed"] else 0.3, "correct" if q["passed"] else "incorrect", "qualitative")
        for q in path["qualitative_log"]
        if q["kp"] == kp_id
    ]
    events.sort(key=lambda e: e[0])
    path["repetition"].pop(kp_id, None)
    for at, quality, result, kind in events:
        state = path["repetition"].get(kp_id) or scheduler.initial_state(kp["type"], at)
        path["repetition"][kp_id] = scheduler.schedule_review(
            state, kp["type"], quality, at, result=result, assessment_type=kind
        )


def _result(credit):
    if credit >= 0.8:
        return "correct"
    return "partial" if credit > 0 else "incorrect"


def _record_evidence(path, kp, quality, credit, now, assessment_type="quiz"):
    import scheduler

    state = path["repetition"].get(kp["id"]) or scheduler.initial_state(kp["type"], now)
    path["repetition"][kp["id"]] = scheduler.schedule_review(
        state, kp["type"], quality, now, result=_result(credit), assessment_type=assessment_type
    )


def _judge(pending, args):
    """Return (raw_credit, early_reply). early_reply means nothing is recorded yet."""
    import grading

    qtype = pending["type"]
    if args.credit is not None:
        if qtype in grading.ENGINE_GRADED:
            raise Refusal("engine_graded_type", "The engine grades this type. Do not pass --credit.")
        if not args.rationale:
            raise Refusal("rationale_required", "Say why this credit is fair, with --rationale.")
        if not 0.0 <= args.credit <= 1.0:
            raise Refusal("credit_out_of_range", "Credit runs from 0 to 1.")
    if qtype == "choice":
        verdict = grading.grade_choice(pending["options"], pending["expected"], args.answer)
    elif qtype == "true_false":
        verdict = grading.grade_true_false(pending["expected"], args.answer)
    else:
        verdict = None
    if qtype in grading.ENGINE_GRADED:
        if verdict is None:
            return None, {
                "needs_clarification": True,
                "message": "The answer names no option. Ask the learner which one they mean. Nothing was recorded.",
            }
        return (1.0 if verdict else 0.0), None
    if not args.answer.strip():
        return 0.0, None
    if qtype == "fill_in_blank" and grading.fuzzy_match(pending["expected"], args.answer):
        return 1.0, None
    if args.credit is None:
        return None, {
            "needs_judgment": True,
            "expected": pending["expected"],
            "explanation": pending["explanation"],
            "message": "Judge the answer against this reference, then grade again with --credit and --rationale.",
        }
    return args.credit, None


def cmd_grade(args):
    import grading
    import policy

    path = store.load_path(args.topic)
    pending = path.get("pending")
    if not pending:
        raise Refusal("no_pending_question", "No question is open.")
    if args.error_type and args.error_type not in ERROR_TYPES:
        raise Refusal("invalid_error_type", f"Use one of {ERROR_TYPES}.")
    raw, reply = _judge(pending, args)
    if reply:
        return reply
    module, kp = policy.find_kp(path, pending["kp"])
    now = store.now()
    was_mastered = policy.is_assessed_mastered(path, kp)
    independent = args.hints == 0 and not args.assisted
    credit = raw if independent else min(raw, 0.5)
    quality = max(0.0, credit - min(0.25, args.hints * 0.08))
    path["attempts"].append(
        {
            "question_id": pending["id"],
            "kp": kp["id"],
            "credit": credit,
            "quality": quality,
            "independent": independent,
            "hints": args.hints,
            "voided": False,
            "learner_answer": args.answer,
            "rationale": args.rationale or "",
            "at": now,
            "type": pending["type"],
            "question": pending["question"],
            "options": pending.get("options"),
            "expected": pending["expected"],
            "explanation": pending["explanation"],
            "difficulty": pending["difficulty"],
        }
    )
    _record_evidence(path, kp, quality, credit, now)
    error_record = None
    if raw < 0.5:
        error_record = {
            "kp": kp["id"],
            "question_id": pending["id"],
            "error_type": args.error_type or grading.classify_error(args.answer),
            "remediation": args.remediation or "",
            "status": "active",
            "at": now,
        }
        path["errors"].append(error_record)
    elif raw >= 0.8:
        for record in path["errors"]:
            if record["kp"] == kp["id"] and record["status"] == "active":
                record["status"] = "resolved"
    path["pending"] = None
    store.save_path(path)
    store.append_jsonl(
        store.home() / "bank.jsonl",
        {
            "topic": path["slug"],
            "kp": kp["id"],
            "question_id": pending["id"],
            "type": pending["type"],
            "question": pending["question"],
            "options": pending.get("options"),
            "expected": pending["expected"],
            "learner_answer": args.answer,
            "credit": credit,
            "explanation": pending["explanation"],
            "difficulty": pending["difficulty"],
            "at": now,
        },
    )
    mastered = policy.is_assessed_mastered(path, kp)
    out = {
        "question_id": pending["id"],
        "kp": kp["id"],
        "correct": raw >= 0.8,
        "credit": credit,
        "independent": independent,
        "mastery": policy.display_mastery(path, kp),
        "threshold": policy.threshold_of(kp),
        "mastered": mastered,
        "mastered_now": mastered and not was_mastered,
        "explanation": pending["explanation"],
        "next": policy.next_step(path, now),
    }
    if pending["type"] == "choice":
        out["correct_option"] = pending["expected"]
    if error_record:
        out["error_record"] = error_record
    return out


def cmd_assess(args):
    import policy

    path = store.load_path(args.topic)
    _require_mode(path, "study", "review")
    module, kp = policy.find_kp(path, args.kp)
    if kp is None:
        raise Refusal("unknown_objective", "That objective is not in the outline.", kp=args.kp)
    if kp["type"] not in policy.QUALITATIVE_TYPES:
        raise Refusal("quantitative_gate", "This objective is gated by questions. Use `dtutor pose` and `dtutor grade`.")
    evidence = args.evidence.strip()
    if not evidence:
        raise Refusal("evidence_required", "Quote what the learner said.")
    if args.passed and len(evidence.split()) < 5 and len(evidence) < 20:
        raise Refusal(
            "evidence_too_short",
            "A pass needs the learner's own explanation, quoted. This is too short to show understanding.",
        )
    now = store.now()
    was_mastered = policy.is_assessed_mastered(path, kp)
    path["qualitative"][kp["id"]] = bool(args.passed)
    path["qualitative_log"].append(
        {"kp": kp["id"], "passed": bool(args.passed), "evidence": evidence, "gap": args.gap or "", "at": now}
    )
    _record_evidence(path, kp, 1.0 if args.passed else 0.3, 1.0 if args.passed else 0.0, now, "qualitative")
    store.save_path(path)
    mastered = policy.is_assessed_mastered(path, kp)
    return {
        "kp": kp["id"],
        "mastered": mastered,
        "mastered_now": mastered and not was_mastered,
        "gap": args.gap or "",
        "next": policy.next_step(path, now),
    }


def cmd_skip(args):
    import policy

    path = store.load_path(args.topic)
    if not path.get("pending"):
        raise Refusal("no_pending_question", "No question is open.")
    skipped = path["pending"]["id"]
    path["pending"] = None
    store.save_path(path)
    return {"skipped": skipped, "credit": 0, "next": policy.next_step(path, store.now())}


def cmd_repair(args):
    import grading
    import policy

    path = store.load_path(args.topic)
    attempts = [a for a in path["attempts"] if a.get("question_id") == args.question_id]
    if not attempts:
        raise Refusal("unknown_question", f"No graded attempt for {args.question_id}.")
    if not args.void and args.correct is None:
        raise Refusal("repair_action_required", "Pass --void or --correct ANSWER.")
    attempt = attempts[-1]
    if args.void:
        attempt["voided"] = True
    else:
        attempt["expected"] = args.correct
        if attempt["type"] == "choice":
            verdict = grading.grade_choice(attempt["options"], args.correct, attempt["learner_answer"])
        elif attempt["type"] == "true_false":
            verdict = grading.grade_true_false(args.correct, attempt["learner_answer"])
        else:
            verdict = grading.fuzzy_match(args.correct, attempt["learner_answer"]) or args.credit_full
        attempt["credit"] = attempt["quality"] = 1.0 if verdict else 0.0
    path["errors"] = [e for e in path["errors"] if e.get("question_id") != args.question_id]
    _replay(path, attempt["kp"])
    store.save_path(path)
    _, kp = policy.find_kp(path, attempt["kp"])
    return {
        "question_id": args.question_id,
        "voided": bool(args.void),
        "mastery": policy.display_mastery(path, kp) if kp else 0.0,
        "next": policy.next_step(path, store.now()),
    }


def _existing_kp(path, kp_id):
    import policy

    _, kp = policy.find_kp(path, kp_id)
    if kp is None:
        raise Refusal("unknown_objective", "That objective is not in the outline.", kp=kp_id)
    return kp


def cmd_defer(args):
    import policy

    path = store.load_path(args.topic)
    kp = _existing_kp(path, args.kp)
    if kp["id"] not in path["deferred"]:
        path["deferred"].append(kp["id"])
    store.save_path(path)
    return {"deferred": kp["id"], "mastered": False, "next": policy.next_step(path, store.now())}


def cmd_override(args):
    import policy

    path = store.load_path(args.topic)
    kp = _existing_kp(path, args.kp)
    if not args.quote.strip():
        raise Refusal("quote_required", "An override needs the learner's own words, quoted literally.")
    path["overrides"][kp["id"]] = {"quote": args.quote.strip(), "at": store.now()}
    store.save_path(path)
    return {"kp": kp["id"], "source": "learner", "next": policy.next_step(path, store.now())}


def cmd_explained(args):
    path = store.load_path(args.topic)
    kp = _existing_kp(path, args.kp)
    path["explained"][kp["id"]] = {"quote": args.quote, "coverage": "partial", "at": store.now()}
    store.save_path(path)
    return {"kp": kp["id"], "learning_stage": "partially_explained"}


def cmd_observe(args):
    path = store.load_path(args.topic)
    kp = _existing_kp(path, args.kp)
    if args.result in ("helped", "not_helped") and not (args.evidence or "").strip():
        raise Refusal("evidence_required", "helped or not_helped needs a literal quote from the learner.")
    path["observations"].setdefault(kp["id"], []).append(
        {"strategy": args.strategy, "result": args.result, "evidence": args.evidence or "", "at": store.now()}
    )
    store.save_path(path)
    return {"kp": kp["id"], "observations": path["observations"][kp["id"]]}


def cmd_handoff(args):
    path = store.load_path(args.topic)
    path["handoff"] = {"summary": args.summary, "next_focus": args.next_focus, "at": store.now()}
    store.save_path(path)
    return {"handoff": path["handoff"]}


def cmd_reviews(args):
    import policy

    now = store.now()
    slugs = store.list_topics() if args.all_topics else [store.resolve_topic(args.topic)]
    due = []
    for slug in slugs:
        path = store.read_json(store.topic_file(slug))
        for task in policy.due_reviews(path, now):
            due.append({**task, "topic": slug})
    due.sort(key=lambda t: -t["forgetting_risk"])
    return {"count": len(due), "due": due}


# ------------------------------------------------------------------ notes


def _notes_file():
    return store.home() / "notes" / "index.json"


def _note_index():
    return store.read_json(_notes_file(), [])


def _note_body(note_id):
    path = store.home() / "notes" / f"{note_id}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def cmd_note_add(args):
    body = _read_text(args)
    if not body.strip():
        raise Refusal("empty_body", "Pass the note's body with --body or --file.")
    index = _note_index()
    note_id = f"n{max((int(n['id'][1:]) for n in index), default=0) + 1}"
    row = {
        "id": note_id,
        "title": args.title,
        "kind": args.kind,
        "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()],
        "summary": args.summary or "",
        "topic": args.topic or store.state().get("active"),
        "favorite": False,
        "at": store.now(),
    }
    index.append(row)
    target = store.home() / "notes" / f"{note_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    store.write_json(_notes_file(), index)
    return {"id": note_id, "path": str(target)}


def cmd_note_list(args):
    rows = _note_index()
    if args.favorites:
        rows = [r for r in rows if r["favorite"]]
    return {"items": rows}


def cmd_note_show(args):
    for row in _note_index():
        if row["id"] == args.id:
            return {**row, "body": _note_body(args.id)}
    raise Refusal("unknown_note", f"No note {args.id}.")


def cmd_note_search(args):
    needle = args.query.lower()
    hits = []
    for row in _note_index():
        haystack = " ".join([row["title"], row["summary"], " ".join(row["tags"]), _note_body(row["id"])])
        if needle in haystack.lower():
            hits.append(row)
    return {"items": hits}


def cmd_note_fav(args):
    index = _note_index()
    for row in index:
        if row["id"] == args.id:
            row["favorite"] = not row["favorite"]
            store.write_json(_notes_file(), index)
            return {"id": args.id, "favorite": row["favorite"]}
    raise Refusal("unknown_note", f"No note {args.id}.")


def cmd_bank_add(args):
    import grading

    q = _read_json(args)
    qtype = q.get("type")
    answer = str(q.get("learner_answer", ""))
    if qtype == "choice":
        verdict = grading.grade_choice(q.get("options") or [], q.get("expected"), answer)
        if verdict is None:
            raise Refusal("answer_names_no_option", "Ask the learner which option they mean.")
        q["credit"] = 1.0 if verdict else 0.0
    elif qtype == "true_false":
        verdict = grading.grade_true_false(q.get("expected"), answer)
        if verdict is None:
            raise Refusal("answer_names_no_option", "Ask the learner for true or false.")
        q["credit"] = 1.0 if verdict else 0.0
    elif q.get("credit") is None:
        raise Refusal("credit_required", "Judge this answer and pass credit from 0 to 1.")
    q.setdefault("topic", store.state().get("active"))
    q["at"] = store.now()
    store.append_jsonl(store.home() / "bank.jsonl", q)
    return {"credit": q["credit"], "correct": q["credit"] >= 0.8}


def cmd_bank_list(args):
    rows = store.read_jsonl(store.home() / "bank.jsonl")
    if args.wrong:
        rows = [r for r in rows if r.get("credit", 0) < 0.8]
    if args.topic:
        rows = [r for r in rows if r.get("topic") == args.topic]
    return {"items": rows[-args.limit :]}


def cmd_save(args):
    kind = store.slugify(args.kind)
    stem, dot, ext = args.name.rpartition(".")
    name = f"{store.slugify(stem)}.{store.slugify(ext)}" if dot else store.slugify(args.name)
    body = _read_text(args)
    if not body.strip():
        raise Refusal("empty_body", "Pass the document with --body or --file.")
    target = store.home() / "outputs" / kind / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a" if args.append else "w", encoding="utf-8") as handle:
        handle.write(body)
    return {"path": str(target)}


# ---------------------------------------------------------------- sources


def cmd_source_add(args):
    import sources

    if args.path:
        return sources.add(path=args.path, title=args.title, origin=args.origin)
    return sources.add(title=args.title, origin=args.origin, stdin_text=_read_text(args))


def cmd_source_list(args):
    import sources

    return {"items": sources.manifest()}


def cmd_source_outline(args):
    import sources

    row, headings = sources.outline(args.id)
    return {"id": row["id"], "title": row["title"], "unit_count": row["unit_count"], "headings": headings}


def cmd_source_search(args):
    import sources

    return {"items": sources.search(args.query, args.id, args.limit)}


def cmd_source_read(args):
    import sources

    return sources.read(args.id, args.pages)


# ----------------------------------------------------------------- memory


def cmd_memory_show(args):
    import memory

    return {"markdown": memory.render(), "entries": len(memory.entries())}


def cmd_memory_apply(args):
    import memory

    ops = _read_json(args).get("ops", [])
    ids = memory.apply_ops(ops)
    return {"applied": len(ops), "ids": ids}


def cmd_session_pending(args):
    rows = store.read_jsonl(store.home() / "sessions.jsonl")
    return {"items": [r for r in rows if not r.get("consolidated")]}


def cmd_session_done(args):
    rows = store.read_jsonl(store.home() / "sessions.jsonl")
    for row in rows:
        if args.all or row.get("session_id") in args.ids:
            row["consolidated"] = True
    if rows:
        store.write_jsonl(store.home() / "sessions.jsonl", rows)
    return {"pending": sum(not r.get("consolidated") for r in rows)}


# ----------------------------------------------------------------- parser


def build_parser():
    ap = argparse.ArgumentParser(prog="dtutor", description=__doc__.split("\n")[0])
    ap.add_argument("--version", action="version", version="dtutor 0.1.0")
    sub = ap.add_subparsers(dest="command", required=True)
    topic_opt = argparse.ArgumentParser(add_help=False)
    topic_opt.add_argument("--topic", help="Topic slug. Default: the active topic.")
    # Claude Code's Bash(dtutor:*) rule denies a heredoc, so documents travel as arguments.
    json_input = argparse.ArgumentParser(add_help=False)
    group = json_input.add_mutually_exclusive_group()
    group.add_argument("--json", help="The JSON itself, in single quotes. Write an apostrophe as '\\''.")
    group.add_argument("--json-file", help="Read the JSON from this file.")
    text_input = argparse.ArgumentParser(add_help=False)
    group = text_input.add_mutually_exclusive_group()
    group.add_argument("--body", help="The text itself, in single quotes. Write an apostrophe as '\\'' and a line-start # as \\#.")
    group.add_argument("--file", help="Read the text from this file.")

    def add(parent, name, func, *parents_, help=None):  # noqa: A002
        parser = parent.add_parser(name, parents=list(parents_), help=help)
        parser.set_defaults(func=func)
        return parser

    topic = sub.add_parser("topic", help="Create, list and switch learning topics").add_subparsers(dest="sub", required=True)
    p = add(topic, "new", cmd_topic_new)
    p.add_argument("name")
    p.add_argument("--goal")
    add(topic, "list", cmd_topic_list)
    add(topic, "use", cmd_topic_use).add_argument("slug")
    add(topic, "leave", cmd_topic_leave)
    p = add(topic, "materials", cmd_topic_materials, topic_opt)
    p.add_argument("ids", nargs="+")

    p = add(sub, "mode", cmd_mode, topic_opt, help="Switch between outline, study and review")
    p.add_argument("mode", choices=("outline", "study", "review"))
    add(sub, "status", cmd_status, topic_opt, help="What to do now, from the engine").add_argument("--full", action="store_true")

    profile = sub.add_parser("profile", help="Learner profile for a topic").add_subparsers(dest="sub", required=True)
    add(profile, "set", cmd_profile_set, topic_opt).add_argument("--json", required=True)
    add(profile, "decline", cmd_profile_decline, topic_opt)

    outline = sub.add_parser("outline", help="Set the topic outline").add_subparsers(dest="sub", required=True)
    p = add(outline, "set", cmd_outline_set, topic_opt, json_input)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force-drop-mastered", action="store_true")

    add(sub, "pose", cmd_pose, topic_opt, json_input, help="Register a question")
    add(sub, "pending", cmd_pending, topic_opt, help="Show the open question").add_argument("--reveal", action="store_true")
    p = add(sub, "grade", cmd_grade, topic_opt, help="Grade the open question")
    p.add_argument("--answer", required=True)
    p.add_argument("--credit", type=float)
    p.add_argument("--rationale")
    p.add_argument("--hints", type=int, default=0)
    p.add_argument("--assisted", action="store_true")
    p.add_argument("--error-type")
    p.add_argument("--remediation")
    p = add(sub, "assess", cmd_assess, topic_opt, help="Record a concept or design explanation")
    p.add_argument("--kp", required=True)
    verdict = p.add_mutually_exclusive_group(required=True)
    verdict.add_argument("--passed", action="store_true")
    verdict.add_argument("--failed", action="store_true")
    p.add_argument("--evidence", required=True)
    p.add_argument("--gap")
    add(sub, "skip", cmd_skip, topic_opt, help="Drop the open question, with no credit")
    p = add(sub, "repair", cmd_repair, topic_opt, help="Void or correct a bad question")
    p.add_argument("--question-id", required=True)
    p.add_argument("--void", action="store_true")
    p.add_argument("--correct")
    p.add_argument("--credit-full", action="store_true")
    add(sub, "defer", cmd_defer, topic_opt, help="Set an objective aside, not mastered").add_argument("--kp", required=True)
    p = add(sub, "override", cmd_override, topic_opt, help="Learner claims mastery, with provenance")
    p.add_argument("--kp", required=True)
    p.add_argument("--quote", required=True)
    p = add(sub, "explained", cmd_explained, topic_opt, help="Record a delivered explanation")
    p.add_argument("--kp", required=True)
    p.add_argument("--quote", required=True)
    p = add(sub, "observe", cmd_observe, topic_opt, help="Record whether a teaching strategy helped")
    p.add_argument("--kp", required=True)
    p.add_argument("--strategy", required=True)
    p.add_argument("--result", choices=("helped", "not_helped", "unknown"), default="unknown")
    p.add_argument("--evidence")
    p = add(sub, "handoff", cmd_handoff, topic_opt, help="Leave a note for the next session")
    p.add_argument("--summary", required=True)
    p.add_argument("--next-focus", required=True)
    add(sub, "reviews", cmd_reviews, topic_opt, help="Due spaced-repetition reviews").add_argument("--all-topics", action="store_true")

    note = sub.add_parser("note", help="Notebook").add_subparsers(dest="sub", required=True)
    p = add(note, "add", cmd_note_add, topic_opt, text_input)
    p.add_argument("--title", required=True)
    p.add_argument("--kind", default="chat")
    p.add_argument("--tags")
    p.add_argument("--summary")
    add(note, "list", cmd_note_list).add_argument("--favorites", action="store_true")
    add(note, "show", cmd_note_show).add_argument("id")
    add(note, "search", cmd_note_search).add_argument("query")
    add(note, "fav", cmd_note_fav).add_argument("id")

    bank = sub.add_parser("bank", help="Question bank").add_subparsers(dest="sub", required=True)
    add(bank, "add", cmd_bank_add, json_input)
    p = add(bank, "list", cmd_bank_list, topic_opt)
    p.add_argument("--wrong", action="store_true")
    p.add_argument("--limit", type=int, default=50)

    p = add(sub, "save", cmd_save, text_input, help="Save generated output under the home")
    p.add_argument("--kind", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--append", action="store_true", help="Add to the end of an existing file.")

    source = sub.add_parser("source", help="Documents to read and cite").add_subparsers(dest="sub", required=True)
    p = add(source, "add", cmd_source_add)
    p.add_argument("path", nargs="?")
    p.add_argument("--body", help="The text itself, in single quotes, for a fetched page. Write an apostrophe as '\\'' and a line-start # as \\#.")
    p.add_argument("--title")
    p.add_argument("--origin")
    add(source, "list", cmd_source_list)
    add(source, "outline", cmd_source_outline).add_argument("id")
    p = add(source, "search", cmd_source_search)
    p.add_argument("query")
    p.add_argument("--id")
    p.add_argument("--limit", type=int, default=10)
    p = add(source, "read", cmd_source_read)
    p.add_argument("id")
    p.add_argument("--pages", required=True)

    mem = sub.add_parser("memory", help="Learner memory").add_subparsers(dest="sub", required=True)
    add(mem, "show", cmd_memory_show)
    add(mem, "apply", cmd_memory_apply, json_input)

    session = sub.add_parser("session", help="Study sessions waiting for consolidation").add_subparsers(dest="sub", required=True)
    add(session, "pending", cmd_session_pending)
    p = add(session, "done", cmd_session_done)
    p.add_argument("ids", nargs="*")
    p.add_argument("--all", action="store_true")
    return ap


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["hook"] and len(argv) == 2:
        import hooks

        return hooks.run(argv[1])
    args = build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except Refusal as refusal:
        out = {"ok": False, "error": refusal.code}
        if refusal.message:
            out["message"] = refusal.message
        out.update(refusal.extra)
        print(json.dumps(out, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0
