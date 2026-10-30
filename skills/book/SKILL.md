---
name: book
description: Compile a structured, multi-chapter learning book on any subject. Run it when asked with /deeptutor:book.
argument-hint: "[what the book should teach]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Agent, AskUserQuestion, Bash(dtutor *), WebSearch, WebFetch
---

# Book compiler

Request: $ARGUMENTS

This takes many agents, so get approval before you spend them.

## 1. Propose

From their intent, plus any sources, notes and `dtutor memory show`, propose one coherent book: title, a 1-3 sentence pitch, what is in and out of scope, target level, and 3-8 chapters. Stay anchored to their intent. Prefer fewer, richer chapters.

## 2. Design the spine

For each chapter give a title, learning objectives, prerequisites from earlier chapters only, a one-sentence summary, and the sources it draws on. Order from foundational to advanced.

Then plan each chapter's 5-10 blocks. Use `section`, `text`, `callout`, `quiz`, `flash_cards`, `figure`, `code` and `timeline`. Vary the types, like a good textbook does: explanation, example, practice, deeper insight, another angle. Each chapter has at least one `section`.

Show the spine, and say it costs one agent per chapter. Change it until they approve. **Do not write chapters before they approve.**

## 3. Write

Dispatch one `deeptutor:chapter-writer` agent per chapter, all in one message. Each prompt gives the book's level and scope, the chapter's objectives and block plan, its prerequisites, and any source ids or paths. If one fails, retry it once, then say which chapter is missing.

## 4. Assemble

Read the chapters in order. Fix contradictions and repeated material, and add a contents list. Do not rewrite the voice.

Save the book in parts, one command per part. Each part has this form:
- It holds at most 4,000 characters and starts at a heading.
- Every heading starts with a backslash, as in `\## Summary`, and so does any other line that starts with `#`.
- Every apostrophe is written as `'\''`.
- Each command is `dtutor` alone, with nothing chained to it. Its JSON output says whether it worked.

1. Run `dtutor save --kind book --name <slug>.md --body '<first part>'`, with the contents list first.
2. Run `dtutor save --kind book --name <slug>.md --append --body '<next part>'` for each later part, in order.

If every command succeeds, give the path. If one fails, say so and paste the parts that are not saved in your reply.

## 5. Keep learning

Offer to turn the book's objectives into a study path with `/deeptutor:learn`, so its gates and spaced review cover them.
