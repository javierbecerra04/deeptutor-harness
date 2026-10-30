---
name: quiz
description: Use when someone asks to be quizzed or tested on a subject ("quiz me on X", "test my knowledge of X", "give me practice questions", "make questions like this exam"), in any field, without working through a study path.
argument-hint: "[subject] [number of questions] [difficulty]"
allowed-tools: Bash(dtutor *), Read, Grep, Glob, AskUserQuestion, WebSearch, WebFetch
---

# Quiz

Generate questions grounded in evidence, ask them one at a time, grade each answer, and keep what was missed.

Request: $ARGUMENTS

Default to 5 questions at mixed difficulty if they did not say. Do not ask about settings that have a sensible default.

## Prepare, silently

1. Run `dtutor bank list --wrong --limit 20` and `dtutor memory show`. If they have history on this subject, do not repeat old questions, and lean toward their weak areas.
2. Ground the questions. If they named a document, register it with `dtutor source add <path>`, then use `dtutor source search` and `dtutor source read`. Cite as [p.12] only what you read. For facts you are unsure of, look them up.
3. Plan the set. Give each question a distinct focus, a type and a difficulty. Keep the plan to yourself.

If they gave a past paper and want questions like it, mimic its style and difficulty, and label each one as your adaptation, never as an original exam question.

## Ask

Your reply holds exactly one question, and nothing about the ones to come beyond "Question 1 of 5". Write each question only when its turn comes. The answer and explanation stay out of the reply until they have answered.

Types:
- `choice`: exactly four options. Sort the options alphabetically by their text, then label them A to D, so position gives nothing away. Use `AskUserQuestion` with the letter as the label and the text as the description, or print them if that tool is unavailable.
- `true_false`: one proposition to judge.
- `fill_in_blank`: one `____` for one word or short phrase.
- `short_answer`: a few sentences. `written`: a longer discussion. `coding`: code or pseudocode.

Question rules:
- Test whether they can tell things apart and apply them, not whether they can recite.
- Each distractor encodes a specific, plausible misconception and matches the right answer in length and tone.
- Never hint. No markers such as "(Recommended)".

## Grade

1. Record each answer with `dtutor bank add --json '<json>'`. Keep the JSON in single quotes, and write any apostrophe inside it as `'\''`. Include `type`, `question`, `options` for choice, `expected`, `learner_answer`, `explanation`, `difficulty`, `topic_label`, and, for open types, your `credit` from 0 to 1. The engine grades `choice` and `true_false` itself and ignores any credit you pass for them.
2. Tell them the result and why, in a few lines. When they got it wrong, explain precisely where the reasoning went off, against the correct answer.
3. If they ask a follow-up, answer it, grounded in that question. Then continue.
4. Then give the next question.

## Finish

Give the score, the pattern in what they missed, and one thing to work on. If the subject deserves more than a quiz, say that `/deeptutor:learn` can turn it into a study path.
