---
name: research
description: Multi-agent deep research with a cited report, on any topic. Run it when asked with /deeptutor:research.
argument-hint: "[topic] [notes|report|comparison]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, WebSearch, WebFetch, Agent, AskUserQuestion, Bash(dtutor *)
---

# Deep research

Topic: $ARGUMENTS

The report rests only on evidence gathered in this run. If `WebSearch` and `WebFetch` are unavailable and no local sources were given, say so and stop. Do not write a report from memory.

## 1. Clarify

Make the topic precise, with as few questions as possible. Ask only when two readings would produce different reports. Default the form to `report`.

## 2. Decompose

Split the refined topic into 3-6 sub-topics that are disjoint, together cover the topic, and tell a researcher what to look for. Order them background, then core, then implications. Show the list in one short message and continue.

## 3. Research in parallel

Dispatch one `deeptutor:researcher` agent per sub-topic, all in one message. Each prompt gives the overall topic, the sub-topic with its overview, the report form, and any local files.

Each agent returns Findings, Sources, Gaps and New sub-topics. If one proposes a new sub-topic that is truly distinct and matters to the question, run it too, with at most 2 extra agents overall. If an agent fails, say so and continue with the rest.

## 4. Report

Renumber the citations across agents, and map each to its URL or file.

1. **Outline.** A title, then 3-6 sections in reading order. Every research block appears in at least one section.
2. **Sections.** Lead with a claim, then develop the reasoning chain: mechanisms, boundary conditions, examples and counterexamples, trade-offs, and open questions. Use paragraphs as the backbone. Use a table or a Mermaid diagram only where it clarifies. Thin evidence gets stated uncertainty, not padding.
3. **Citations.** Put [1] after each claim. Every number must come from a page an agent read and listed. Keep author findings apart from your inference. If a section found no evidence, write no citations and say so.
4. **Conclusion.** Answer the question, name the disagreement and the gaps, and do not add new claims.
5. **References.** A numbered list with the URLs.

For `notes`, write dense bullets with citations and skip the prose. For `comparison`, build a table of claim, method, data, result and limitation, with citations, then give a verdict.

## 5. Deliver

Save the report in parts, one command per part. Each part has this form:
- It holds at most 4,000 characters and starts at a heading.
- Every heading starts with a backslash, as in `\## Findings`, and so does any other line that starts with `#`.
- Every apostrophe is written as `'\''`.
- Each command is `dtutor` alone, with nothing chained to it. Its JSON output says whether it worked.

1. Run `dtutor save --kind research --name <slug>.md --body '<first part>'`.
2. Run `dtutor save --kind research --name <slug>.md --append --body '<next part>'` for each later part, in order.

If every command succeeds, give the path, the bottom-line answer, and the main gaps. If one fails, say so and paste the full report with its citations in your reply.
