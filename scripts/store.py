"""File storage under $DTUTOR_HOME (default ~/.dtutor). Everything is JSON or Markdown."""
import json
import os
import re
import tempfile
import time
from pathlib import Path


class Refusal(Exception):
    """A rule said no. Reported to the model as JSON so it can act on the reason."""

    def __init__(self, code, message="", **extra):
        super().__init__(code)
        self.code = code
        self.message = message
        self.extra = extra


def home():
    return Path(os.environ.get("DTUTOR_HOME") or Path.home() / ".dtutor")


def now():
    return float(os.environ.get("DTUTOR_NOW") or time.time())


def slugify(text):
    slug = re.sub(r"[^\w]+", "-", str(text).strip().lower(), flags=re.UNICODE).strip("-")
    return slug or "untitled"


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, data):
    """Atomic, so a crash can never leave a half-written path behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    os.replace(tmp, path)


def append_jsonl(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path):
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def state():
    return read_json(home() / "state.json", {})


def save_state(data):
    write_json(home() / "state.json", data)


def topic_file(slug):
    return home() / "topics" / slug / "path.json"


def list_topics():
    root = home() / "topics"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "path.json").is_file())


def new_path(slug, name, goal):
    return {
        "version": 1,
        "slug": slug,
        "name": name,
        "goal": goal,
        "created_at": now(),
        "mode": "outline",
        "profile": {},
        "profile_declined": False,
        "materials": [],
        "modules": [],
        "attempts": [],
        "pending": None,
        "next_question": 1,
        "qualitative": {},
        "qualitative_log": [],
        "repetition": {},
        "deferred": [],
        "overrides": {},
        "errors": [],
        "explained": {},
        "observations": {},
        "handoff": None,
    }


def resolve_topic(explicit=None):
    slug = explicit or state().get("active")
    if not slug:
        raise Refusal(
            "no_active_topic",
            "No topic is active. Create one with `dtutor topic new` or pick one with `dtutor topic use`.",
            topics=list_topics(),
        )
    if not topic_file(slug).is_file():
        raise Refusal("unknown_topic", f"No topic named {slug}.", topics=list_topics())
    return slug


def load_path(explicit=None):
    return read_json(topic_file(resolve_topic(explicit)))


def save_path(path):
    write_json(topic_file(path["slug"]), path)
