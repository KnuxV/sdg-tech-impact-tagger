# SDG pass 2, protocol v1: SDG 15, Life on Land

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
revision 3. The goal's id has the prefix `sdggoal-15` and is listed in
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
Official title: Protect, restore and promote sustainable use of terrestrial ecosystems, sustainably manage forests, combat desertification, and halt and reverse land degradation and halt biodiversity loss
```

## GOAL_TARGETS

```text
15.1  By 2020, ensure the conservation, restoration and sustainable use of terrestrial and inland freshwater ecosystems and their services, in particular forests, wetlands, mountains and drylands, in line with obligations under international agreements
15.2  By 2020, promote the implementation of sustainable management of all types of forests, halt deforestation, restore degraded forests and substantially increase afforestation and reforestation globally
15.3  By 2030, combat desertification, restore degraded land and soil, including land affected by desertification, drought and floods, and strive to achieve a land degradation-neutral world
15.4  By 2030, ensure the conservation of mountain ecosystems, including their biodiversity, in order to enhance their capacity to provide benefits that are essential for sustainable development
15.5  Take urgent and significant action to reduce the degradation of natural habitats, halt the loss of biodiversity and, by 2020, protect and prevent the extinction of threatened species
15.6  Promote fair and equitable sharing of the benefits arising from the utilization of genetic resources and promote appropriate access to such resources, as internationally agreed
15.7  Take urgent action to end poaching and trafficking of protected species of flora and fauna and address both demand and supply of illegal wildlife products
15.8  By 2020, introduce measures to prevent the introduction and significantly reduce the impact of invasive alien species on land and water ecosystems and control or eradicate the priority species
15.9  By 2020, integrate ecosystem and biodiversity values into national and local planning, development processes, poverty reduction strategies and accounts
15.a  Mobilize and significantly increase financial resources from all sources to conserve and sustainably use biodiversity and ecosystems
15.b  Mobilize significant resources from all sources and at all levels to finance sustainable forest management and provide adequate incentives to developing countries to advance such management, including for conservation and reforestation
15.c  Enhance global support for efforts to combat poaching and trafficking of protected species, including by increasing the capacity of local communities to pursue sustainable livelihood opportunities
```
