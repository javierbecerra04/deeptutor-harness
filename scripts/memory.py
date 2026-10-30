"""Learner memory. Same discipline as DeepTutor's consolidator (Apache-2.0).

Every entry cites evidence, stays short, and avoids absolutist claims about the
learner. The rules live here so a model cannot talk its way past them. A batch is
validated whole before anything is written.
"""
import re
import uuid

import store
from store import Refusal

SLOTS = {
    "profile": ["Identity", "Learning style", "Knowledge level"],
    "scope": ["Familiar", "Practicing", "Unsure"],
    "recent": ["This week", "Earlier"],
}
MAX_CHARS = 240
BANNED = re.compile(
    r"\b(deeply|truly|mastered|expert|passionate|loves|hates|always|never|fully understands)\b",
    re.IGNORECASE,
)
QUOTED = re.compile(r"「[^」]*」")
REF = re.compile(r"^(session:|topic:|note:|bank:|m_)\S+$")
DELETE_REASONS = ("contradicted", "superseded", "stale", "low-signal")


def _file():
    return store.home() / "memory.json"


def entries():
    return store.read_json(_file(), [])


def _check_text(text):
    if not str(text or "").strip():
        raise Refusal("text_required", "A memory entry needs text.")
    if len(text) > MAX_CHARS:
        raise Refusal("text_too_long", f"Keep entries to {MAX_CHARS} characters.", length=len(text))
    match = BANNED.search(QUOTED.sub("", text))
    if match:
        raise Refusal(
            "banned_phrase",
            f"Do not write {match.group(0)!r} about the learner unless you quote them in 「 」.",
        )


def _check_refs(refs):
    if not refs:
        raise Refusal("refs_required", "Every entry must cite at least one reference.")
    for ref in refs:
        if not REF.match(str(ref)):
            raise Refusal("invalid_ref", f"Bad reference {ref!r}. Use session:, topic:, note:, bank: or m_.")


def apply_ops(ops):
    rows = [dict(e) for e in entries()]
    ids = []
    for op in ops:
        kind = op.get("op")
        if kind == "add":
            if op.get("slot") not in SLOTS:
                raise Refusal("invalid_slot", f"Slot must be one of {sorted(SLOTS)}.")
            _check_text(op.get("text"))
            _check_refs(op.get("refs"))
            new_id = f"m_{uuid.uuid4().hex[:8]}"
            rows.append(
                {
                    "id": new_id,
                    "slot": op["slot"],
                    "section": op.get("section") or SLOTS[op["slot"]][0],
                    "text": op["text"],
                    "refs": op["refs"],
                    "at": store.now(),
                }
            )
            ids.append(new_id)
            continue
        target = next((r for r in rows if r["id"] == op.get("target_id")), None)
        if kind not in ("edit", "delete"):
            raise Refusal("invalid_op", "op must be add, edit or delete.")
        if target is None:
            raise Refusal("unknown_memory_id", f"No memory entry {op.get('target_id')}.")
        if kind == "edit":
            _check_text(op.get("new_text"))
            _check_refs(op.get("new_refs"))
            target.update(text=op["new_text"], refs=op["new_refs"], at=store.now())
            ids.append(target["id"])
        else:
            if op.get("reason") not in DELETE_REASONS:
                raise Refusal("invalid_delete_reason", f"Reason must be one of {DELETE_REASONS}.")
            rows.remove(target)
    store.write_json(_file(), rows)
    return ids


def render():
    rows = entries()
    out = []
    for slot in SLOTS:
        chosen = [r for r in rows if r["slot"] == slot]
        if not chosen:
            continue
        out.append(f"## {slot}")
        sections = {}
        for row in chosen:
            sections.setdefault(row["section"], []).append(row)
        for section, items in sections.items():
            out.append(f"### {section}")
            out.extend(f"- [{r['id']}] {r['text']}" for r in items)
    return "\n".join(out)
