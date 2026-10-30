"""Claude Code hook handlers. They must stay fast and quiet.

Hooks run in every session on the machine, so a session with no tutoring in it gets
no output, no model context and no new files.
"""
import json
import re
import sys

import policy
import store

NOTICE_COOLDOWN = 6 * 3600
# Study work only. Reading state or consolidating memory must not open a new session to consolidate.
STUDY_WORK = r"(?:topic (?:new|use)|mode|profile|outline|pose|grade|assess|skip|repair|defer|override|explained|observe|handoff|bank add)"
DTUTOR_COMMAND = re.compile(rf"(?:^|[;&|\n]\s*)(?:\S*/)?dtutor\s+{STUDY_WORK}\b")


def _input():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def _marker(session_id):
    return store.home() / "sessions" / f"{store.slugify(session_id)}.json"


def _emit(payload):
    print(json.dumps(payload, ensure_ascii=False))


def post_tool(data):
    """Remember that this session did tutoring work, for restore and consolidation."""
    command = (data.get("tool_input") or {}).get("command", "")
    session_id = data.get("session_id")
    if not session_id or not DTUTOR_COMMAND.search(command) or not store.home().is_dir():
        return
    store.write_json(
        _marker(session_id),
        {
            "session_id": session_id,
            "topic": store.state().get("active"),
            "transcript_path": data.get("transcript_path", ""),
            "cwd": data.get("cwd", ""),
            "at": store.now(),
        },
    )


def session_end(data):
    session_id = data.get("session_id")
    if not session_id or not store.home().is_dir():
        return
    marker = _marker(session_id)
    record = store.read_json(marker)
    if not record:
        return
    record.update(ended_at=store.now(), reason=data.get("reason", ""), consolidated=False)
    record["transcript_path"] = data.get("transcript_path") or record.get("transcript_path", "")
    log = store.home() / "sessions.jsonl"
    rows = [r for r in store.read_jsonl(log) if r.get("session_id") != session_id]
    store.write_jsonl(log, rows + [record])
    marker.unlink(missing_ok=True)


def _restore_context(record):
    slug = record.get("topic")
    if not slug or not store.topic_file(slug).is_file():
        return None
    path = store.read_json(store.topic_file(slug))
    now = store.now()
    step = policy.next_step(path, now)
    lines = [
        f"DeepTutor: this session was tutoring topic {slug} in {path['mode']} mode.",
        "If the learner is still studying, run /deeptutor:learn to reload the tutoring rules before you continue.",
        f"Engine next step: {step['action']}" + (f" on {step['kp_name']}." if step.get("kp_name") else "."),
    ]
    pending = policy.public_pending(path.get("pending"))
    if pending:
        lines.append(f"Open question {pending['id']} is waiting for an answer: {pending['question']}")
        for option in pending.get("options") or []:
            lines.append(f"  {option['label']}. {option['body']}")
    return "\n".join(lines)


def _due_total(now):
    total = 0
    for slug in store.list_topics():
        path = store.read_json(store.topic_file(slug))
        if path:
            total += len(policy.due_reviews(path, now))
    return total


def _waiting_sessions():
    return sum(not r.get("consolidated") for r in store.read_jsonl(store.home() / "sessions.jsonl"))


def session_start(data):
    if not store.home().is_dir():
        return
    source = data.get("source")
    if source in ("compact", "resume", "fork"):
        record = store.read_json(_marker(data.get("session_id", "")))
        context = _restore_context(record) if record else None
        if context:
            _emit(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": context,
                    }
                }
            )
        return
    if source != "startup":
        return
    now = store.now()
    state = store.state()
    if now - state.get("last_notice_at", 0) < NOTICE_COOLDOWN:
        return
    parts = []
    due = _due_total(now)
    if due:
        parts.append(f"{due} review{'s' if due != 1 else ''} due (/deeptutor:review)")
    waiting = _waiting_sessions()
    if waiting:
        parts.append(f"{waiting} study session{'s' if waiting != 1 else ''} to consolidate (/deeptutor:memory)")
    if parts:
        store.save_state({**state, "last_notice_at": now})
        _emit({"systemMessage": "DeepTutor: " + "; ".join(parts) + "."})


HANDLERS = {"session-start": session_start, "post-tool": post_tool, "session-end": session_end}


def run(name):
    """A hook must never break the session, whatever goes wrong in it."""
    try:
        HANDLERS[name](_input())
    except Exception as exc:  # noqa: BLE001
        print(f"dtutor hook {name}: {exc}", file=sys.stderr)
    return 0
