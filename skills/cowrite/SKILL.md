---
name: cowrite
description: Edit a draft by instruction, mark it up for reading, or write a narration script. Run it when asked with /deeptutor:cowrite.
argument-hint: "[rewrite|shorten|expand|mark|narrate] [file or text] [instruction]"
disable-model-invocation: true
allowed-tools: Read, Edit, Write, Grep, Bash(dtutor *)
---

# Co-writer

Request: $ARGUMENTS

If the target is a file, read it, and write the result back only when they asked you to change the file. Otherwise reply with the result. If they named reference sources, use `dtutor source read` and base claims on those only.

- **rewrite, shorten, expand:** follow their instruction and keep their meaning and voice. Your reply is the edited text alone, with no quotes and no explanation.
- **mark:** keep the original wording, punctuation, paragraphs and Markdown. Insert only two inline markers: 【term】 for a short key concept, name or value, and 《statement》 for a short definition, finding or conclusion. Use at most one term per 100 characters and two statements per paragraph. Do not nest markers or wrap Markdown syntax. If nothing needs marking, return the text unchanged.
- **narrate:** rewrite it to be heard, not read: short spoken sentences, numbers and symbols written as they are said, and transitions in place of headings. This produces the script only. The harness has no text-to-speech.

If they asked to keep the result, run `dtutor note add --title "..." --kind cowrite --body '<body>'`. In the body, write any apostrophe as `'\''` and any `#` that starts a line as `\#`. If they did not, offer it once.
