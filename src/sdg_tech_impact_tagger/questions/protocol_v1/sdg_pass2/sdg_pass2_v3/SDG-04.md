# SDG pass 2, protocol v1: SDG 4, Quality Education

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
revision 3. The goal's id has the prefix `sdggoal-04` and is listed in
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
Official title: Ensure inclusive and equitable quality education and promote lifelong learning opportunities for all
```

## GOAL_TARGETS

```text
4.1  By 2030, ensure that all girls and boys complete free, equitable and quality primary and secondary education leading to relevant and effective learning outcomes
4.2  By 2030, ensure that all girls and boys have access to quality early childhood development, care and pre-primary education so that they are ready for primary education
4.3  By 2030, ensure equal access for all women and men to affordable and quality technical, vocational and tertiary education, including university
4.4  By 2030, substantially increase the number of youth and adults who have relevant skills, including technical and vocational skills, for employment, decent jobs and entrepreneurship
4.5  By 2030, eliminate gender disparities in education and ensure equal access to all levels of education and vocational training for the vulnerable, including persons with disabilities, indigenous peoples and children in vulnerable situations
4.6  By 2030, ensure that all youth and a substantial proportion of adults, both men and women, achieve literacy and numeracy
4.7  By 2030, ensure that all learners acquire the knowledge and skills needed to promote sustainable development, including, among others, through education for sustainable development and sustainable lifestyles, human rights, gender equality, promotion of a culture of peace and non-violence, global citizenship and appreciation of cultural diversity and of culture's contribution to sustainable development
4.a  Build and upgrade education facilities that are child, disability and gender sensitive and provide safe, non-violent, inclusive and effective learning environments for all
4.b  By 2020, substantially expand globally the number of scholarships available to developing countries, in particular least developed countries, small island developing States and African countries, for enrolment in higher education, including vocational training and information and communications technology, technical, engineering and scientific programmes, in developed countries and other developing countries
4.c  By 2030, substantially increase the supply of qualified teachers, including through international cooperation for teacher training in developing countries, especially least developed countries and small island developing States
```
