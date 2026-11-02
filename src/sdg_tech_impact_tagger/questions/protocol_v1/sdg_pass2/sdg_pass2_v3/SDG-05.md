# SDG pass 2, protocol v1: SDG 5, Gender Equality

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
revision 3. The goal's id has the prefix `sdggoal-05` and is listed in
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
Official title: Achieve gender equality and empower all women and girls
```

## GOAL_TARGETS

```text
5.1  End all forms of discrimination against all women and girls everywhere
5.2  Eliminate all forms of violence against all women and girls in the public and private spheres, including trafficking and sexual and other types of exploitation
5.3  Eliminate all harmful practices, such as child, early and forced marriage and female genital mutilation
5.4  Recognize and value unpaid care and domestic work through the provision of public services, infrastructure and social protection policies and the promotion of shared responsibility within the household and the family as nationally appropriate
5.5  Ensure women's full and effective participation and equal opportunities for leadership at all levels of decision-making in political, economic and public life
5.6  Ensure universal access to sexual and reproductive health and reproductive rights as agreed in accordance with the Programme of Action of the International Conference on Population and Development and the Beijing Platform for Action and the outcome documents of their review conferences
5.a  Undertake reforms to give women equal rights to economic resources, as well as access to ownership and control over land and other forms of property, financial services, inheritance and natural resources, in accordance with national laws
5.b  Enhance the use of enabling technology, in particular information and communications technology, to promote the empowerment of women
5.c  Adopt and strengthen sound policies and enforceable legislation for the promotion of gender equality and the empowerment of all women and girls at all levels
```
