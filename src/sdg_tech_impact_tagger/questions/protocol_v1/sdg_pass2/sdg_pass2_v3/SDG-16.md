# SDG pass 2, protocol v1: SDG 16, Peace, Justice and Strong Institutions

What the SDG pass 2 question (`../sdg_pass2_v3.md`) tells the model about
this goal. GOAL_SCOPE fills `{scope}`: the official title of the goal and,
for some goals, a guidance paragraph. GOAL_TARGETS fills `{targets}`: the
targets of the goal, one per line, as the target id, two spaces and the
target's title. Neither block holds a brace.

This goal has no guidance: GOAL_SCOPE holds the official title only.

The official title and the target titles are the `title` fields of the UN
Statistics Division SDG API (https://unstats.un.org/sdgapi), downloaded on
2026-10-08, with runs of whitespace collapsed to one space.

First run in `open_alex_adt_gate`. Status: frozen, protocol v1 (2026-10-08),
revision 3. The goal's id has the prefix `sdggoal-16` and is listed in
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
Official title: Promote peaceful and inclusive societies for sustainable development, provide access to justice for all and build effective, accountable and inclusive institutions at all levels
```

## GOAL_TARGETS

```text
16.1  Significantly reduce all forms of violence and related death rates everywhere
16.2  End abuse, exploitation, trafficking and all forms of violence against and torture of children
16.3  Promote the rule of law at the national and international levels and ensure equal access to justice for all
16.4  By 2030, significantly reduce illicit financial and arms flows, strengthen the recovery and return of stolen assets and combat all forms of organized crime
16.5  Substantially reduce corruption and bribery in all their forms
16.6  Develop effective, accountable and transparent institutions at all levels
16.7  Ensure responsive, inclusive, participatory and representative decision-making at all levels
16.8  Broaden and strengthen the participation of developing countries in the institutions of global governance
16.9  By 2030, provide legal identity for all, including birth registration
16.10  Ensure public access to information and protect fundamental freedoms, in accordance with national legislation and international agreements
16.a  Strengthen relevant national institutions, including through international cooperation, for building capacity at all levels, in particular in developing countries, to prevent violence and combat terrorism and crime
16.b  Promote and enforce non-discriminatory laws and policies for sustainable development
```
