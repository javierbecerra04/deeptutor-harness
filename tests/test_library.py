import json


def test_note_lifecycle(dt):
    added = dt.run("note", "add", "--title", "Fork idea", "--kind", "solve", "--tags", "a,b", "--summary", "Short", stdin="Body **text** with keyword zebra\n")
    assert added["id"] == "n1"
    assert dt.run("note", "show", "n1")["body"].startswith("Body")
    assert dt.run("note", "list")["items"][0]["title"] == "Fork idea"
    assert dt.run("note", "search", "ZEBRA")["items"][0]["id"] == "n1"
    assert dt.run("note", "search", "absent")["items"] == []
    dt.run("note", "fav", "n1")
    assert dt.run("note", "list", "--favorites")["items"][0]["favorite"] is True
    assert dt.run("note", "show", "n9", expect_ok=False)["error"] == "unknown_note"
    assert dt.run("note", "add", "--title", "Empty", stdin="", expect_ok=False)["error"] == "empty_body"


def test_bank_add_grades_choice_itself(dt):
    q = {
        "type": "choice",
        "question": "Q?",
        "options": [{"label": "A", "body": "x"}, {"label": "B", "body": "y"}],
        "expected": "A",
        "learner_answer": "B",
        "explanation": "e",
        "topic_label": "misc",
    }
    assert dt.run("bank", "add", stdin=json.dumps(q))["credit"] == 0.0
    q["learner_answer"] = "A"
    q["credit"] = 0.0
    assert dt.run("bank", "add", stdin=json.dumps(q))["credit"] == 1.0
    assert len(dt.run("bank", "list")["items"]) == 2
    assert len(dt.run("bank", "list", "--wrong")["items"]) == 1
    open_q = {"type": "short_answer", "question": "Q?", "expected": "e", "learner_answer": "a", "explanation": "e"}
    assert dt.run("bank", "add", stdin=json.dumps(open_q), expect_ok=False)["error"] == "credit_required"


def test_save_writes_inside_home_only(dt):
    out = dt.run("save", "--kind", "research", "--name", "report.md", stdin="# Report\n")
    assert out["path"].startswith(str(dt.home)) and out["path"].endswith("report.md")
    assert open(out["path"]).read() == "# Report\n"
    sneaky = dt.run("save", "--kind", "../../etc", "--name", "../../passwd", stdin="x")
    assert sneaky["path"].startswith(str(dt.home)) and ".." not in sneaky["path"]


def test_text_source_search_and_read(dt, tmp_path):
    doc = tmp_path / "notes.md"
    lines = ["# Intro"] + [f"line {i}" for i in range(200)] + ["# Later part", "the zebra crossing appears here"]
    doc.write_text("\n".join(lines))
    src = dt.run("source", "add", doc)
    assert src["status"] == "ready" and src["unit_count"] >= 2
    found = dt.run("source", "search", "zebra crossing")["items"]
    assert found[0]["id"] == src["id"] and found[0]["p"] == src["unit_count"]
    read = dt.run("source", "read", src["id"], "--pages", str(found[0]["p"]))
    assert read["untrusted"] is True and "zebra" in read["pages"][0]["text"]
    assert dt.run("source", "read", src["id"], "--pages", "999", expect_ok=False)["error"] == "locator_out_of_range"
    headings = dt.run("source", "outline", src["id"])["headings"]
    assert headings[0]["heading"] == "# Intro"
    assert dt.run("source", "list")["items"][0]["id"] == src["id"]


def test_stdin_source_and_missing_file(dt, tmp_path):
    src = dt.run("source", "add", "--title", "Web page", "--origin", "https://example.com", stdin="Fetched text about llamas\n")
    assert src["kind"] == "text" and src["origin"] == "https://example.com"
    assert dt.run("source", "search", "llamas")["items"][0]["id"] == src["id"]
    assert dt.run("source", "add", tmp_path / "nope.pdf", expect_ok=False)["error"] == "file_not_found"


def test_unreadable_source_is_marked_unavailable(dt, tmp_path):
    blob = tmp_path / "scan.xyz"
    blob.write_bytes(b"\x00\x01\x02\x03")
    src = dt.run("source", "add", blob)
    assert src["status"] == "unavailable" and src["reason"]
    assert dt.run("source", "read", src["id"], "--pages", "1", expect_ok=False)["error"] == "source_unavailable"


def test_memory_rules_are_enforced(dt):
    def op(**kw):
        return json.dumps({"ops": [{"op": "add", "slot": "profile", "section": "Learning style", "text": "prefers worked examples", "refs": ["session:s1"], **kw}]})

    assert dt.run("memory", "apply", stdin=op(refs=[]), expect_ok=False)["error"] == "refs_required"
    assert dt.run("memory", "apply", stdin=op(text="x" * 241), expect_ok=False)["error"] == "text_too_long"
    assert dt.run("memory", "apply", stdin=op(text="has mastered recursion"), expect_ok=False)["error"] == "banned_phrase"
    assert dt.run("memory", "apply", stdin=op(slot="vibes"), expect_ok=False)["error"] == "invalid_slot"
    assert dt.run("memory", "apply", stdin=op(refs=["whatever"]), expect_ok=False)["error"] == "invalid_ref"
    quoted = dt.run("memory", "apply", stdin=op(text="said 「I always forget this」"))
    assert quoted["applied"] == 1
    added = dt.run("memory", "apply", stdin=op())
    mid = added["ids"][0]
    edit = {"ops": [{"op": "edit", "target_id": mid, "new_text": "prefers diagrams", "new_refs": ["topic:x"]}]}
    dt.run("memory", "apply", stdin=json.dumps(edit))
    shown = dt.run("memory", "show")
    assert "prefers diagrams" in shown["markdown"] and mid in shown["markdown"]
    bad = {"ops": [{"op": "delete", "target_id": mid, "reason": "bored"}]}
    assert dt.run("memory", "apply", stdin=json.dumps(bad), expect_ok=False)["error"] == "invalid_delete_reason"
    gone = {"ops": [{"op": "delete", "target_id": mid, "reason": "stale"}]}
    dt.run("memory", "apply", stdin=json.dumps(gone))
    assert "prefers diagrams" not in dt.run("memory", "show")["markdown"]
    assert dt.run("memory", "apply", stdin=json.dumps(gone), expect_ok=False)["error"] == "unknown_memory_id"


def test_memory_batch_is_atomic(dt):
    ops = {"ops": [
        {"op": "add", "slot": "scope", "section": "Practicing", "text": "fine", "refs": ["topic:x"]},
        {"op": "add", "slot": "scope", "section": "Practicing", "text": "never fine", "refs": ["topic:x"]},
    ]}
    assert dt.run("memory", "apply", stdin=json.dumps(ops), expect_ok=False)["error"] == "banned_phrase"
    assert "fine" not in dt.run("memory", "show")["markdown"]
