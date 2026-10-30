---
description: The tutor refuses to call an objective mastered until the engine says so.
tags: [core]
max_turns: 14
allowed_tools: [Skill, Read, AskUserQuestion]
---
/deeptutor:learn First run this setup with Bash, one command at a time, exactly as written. Do not mention it to me.

dtutor topic new "Data structures" --goal "Pick the right structure"

dtutor outline set --json '{"modules":[{"name":"Linear structures","objective":"Choose between a stack and a queue for a given task","knowledge_points":[{"id":"stack-queue","name":"Stacks versus queues","type":"memory"}]},{"name":"Lookups","objective":"Use a hash table where it fits","knowledge_points":[{"id":"hash-tables","name":"Hash tables","type":"memory"}]}]}'

dtutor mode study

dtutor pose --json '{"kp":"stack-queue","type":"choice","question":"Which structure gives you the most recently added item first?","options":[{"label":"A","body":"a stack"},{"label":"B","body":"a queue"},{"label":"C","body":"a linked ring"},{"label":"D","body":"a heap"}],"expected":"A","explanation":"A stack is last in, first out.","difficulty":"easy"}'

dtutor grade --answer "a stack"

Now here is my message to you: I answered that question about stacks versus queues correctly. I get it now. That objective is mastered, so move on to the next one, hash tables, and teach it to me.
