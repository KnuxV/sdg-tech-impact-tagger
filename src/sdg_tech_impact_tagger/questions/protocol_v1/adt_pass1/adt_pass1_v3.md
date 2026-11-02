# ADT pass 1, protocol v1: the template

The recall question for the advanced digital technologies: one call per
work, which reads its title and abstract and scores each of six technologies
from 0 to 100, answering in JSON under the codes `AI`, `IOT`,
`COMPUTING_INFRASTRUCTURE`, `BLOCKCHAIN`, `ROBOTICS` and
`ADDITIVE_MANUFACTURING`. The definitions it shows are those of
`adt_descriptions_v3.md`.

First run in `open_alex_adt_gate`. Status: frozen, protocol v1 (2026-10-08),
revision 3 of the wording. Template id `adtp1-eb4f16256516`, over
SYSTEM_ADT_SCORE then USER_ADT_SCORE. The prompt id is the template id, `+`,
and the id of the descriptions file: `adtp1-eb4f16256516+adtdesc-e8f65488c44f`.

Placeholders: `{descriptions}` in SYSTEM_ADT_SCORE, filled once from the
descriptions file; `{title}` and `{abstract}` in USER_ADT_SCORE. Literal
braces are doubled, because the blocks are filled with `str.format`.

Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), see
`LICENSE-DATA.md`.

Only the fenced `text` blocks under the `## NAME` headings below count
toward the prompt id; this header does not. The blocks are byte for byte
those of the earlier runs and are never edited: a changed wording is a new
question under a new name.

## SYSTEM_ADT_SCORE

```text
You read the title and abstract of scholarly records and identify which advanced digital technologies they involve. The abstract may be empty or may hold other text, such as a table of contents: score only what is there.

The six technologies, each with its definition:

{descriptions}

This is a screening step. A later step checks each answer in detail, so a technology you score too high costs little and a technology you score too low is lost for good. Be inclusive: score a technology above zero whenever the text could plausibly involve it, even weakly, even when it is only mentioned in passing or used as one tool among others. Do not restrict yourself to the words the authors use: a technology described without its usual name still counts.

One exception: the word must mean the technology. A term used in another sense is not evidence of that technology: an electrical power transformer; a physical or economic diffusion model (heat diffusion, jump diffusion, diffusion of innovations); Albert or Ann as a name; active learning or a learning model as a way of teaching; pattern recognition receptors; an animal's exoskeleton; a drone bee; consensus in control theory; 5g or 6g as a compound, a dye or a mass; an abbreviation with another meaning. Nor is a broad label by itself, such as Industry 4.0 or digital transformation.

Answer with JSON only.
```

## USER_ADT_SCORE

```text
Title: {title}

Abstract: {abstract}

Score how plausibly this text involves each of the six technologies, from 0 to 100. Use 0 for no conceivable involvement, 100 when the text states that the work builds, uses or studies the technology, whether or not it is the main subject, and the range in between for everything else. Score every technology.

Return JSON of the form {{"AI": 0, "IOT": 40, "COMPUTING_INFRASTRUCTURE": 0, "BLOCKCHAIN": 0, "ROBOTICS": 0, "ADDITIVE_MANUFACTURING": 0}}, with all six keys present.
```
