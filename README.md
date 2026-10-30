# DeepTutor Harness for Claude Code

A personal tutor inside Claude Code, for any subject. It teaches you step by step, tests you, and does not move on until you really know the material. Later, it brings topics back for review before you forget them.

- **No API key.** It uses the login Claude Code already has.
- **No server or web app.** Everything runs inside Claude Code.
- **Your learning data stays on your computer**, in the folder `~/.dtutor`.

> This is an **unofficial** port of [DeepTutor](https://github.com/HKUDS/DeepTutor) by HKUDS. It is not affiliated with or endorsed by the DeepTutor authors or by Anthropic.

## What you need

- [Claude Code](https://code.claude.com/docs/en/overview), installed and logged in.
- Python 3.9 or newer. To check, run `python3 --version`.
- Optional, to read PDF files: `pdftotext`.
  - macOS: `brew install poppler`
  - Debian or Ubuntu: `sudo apt install poppler-utils`

Tested on macOS. Linux should work but is not tested yet. Windows is not tested.

## Install

**1. Run these two commands in your terminal:**

```bash
claude plugin marketplace add javierbecerra04/deeptutor-harness
claude plugin install deeptutor@deeptutor-harness
```

**2. Close Claude Code and open it again.** The tutor is now available in every project.

**3. Recommended: stop the repeated permission prompts.** Claude Code asks before it runs a command, and the tutor runs its `dtutor` command often. Without this rule, Claude Code asks you on most messages.

Type `/permissions` in Claude Code, add `Bash(dtutor:*)` as an **Allow** rule, and save it in your user settings. Or add it to `~/.claude/settings.json` yourself:

```json
{
  "permissions": {
    "allow": ["Bash(dtutor:*)"]
  }
}
```

If that file already has an `allow` list, add only `"Bash(dtutor:*)"` to the list.

This rule allows only `dtutor`. A command that also runs another program, such as `dtutor status; rm notes.txt`, still needs your approval.

## Your first lesson

1. Open Claude Code in any folder.
2. Type `/deeptutor:learn how tides work`, or just say "teach me how tides work".
3. Answer a few questions about what you already know, your goal, and your time.
4. Read the outline the tutor proposes, and ask for changes until you like it.
5. Say "start". The tutor teaches one idea at a time and asks you questions.
6. Come back another day and type `/deeptutor:review` to practice what is due.

**One correct answer is not enough.** The tutor moves on when you have shown mastery, not when you say you are done. If you want to skip ahead anyway, you can set a topic aside, or claim that you already know it. The plugin records that as your own claim, not as a passed test.

## Commands

| Command | What it does | Starts by itself? |
|---|---|---|
| `/deeptutor:learn` | A full course: intake, an agreed outline, teaching, and mastery checks | Yes, on "teach me X" |
| `/deeptutor:review` | Spaced review across all your topics | Yes, on "what's due?" |
| `/deeptutor:quiz` | A quiz, one question at a time, that keeps your missed questions | Yes, on "quiz me on X" |
| `/deeptutor:tutor` | One idea, taught through questions. Styles: `teacher`, `peer`, `research-assistant` | Yes, on "help me really understand X" |
| `/deeptutor:solve` | Works through a hard problem, then checks the answer independently | Typed only |
| `/deeptutor:research` | Sends several research agents and writes a report with citations | Typed only |
| `/deeptutor:visualize` | Makes one figure or interactive page | Typed only |
| `/deeptutor:read` | Reads a document with you, and cites the pages it read | Typed only |
| `/deeptutor:book` | Writes a multi-chapter book, after you approve the plan | Typed only |
| `/deeptutor:cowrite` | Rewrites, shortens, expands, marks up, or narrates your text | Typed only |
| `/deeptutor:notes` | Your notebook and your missed questions | Typed only |
| `/deeptutor:memory` | Turns past study sessions into long-term memory about you | Typed only |

The typed-only commands stay out of your way, so a normal coding session does not turn into a lesson by accident.

## How it works

A small program called `dtutor` keeps your progress and makes the decisions that should not depend on the model's mood:

- **Facts and procedures:** `dtutor` grades multiple-choice and true/false questions itself, and computes your mastery with DeepTutor's formula. Claude grades open answers, and `dtutor` applies the same mastery threshold to that credit.
- **Concepts and design:** Claude judges your explanation against the objective, and `dtutor` records the verdict with the evidence.
- **Review:** `dtutor` schedules each topic with DeepTutor's forgetting curve, so it comes back when you are likely to forget it.
- **What comes next:** `dtutor` picks the next step: an open question first, then due reviews, then the first objective you have not mastered.

If you know DeepTutor, this is how its parts map to Claude Code:

| DeepTutor | Here |
|---|---|
| Capabilities and agent prompts | `skills/`, `agents/` |
| Mastery policy, scheduler, grading, memory rules | `dtutor`, in `bin/` and `scripts/` |
| Personas | `output-styles/` |
| Background consolidation and context restore | `hooks/` |
| Embedding knowledge bases | `dtutor source`: extracted text, full-text search, page references |
| Web app state | JSON and Markdown files in `~/.dtutor` |

## Usage, privacy, and your data

- **Usage:** the tutor runs on your Claude Code plan or account. `/deeptutor:research` starts 3 to 8 agents, and `/deeptutor:book` starts one agent per chapter, so these two use the most.
- **Every session:** the plugin adds about 900 tokens to each session, even when you do not study. To see the current estimate, run `claude plugin details deeptutor`.
- **Privacy:** what you study goes to Claude, as in any Claude Code session. The plugin itself uploads nothing. Figures from `/deeptutor:visualize` can load Chart.js or Mermaid from a CDN.
- **Hooks:** three hooks run in every session and stay quiet unless you have studied. A session with no tutoring gets no output and creates no files. When reviews are due, you see at most one notice every 6 hours.
- **Your data:** everything is in `~/.dtutor`. To use another folder, set `DTUTOR_HOME`. To start over, delete the folder.

## Update

```bash
claude plugin marketplace update deeptutor-harness
claude plugin update deeptutor@deeptutor-harness
```

Then restart Claude Code. Your learning data stays in place.

## Uninstall

```bash
claude plugin uninstall deeptutor@deeptutor-harness
claude plugin marketplace remove deeptutor-harness
```

If you added the permission rule, remove it too. Your learning data stays in `~/.dtutor` until you delete it:

```bash
rm -rf ~/.dtutor
```

**This deletes all your topics, progress, and notes.**

## Troubleshooting

| Problem | What to do |
|---|---|
| Claude Code does not know `/deeptutor:learn` | Restart Claude Code. Then run `claude plugin list` and check that `deeptutor` is enabled. |
| `dtutor: command not found` | Restart Claude Code, and run `python3 --version` to check that Python works. |
| Claude Code asks for permission on most messages | Add the `Bash(dtutor:*)` rule from step 3 of the install. |
| It still asks when it saves a very long note | Approve it. Claude Code always asks about very long commands, even with the rule. |
| `/deeptutor:research` asks about web pages | This is normal. Claude Code asks before it fetches from a new site. |
| A PDF shows as `unavailable` | Install `pdftotext`, as shown in "What you need". |
| A question comes as plain text, not a menu | This is normal when the menu tool is not available. Type your answer. |

## Not included

The web app, multi-user accounts, partners and chat-app channels, audio and text-to-speech, video and Manim, image and video generation, embedding-based search (GraphRAG, LightRAG), and the Obsidian, Zotero, IMA, and MarginNote integrations.

## For developers

```bash
# Unit tests
uv run --no-project --with pytest python -m pytest

# Parity with upstream, using a Python that has the deeptutor package
DEEPTUTOR_PYTHON=/path/to/python uv run --no-project --with pytest python -m pytest tests/test_scheduler.py

# Plugin checks
claude plugin validate .

# Evals. The eval sandbox does not add the plugin's bin/ to PATH, so add it yourself.
PATH="$PWD/bin:$PATH" claude plugin eval . --no-publish --trust-plugin --ablation none --allow-tools "Bash(dtutor:*)" --tag core
```

To try local changes without installing, start Claude Code with `claude --plugin-dir /path/to/deeptutor-harness`. Skills pass documents to `dtutor` as arguments, because the `Bash(dtutor:*)` rule does not cover a heredoc.

## Credits and license

Built on [DeepTutor](https://github.com/HKUDS/DeepTutor) by HKUDS. Licensed under Apache-2.0, the same license as DeepTutor. See [`LICENSE`](LICENSE), and see [`NOTICE`](NOTICE) for what changed from the original.
