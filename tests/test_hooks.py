import json
import subprocess
import sys
import time

from conftest import DAY, ROOT, choice, correct_label


def test_silent_when_nothing_was_ever_studied(dt):
    assert dt.hook("session-start", {"source": "startup", "session_id": "s1"}) is None
    assert not dt.home.exists(), "hooks must not create state in unrelated sessions"
    assert dt.hook("session-end", {"session_id": "s1", "reason": "other"}) is None
    assert not dt.home.exists()


def test_post_tool_ignored_for_other_commands(dt):
    payload = {"session_id": "s1", "tool_input": {"command": "git status"}}
    assert dt.hook("post-tool", payload) is None
    assert not dt.home.exists()




def test_startup_shows_user_notice_without_touching_model_context(studying):
    dt = studying
    for _ in range(3):
        dt.run("grade", "--answer", correct_label(dt.run("pose", stdin=choice())))
    dt.now += 30 * DAY
    out = dt.hook("session-start", {"source": "startup", "session_id": "s1"})
    assert "1 review" in out["systemMessage"] and "/deeptutor:review" in out["systemMessage"]
    assert "hookSpecificOutput" not in out
    assert dt.hook("session-start", {"source": "startup", "session_id": "s2"}) is None, "at most one notice per cooldown"
    dt.now += 1 * DAY
    assert dt.hook("session-start", {"source": "startup", "session_id": "s3"}) is not None


def test_session_marker_end_to_end_with_compaction_restore(studying):
    dt = studying
    posed = dt.run("pose", stdin=choice())
    payload = {"session_id": "s1", "transcript_path": "/t/s1.jsonl", "cwd": "/w", "tool_input": {"command": "dtutor grade --answer A"}}
    assert dt.hook("post-tool", payload) is None
    assert dt.hook("session-start", {"source": "compact", "session_id": "other"}) is None
    restored = dt.hook("session-start", {"source": "compact", "session_id": "s1"})
    ctx = restored["hookSpecificOutput"]["additionalContext"]
    assert restored["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "sample-subject" in ctx and "/deeptutor:learn" in ctx and "Which one is right?" in ctx
    assert "the right thing here" not in ctx.split("Open question")[0]
    assert "Because the right thing" not in ctx
    assert posed["question_id"]

    assert dt.hook("session-end", {"session_id": "s1", "reason": "other", "transcript_path": "/t/s1.jsonl", "cwd": "/w"}) is None
    pending = dt.run("session", "pending")["items"]
    assert pending[0]["session_id"] == "s1" and pending[0]["transcript_path"] == "/t/s1.jsonl"
    assert pending[0]["topic"] == "sample-subject"
    dt.now += 1 * DAY
    out = dt.hook("session-start", {"source": "startup", "session_id": "s2"})
    assert "/deeptutor:memory" in out["systemMessage"]
    dt.run("session", "done", "--all")
    assert dt.run("session", "pending")["items"] == []


def test_commands_chained_after_dtutor_are_recognised(dt):
    dt.run("topic", "new", "S")
    for cmd, expected in [
        ("cd /x && dtutor grade --answer A", True),
        ("echo dtutor", False),
        ("/plugin/bin/dtutor pose --json '{}'", True),
        ("dtutor bank add --json '{}'", True),
        ("dtutor memory show", False),
        ("dtutor session done --all", False),
        ("dtutor status --full", False),
        ("dtutor bank list", False),
        ("dtutor note add --title x --body y", False),
    ]:
        dt.hook("post-tool", {"session_id": "m", "tool_input": {"command": cmd}})
        assert (dt.home / "sessions" / "m.json").exists() is expected, cmd
        (dt.home / "sessions" / "m.json").unlink(missing_ok=True)


def test_hooks_survive_bad_input(dt):
    env_cmd = [sys.executable, str(ROOT / "bin" / "dtutor"), "hook", "session-start"]
    proc = subprocess.run(env_cmd, input="not json", capture_output=True, text=True, env={"DTUTOR_HOME": str(dt.home), "PATH": "/usr/bin"})
    assert proc.returncode == 0 and proc.stdout == ""


def test_session_start_is_fast(studying):
    dt = studying
    start = time.monotonic()
    dt.hook("session-start", {"source": "startup", "session_id": "s9"})
    assert time.monotonic() - start < 1.0


def test_resumed_session_counts_once_and_reopens(studying):
    dt = studying
    work = {"session_id": "s1", "transcript_path": "/t/s1.jsonl", "cwd": "/w", "tool_input": {"command": "dtutor grade --answer A"}}
    end = {"session_id": "s1", "reason": "other", "transcript_path": "/t/s1.jsonl"}
    for _ in range(3):
        dt.hook("post-tool", work)
        dt.hook("session-end", end)
    assert len(dt.run("session", "pending")["items"]) == 1
    dt.run("session", "done", "--all")
    assert dt.run("session", "pending")["items"] == []
    dt.hook("post-tool", work)
    dt.hook("session-end", end)
    assert len(dt.run("session", "pending")["items"]) == 1
