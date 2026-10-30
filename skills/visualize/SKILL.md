---
name: visualize
description: Turn a concept or data into one figure or interactive page for learning. Run it when asked with /deeptutor:visualize.
argument-hint: "[what to show]"
disable-model-invocation: true
allowed-tools: Read, Bash(dtutor *), Bash(python3 *)
---

# Visualize

Request: $ARGUMENTS

## 1. Choose the form from the verb, not the noun

| The learner wants | Render | Genre |
|---|---|---|
| "how does X work", "give me intuition", "I don't get X" | svg or html | illustrative, interactive |
| "what are the parts", "architecture" | svg or mermaid | structural |
| "the process", "the steps", "what happens when" | mermaid or svg | flowchart |
| a cycle or staged walkthrough | html | stepper |
| compare quantities, show data | chartjs | chart |
| relationships, schema | mermaid | structural |

Prefer a static figure when it is enough. Choose html only when interaction with changing state is the core of the experience. "How does X work" defaults to a spatial metaphor that shows the mechanism, not a safe flowchart.

## 2. Build it

Start from `${CLAUDE_PLUGIN_ROOT}/skills/visualize/shell.html`, which handles light and dark themes.

Keep to this budget. A sparse, correct figure beats a dense one:
- A subtitle has at most 5 words. Detail goes in your chat reply.
- Use 2-3 colors, and let color encode meaning, never decoration.
- A row holds at most 4 full-width boxes. Wrap the rest.
- If they listed 6 or more components, draw the main flow only, and say they can ask for any sub-flow.
- Use sentence case everywhere. No text under 11px.

By form:
- **svg:** exactly one `<svg>` with `xmlns` and a `viewBox`, no background rect, and the shell's classes (`t`, `th`, `ts`, `box`, `arr`, `c-*`). Lay out several parts as regions inside it. It must be well-formed XML, with `&` written as `&amp;`.
- **chartjs:** `<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.9/dist/chart.umd.min.js"></script>`, with the config as strict JSON that has `type` and `data`.
- **mermaid:** `<script src="https://cdn.jsdelivr.net/npm/mermaid@11.6.0/dist/mermaid.min.js"></script>`, then `mermaid.initialize({startOnLoad: true})`. Node IDs have no spaces.
- **html:** self-contained, with visible controls and a clear first state.

## 3. Validate before you hand it over

Check the code, and fix the one defect with the smallest change. Do not redesign it.
- svg: `python3 -c "import sys, xml.dom.minidom as m; m.parseString(sys.argv[1])" '<the svg>'`
- chartjs: `python3 -c "import json, sys; d = json.loads(sys.argv[1]); assert d['type'] and d['data']" '<the config>'`

Run each check as that one command, with nothing before it and no temporary file.

## 4. Deliver

Save it with `dtutor save --kind visualize --name <slug>.html --body '<page>'`. In the page, write any apostrophe as `'\''` and any `#` that starts a line as `\#`. If the command fails, say so and paste the page in your reply. If it succeeds, give the path. Explain in a few sentences what to look at and the one idea it shows. Say that charts and Mermaid figures load their library from a CDN, so those need a network connection.
