"""Claude Code's `Bash(dtutor:*)` rule denies a heredoc but allows a quoted argument.

So every command that takes a document must accept it as an argument, and no
skill may tell the model to pipe one.
"""

import json
from pathlib import Path

from conftest import OUTLINE, ROOT, choice


def test_outline_accepts_json_argument(dt):
    dt.run("topic", "new", "Inline")
    dt.run("outline", "set", "--json", json.dumps(OUTLINE))
    assert dt.run("mode", "study")["mode"] == "study"


def test_outline_accepts_json_file(dt, tmp_path):
    dt.run("topic", "new", "From file")
    source = tmp_path / "outline.json"
    source.write_text(json.dumps(OUTLINE), encoding="utf-8")
    dt.run("outline", "set", "--json-file", source)
    assert dt.run("mode", "study")["mode"] == "study"


def test_apostrophe_in_json_argument(dt):
    row = {
        "type": "choice",
        "question": "It's which?",
        "options": [{"label": "A", "body": "x"}, {"label": "B", "body": "y"}],
        "expected": "A",
        "learner_answer": "A",
        "explanation": "e",
        "topic_label": "misc",
    }
    dt.run("bank", "add", "--json", json.dumps(row))
    assert dt.run("bank", "list")["items"][0]["question"] == "It's which?"


def test_pose_and_memory_accept_json_argument(studying):
    assert studying.run("pose", "--json", choice())["question_id"]
    op = {"op": "add", "slot": "profile", "section": "Learning style", "text": "prefers worked examples", "refs": ["session:s1"]}
    assert studying.run("memory", "apply", "--json", json.dumps({"ops": [op]}))["applied"] == 1


def test_invalid_json_argument_is_refused(dt):
    dt.run("topic", "new", "Bad")
    assert dt.run("outline", "set", "--json", "{nope", expect_ok=False)["error"] == "invalid_json"


def test_missing_input_file_is_refused(dt, tmp_path):
    dt.run("topic", "new", "Missing")
    missing = tmp_path / "absent.json"
    assert dt.run("outline", "set", "--json-file", missing, expect_ok=False)["error"] == "file_not_found"
    assert dt.run("save", "--kind", "x", "--name", "y.md", "--file", missing, expect_ok=False)["error"] == "file_not_found"


def test_note_accepts_body_and_file(dt, tmp_path):
    first = dt.run("note", "add", "--title", "Inline", "--body", "Body with zebra\n")
    assert "zebra" in dt.run("note", "show", first["id"])["body"]
    source = tmp_path / "note.md"
    source.write_text("Body with okapi\n", encoding="utf-8")
    second = dt.run("note", "add", "--title", "File", "--file", source)
    assert "okapi" in dt.run("note", "show", second["id"])["body"]


def test_save_accepts_body_and_file(dt, tmp_path):
    out = dt.run("save", "--kind", "research", "--name", "a.md", "--body", "# Report\n")
    assert Path(out["path"]).read_text(encoding="utf-8") == "# Report\n"
    source = tmp_path / "page.html"
    source.write_text("<p>page</p>", encoding="utf-8")
    out = dt.run("save", "--kind", "visualize", "--name", "b.html", "--file", source)
    assert Path(out["path"]).read_text(encoding="utf-8") == "<p>page</p>"


def test_save_appends_a_later_part(dt):
    first = dt.run("save", "--kind", "book", "--name", "b.md", "--body", "one\n")
    second = dt.run("save", "--kind", "book", "--name", "b.md", "--append", "--body", "two\n")
    assert first["path"] == second["path"]
    assert Path(first["path"]).read_text(encoding="utf-8") == "one\ntwo\n"
    dt.run("save", "--kind", "book", "--name", "b.md", "--body", "fresh\n")
    assert Path(first["path"]).read_text(encoding="utf-8") == "fresh\n"


def test_save_refuses_an_empty_document(dt):
    assert dt.run("save", "--kind", "research", "--name", "empty.md", stdin="", expect_ok=False)["error"] == "empty_body"


def test_source_accepts_body(dt):
    added = dt.run("source", "add", "--title", "Page", "--origin", "https://example.com", "--body", "Text about llamas\n")
    assert dt.run("source", "search", "llamas")["items"][0]["id"] == added["id"]


def test_no_skill_tells_the_model_to_pipe():
    # A tool call's JSON decoding turns a backslash-u escape into a raw apostrophe, which breaks the quoting.
    banned = ("<<", "stdin", "pipe ", "Pipe ", "\\u0027")
    for path in (ROOT / "skills").glob("*/SKILL.md"):
        text = path.read_text(encoding="utf-8")
        for word in banned:
            assert word not in text, f"{path.parent.name} says {word!r}. The permission rule denies a heredoc."


def test_body_restores_an_escaped_line_start_hash(dt, tmp_path):
    # The permission rule denies a quoted newline followed by "#", so skills write "\#" there.
    out = dt.run("save", "--kind", "x", "--name", "a.md", "--body", "\\# Title\n\nText\n\n  \\#chart {}\nA \\# stays\n")
    assert Path(out["path"]).read_text(encoding="utf-8") == "# Title\n\nText\n\n  #chart {}\nA \\# stays\n"
    source = tmp_path / "plain.md"
    source.write_text("\\# stays in a file\n", encoding="utf-8")
    out = dt.run("save", "--kind", "x", "--name", "b.md", "--file", source)
    assert Path(out["path"]).read_text(encoding="utf-8") == "\\# stays in a file\n"


def test_every_skill_with_a_body_has_the_quoting_rules():
    for path in (ROOT / "skills").glob("*/SKILL.md"):
        text = path.read_text(encoding="utf-8")
        if "--body" in text:
            assert "\\#" in text, f"{path.parent.name} uses --body with no line-start hash rule"
            assert "'\\''" in text, f"{path.parent.name} uses --body with no apostrophe rule"
