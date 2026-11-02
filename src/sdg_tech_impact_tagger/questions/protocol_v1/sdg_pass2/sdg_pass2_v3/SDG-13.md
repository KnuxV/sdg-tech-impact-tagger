# SDG pass 2, protocol v1: SDG 13, Climate Action

What the SDG pass 2 question (`../sdg_pass2_v3.md`) tells the model about
this goal. GOAL_SCOPE fills `{scope}`: the official title of the goal and,
for some goals, a guidance paragraph. GOAL_TARGETS fills `{targets}`: the
targets of the goal, one per line, as the target id, two spaces and the
target's title. Neither block holds a brace.

The second paragraph of GOAL_SCOPE is guidance written for this
question.

The official title and the target titles are the `title` fields of the UN
Statistics Division SDG API (https://unstats.un.org/sdgapi), downloaded on
2026-10-08, with runs of whitespace collapsed to one space.

First run in `open_alex_adt_gate`. Status: frozen, protocol v1 (2026-10-08),
revision 3. The goal's id has the prefix `sdggoal-13` and is listed in
`../../../IDS.tsv`.

Licence: the official title and the targets are those of the United Nations
and keep their source's terms (`CREDITS.md`); the rest is CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/), see `LICENSE-DATA.md`.

Only the fenced `text` blocks under the `## NAME` headings below count
toward the prompt id; this header does not. The blocks are byte for byte
those of the earlier runs and are never edited: a changed wording is a new
question under a new name.

## GOAL_SCOPE

```text
Official title: Take urgent action to combat climate change and its impacts

A work on the mitigation of climate change, including the reduction of greenhouse gas emissions, or on adaptation to climate change, is within this goal even where no target below names it. Reducing greenhouse gas or carbon emissions is within this goal whether or not the text names climate. Saving energy with no statement about emissions or climate is not.
```

## GOAL_TARGETS

```text
13.1  Strengthen resilience and adaptive capacity to climate-related hazards and natural disasters in all countries
13.2  Integrate climate change measures into national policies, strategies and planning
13.3  Improve education, awareness-raising and human and institutional capacity on climate change mitigation, adaptation, impact reduction and early warning
13.a  Implement the commitment undertaken by developed-country parties to the United Nations Framework Convention on Climate Change to a goal of mobilizing jointly $100 billion annually by 2020 from all sources to address the needs of developing countries in the context of meaningful mitigation actions and transparency on implementation and fully operationalize the Green Climate Fund through its capitalization as soon as possible
13.b  Promote mechanisms for raising capacity for effective climate change-related planning and management in least developed countries and small island developing States, including focusing on women, youth and local and marginalized communities
```
