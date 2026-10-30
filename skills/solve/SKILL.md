---
name: solve
description: Rigorous plan, work and verify mode for a hard problem in any subject. Run it when asked with /deeptutor:solve.
argument-hint: "[problem]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, WebSearch, WebFetch, Agent
---

# Deep solve

Problem: $ARGUMENTS

If the problem is missing, ask for it. Then:

1. **Plan first.** Before any work, write a short analysis and an ordered list of 2-6 steps. One step is fine for a trivial problem. Show it, and track it with the task list if you have one.
2. **Work one step at a time.** Do the step's real work with the right tool. Compute with Bash when arithmetic or code can settle something, rather than doing it in your head. After each step, write one line on what it established. Do not mark a step done before its work is complete.
3. **Replan only for a real course correction.** State the reason and give a new step list. You get two replans. After that, finish with the best of what you have, and say what remains unverified.
4. **Check.** For a non-trivial result, dispatch the `deeptutor:solution-checker` agent with the problem and your answer. If it returns FLAWED, fix the step it names and check again, once. If it returns UNSURE, say so in the answer.
5. **Answer.** State the precise result first, then give a concise, well-structured explanation of how you got there. Write maths as LaTeX. Show any figure or file you produced. Tell them what the checker said.

Offer to save it with `dtutor note add --title "..." --kind solve --body '<body>'`. In the body, write any apostrophe as `'\''` and any `#` that starts a line as `\#`.
