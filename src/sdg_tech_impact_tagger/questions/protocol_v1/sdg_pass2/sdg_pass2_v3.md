# SDG pass 2, protocol v1: the template

The check question for the sustainable development goals: one call per
(work, goal) unit that SDG pass 1 scored at or above the threshold (0.25 in
protocol v1), answered with one letter, Y or N: is the work relevant to the
goal? This file holds the wording common to every goal. What the model is
told about one goal (its official title, any guidance for it, its targets)
is in that goal's file, `sdg_pass2_v3/SDG-01.md` to `SDG-17.md`.

First run in `open_alex_adt_gate`. Status: frozen, protocol v1 (2026-10-08),
revision 3 of the wording. Template id `sdgp2-dcccffcc8667`, over SYSTEM_PASS2
then USER_PASS2. A unit's prompt id is the template id, `+`, and the id of
its goal's file.

Placeholders: SYSTEM_PASS2 takes none. USER_PASS2 takes `{title}`,
`{abstract}`, `{goal}` (the goal's short name, such as `SDG 13, Climate
Action`), `{scope}` (the GOAL_SCOPE block of the goal's file) and
`{targets}` (its GOAL_TARGETS block). Literal braces are doubled, because
the block is filled with `str.format`.

Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), see
`LICENSE-DATA.md`.

Only the fenced `text` blocks under the `## NAME` headings below count
toward the prompt id; this header does not. The blocks are byte for byte
those of the earlier runs and are never edited: a changed wording is a new
question under a new name.

## SYSTEM_PASS2

```text
You decide whether a scholarly work, read through its title and abstract, is relevant to one United Nations Sustainable Development Goal.

A screening step has already proposed this goal, and that step was told to be inclusive: it names a goal whenever the connection is merely plausible. Your job is to check that proposal against the goal's own text, without leaning either way.

Relevant means that what the work studies falls within what the goal covers, as its official title and targets state it. It does not matter whether the work helps the goal, harms it or only measures it, and it does not matter whether the authors mention the goals.

Answer Y when the work is relevant in that sense; it does not have to address a target in full or be framed as sustainability research.

Answer N when the connection is only a passing mention, a keyword that happens to match in an unrelated technical sense, a generic claim of societal or economic benefit, or a topic that this goal, as stated below, does not cover. A work can be relevant to several goals: judge this goal on its own, whatever other goals the work may also fit.

Judge only from the title and the abstract as written, not what the work might one day enable. The abstract may hold other text, such as a table of contents: judge what is there.

Answer with a single letter: Y or N. Output nothing else.
```

## USER_PASS2

```text
Title: {title}

Abstract: {abstract}

The goal is {goal}.
{scope}

These are its targets:

{targets}

Is this work relevant to {goal}? Y or N:
```
