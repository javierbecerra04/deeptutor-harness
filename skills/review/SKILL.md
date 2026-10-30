---
name: review
description: Use when someone wants to do their spaced-repetition review of subjects they studied ("what's due", "review what I learned", "test me on old material"), or after a DeepTutor notice about due reviews. Not for flashcards in other tools or code review.
argument-hint: "[topic]"
allowed-tools: Bash(dtutor *), Read, AskUserQuestion
---

# Spaced review

Review re-tests what is already mastered. The engine schedules it and refuses anything else. Do not roll on into teaching new objectives.

Request: $ARGUMENTS

1. Run `dtutor reviews --all-topics`. If `count` is 0, say nothing is due, and offer `/deeptutor:learn` to go forward. Stop there.
2. Tell them how many are due, per topic, and start with the highest `forgetting_risk`. A due date is a reminder, not a limit: if they name something else they mastered, review that.
3. For each topic: `dtutor topic use <slug>`, then `dtutor mode review`.
4. For each due objective, test it. Use a new angle on the idea, not a repeat of an old question, and check `dtutor bank list --topic <slug>` to avoid repeats.
   - `memory` or `procedure`: pose a question with `dtutor pose --json '<json>'`, using the JSON from `/deeptutor:learn`. Write any apostrophe inside it as `'\''`. Show the engine's returned options in that order, with `AskUserQuestion` or as text. Then stop and wait for the answer.
   - `concept` or `design`: ask for an explanation in their own words. Record it with `dtutor assess --kp ID --passed|--failed --evidence "<their exact words>"`.
5. Grade with `dtutor grade --answer "<their answer>"`, as `/deeptutor:learn` describes. Give the explanation from the result. A miss may send the objective back below its gate. Tell them plainly if it does, and say that study mode will pick it up.
6. When the queue is empty or they stop, run `dtutor mode study` on each topic you touched. Say what held up, what slipped, and when the next review falls due.

Ask one question per turn. Never reveal the answer before they respond.
