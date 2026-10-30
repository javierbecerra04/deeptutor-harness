import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

T0 = 1_800_000_000.0
DAY = 86400.0


class Dtutor:
    """Run the real CLI as a subprocess against a throwaway home."""

    def __init__(self, home):
        self.home = home
        self.now = T0

    def run(self, *args, stdin=None, expect_ok=True):
        env = {
            **os.environ,
            "DTUTOR_HOME": str(self.home),
            "DTUTOR_NOW": str(self.now),
            "DTUTOR_SEED": "7",
        }
        proc = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "dtutor"), *map(str, args)],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        out = json.loads(proc.stdout) if proc.stdout.strip() else {}
        if expect_ok is True:
            assert proc.returncode == 0, f"{args}: {proc.stdout}\n{proc.stderr}"
        elif expect_ok is False:
            assert proc.returncode == 2, f"{args} should be refused: {proc.stdout}\n{proc.stderr}"
        return out

    def hook(self, name, payload):
        env = {**os.environ, "DTUTOR_HOME": str(self.home), "DTUTOR_NOW": str(self.now)}
        proc = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "dtutor"), "hook", name],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout) if proc.stdout.strip() else None


@pytest.fixture
def dt(tmp_path):
    return Dtutor(tmp_path / "home")


OUTLINE = {
    "modules": [
        {
            "name": "Foundations",
            "objective": "Name the core facts and apply the basic procedure unaided",
            "knowledge_points": [
                {"id": "facts", "name": "Core facts", "type": "memory"},
                {"id": "steps", "name": "Basic procedure", "type": "procedure"},
            ],
        },
        {
            "name": "Understanding",
            "objective": "Explain why the procedure works in plain language",
            "knowledge_points": [{"id": "why", "name": "Why it works", "type": "concept"}],
        },
    ]
}


def choice(kp="facts", question="Which one is right?", expected="A"):
    return json.dumps(
        {
            "kp": kp,
            "type": "choice",
            "question": question,
            "options": [
                {"label": "A", "body": "the right thing here"},
                {"label": "B", "body": "a plausible wrong one"},
                {"label": "C", "body": "another wrong choice"},
                {"label": "D", "body": "yet another mistake"},
            ],
            "expected": expected,
            "explanation": "Because the right thing is right.",
            "difficulty": "medium",
        }
    )


def correct_label(pose_result):
    for opt in pose_result["options"]:
        if opt["body"] == "the right thing here":
            return opt["label"]
    raise AssertionError("correct option missing")


def wrong_label(pose_result):
    for opt in pose_result["options"]:
        if opt["body"] != "the right thing here":
            return opt["label"]
    raise AssertionError("no wrong option")


@pytest.fixture
def studying(dt):
    dt.run("topic", "new", "Sample Subject", "--goal", "Be able to use it")
    dt.run("outline", "set", stdin=json.dumps(OUTLINE))
    dt.run("mode", "study")
    return dt
