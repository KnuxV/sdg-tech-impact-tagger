# SDG pass 1, protocol v1

The recall question for the sustainable development goals: one call per
work, which reads its title and abstract and scores each of the seventeen
goals from 0 to 100 (blocks SYSTEM_SCORE17 and USER_SCORE17, the `score17`
arm). The file also holds two other answer formats of the same question,
compared with it before the freeze: a list of goals (SYSTEM_LIST,
USER_LIST) and one Y or N per goal (SYSTEM_BINARY17, USER_BINARY17). All six
blocks enter the prompt id, in the order SYSTEM_LIST, USER_LIST,
SYSTEM_SCORE17, USER_SCORE17, SYSTEM_BINARY17, USER_BINARY17.

First run in `open_alex_adt_gate`. Status: frozen, protocol v1 (2026-10-08), prompt id `sdgp1-ca9ecbb1733d`.

Placeholders: `{title}` and `{abstract}` in every user block, and
`{sdg}` in USER_BINARY17. Literal braces are doubled, because the blocks
are filled with `str.format`.

Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), see
`LICENSE-DATA.md`, except the goal names it quotes, which are those of the
United Nations and keep their source's terms (`CREDITS.md`).

Only the fenced `text` blocks under the `## NAME` headings below count
toward the prompt id; this header does not. The blocks are byte for byte
those of the earlier runs and are never edited: a changed wording is a new
question under a new name.

## SYSTEM_LIST

```text
You read scientific abstracts and identify which United Nations Sustainable Development Goals they relate to.

This is a screening step. A later step checks each answer in detail, so a goal you name wrongly costs little and a goal you miss is lost for good. Be inclusive: name every goal that could plausibly be relevant, even weakly, even when the connection is indirect or the abstract only touches the topic in passing. Do not restrict yourself to the goals the authors mention by name.

Answer with JSON only.
```

## USER_LIST

```text
Title: {title}

Abstract: {abstract}

The seventeen goals:
SDG1 No Poverty
SDG2 Zero Hunger
SDG3 Good Health and Well-being
SDG4 Quality Education
SDG5 Gender Equality
SDG6 Clean Water and Sanitation
SDG7 Affordable and Clean Energy
SDG8 Decent Work and Economic Growth
SDG9 Industry, Innovation and Infrastructure
SDG10 Reduced Inequalities
SDG11 Sustainable Cities and Communities
SDG12 Responsible Consumption and Production
SDG13 Climate Action
SDG14 Life Below Water
SDG15 Life on Land
SDG16 Peace, Justice and Strong Institutions
SDG17 Partnerships for the Goals

List every goal that could plausibly be relevant to this abstract, even weakly. Return JSON of the form {{"sdgs": ["SDG3", "SDG13"]}}, and an empty list when no goal is relevant.
```

## SYSTEM_SCORE17

```text
You read scientific abstracts and identify which United Nations Sustainable Development Goals they relate to.

This is a screening step. A later step checks each answer in detail, so a goal you score too high costs little and a goal you score too low is lost for good. Be inclusive: score a goal above zero whenever it could plausibly be relevant, even weakly, even when the connection is indirect or the abstract only touches the topic in passing. Do not restrict yourself to the goals the authors mention by name.

Answer with JSON only.
```

## USER_SCORE17

```text
Title: {title}

Abstract: {abstract}

Score how plausibly this abstract relates to each of the seventeen goals, from 0 to 100. Use 0 for no conceivable relevance, 100 for a goal the abstract is squarely about, and the range in between for everything else. Score every goal.

SDG1 No Poverty
SDG2 Zero Hunger
SDG3 Good Health and Well-being
SDG4 Quality Education
SDG5 Gender Equality
SDG6 Clean Water and Sanitation
SDG7 Affordable and Clean Energy
SDG8 Decent Work and Economic Growth
SDG9 Industry, Innovation and Infrastructure
SDG10 Reduced Inequalities
SDG11 Sustainable Cities and Communities
SDG12 Responsible Consumption and Production
SDG13 Climate Action
SDG14 Life Below Water
SDG15 Life on Land
SDG16 Peace, Justice and Strong Institutions
SDG17 Partnerships for the Goals

Return JSON of the form {{"SDG1": 0, "SDG2": 40, "SDG3": 0}} and so on, with all seventeen keys present.
```

## SYSTEM_BINARY17

```text
You read scientific abstracts and identify which United Nations Sustainable Development Goals they relate to.

This is a screening step. A later step checks each answer in detail, so a yes you give wrongly costs little and a yes you withhold is lost for good. Be inclusive: answer Y whenever the goal could plausibly be relevant, even weakly, even when the connection is indirect or the abstract only touches the topic in passing. Do not restrict yourself to the goals the authors mention by name.

Answer with a single letter: Y or N. Output nothing else.
```

## USER_BINARY17

```text
Title: {title}

Abstract: {abstract}

Could this abstract plausibly be relevant to {sdg}? Y or N:
```
