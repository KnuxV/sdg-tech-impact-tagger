# ADT pass 2, protocol v1: the template

The role question for the advanced digital technologies: one call per
(work, technology) unit that ADT pass 1 scored at or above the threshold
(0.25 in protocol v1), answered with one letter: E external, A artefact, T
tool, M mention, N not this technology. The technology's name and definition
come from `adt_descriptions_v3.md`, its boundary rules from
`adt_boundaries_v4.md`.

First run in `open_alex_adt_gate`. Status: frozen, protocol v1 (2026-10-08),
version 4 of the wording. Template id `adtp2-92e7027dcba2`, over
SYSTEM_ADT_PASS2, ROLE_RULES then USER_ADT_PASS2. A unit's prompt id is
`<template id>+<description id>+<boundary id>`, the last two hashed over the
technology's own block of each file.

Placeholders: SYSTEM_ADT_PASS2 takes `{role_rules}`, filled with the
ROLE_RULES block as it stands. ROLE_RULES takes none, and a brace in it
reaches the model as written. USER_ADT_PASS2 takes `{title}`,
`{abstract}`, `{technology}`, `{definition}` and `{boundaries}`.
Literal braces in SYSTEM_ADT_PASS2 and USER_ADT_PASS2 are doubled, because
those blocks are filled with `str.format`.

Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), see
`LICENSE-DATA.md`.

Only the fenced `text` blocks under the `## NAME` headings below count
toward the prompt id; this header does not. The blocks are byte for byte
those of the earlier runs and are never edited: a changed wording is a new
question under a new name.

## SYSTEM_ADT_PASS2

```text
You decide how a scholarly work, read through its title and abstract, relates to one advanced digital technology.

First decide whether the technology, as its definition and boundary rules describe it, is in the text at all. Then, if it is, decide the relation between the authors and the technology.

Answer with exactly one letter:

E  External. The technology as it exists in the world is what the work studies: its adoption, effects, costs, risks, performance, perception or governance, where the instance belongs to others.
A  Artefact. The authors build, propose, design or adapt the technology, or a system made from it, and offer it as their contribution.
T  Tool. The authors use the technology to obtain a result about something else.
M  Mention. The technology is in the text, but the authors do nothing with it and it is not what the work studies.
N  The technology is not in the text. It is neither named nor described, or the word means something else, or the text names only a broad label and no instance of the technology.

Rules that apply to every technology:

- Judge only from the title and the abstract as written. The abstract may be empty or may hold other text, such as a table of contents: judge what is there. A technology the text describes in its own terms without its usual name is in the text. A technology the text neither names nor describes is not, however likely: a statistical analysis was run on some computer, a survey was hosted on some website, and neither is evidence of anything.
- A broad label is not a technology. Industry 4.0 or 5.0, the fourth industrial revolution, Society 5.0, digital transformation, digitalisation, digital technologies, digital twin, smart manufacturing, intelligent manufacturing, digital manufacturing, smart city, smart farming, precision agriculture and metaverse are not evidence by themselves; judge the named technologies the text describes under them.
- A word or abbreviation used in another sense is not the technology, and the answer is N.
- A text can involve several technologies. Judge only the one you are asked about.

{role_rules}

Answer with a single letter: E, A, T, M or N. Output nothing else.
```

## ROLE_RULES

```text
How to choose between E, A, T and M once the technology is in the text:

- E applies when what the work says is about the technology as it exists in the world, deployed, adopted, sold, regulated or anticipated by others. A study of the effect of AI adoption on emissions, a survey of farmers' drone use, a test of an off-the-shelf chatbot and a policy framework for blockchain are E. If the authors built the instance, it is A, however thoroughly they evaluate it.
- A is what is offered. If the text presents the model, system, method or device as what the authors propose, develop or introduce, it is A, even when they also apply it to a domain problem. A system the authors plan or propose to build, in a protocol or project description, is also A. If they used an existing technology and the contribution is the finding about the domain, it is T. A system built for an environment ("a routing method designed for sensor networks") is A for the technology built, M for the environment.
- A built and then tested remains A, whether tested in a trial, a deployment or a simulation.
- T needs a signal. The text must show the authors doing something with the technology to get a result, in any voice: "we applied a random forest", "images were classified using a neural network", "processed in Google Earth Engine". Tuning a model, or comparing existing algorithms that the authors train or fit themselves for a result about the domain, is still T; testing a product or system deployed by others is E. A technology in the text without such a signal is M.
- M covers the rest: a fact about the technology, a comparison with it, the setting ("in the age of AI"), an intended application the authors name without building or using it ("a material for soft robotics", "suitable for 5G"), a platform or hardware named only as where something is hosted, stored or ran ("hosted on AWS", "trained on a GPU"), or future work named in passing.
- When the abstract is empty, the title is the text and is signal enough: a title presenting the technology as built, used or studied is A, T or E; it is M only when it names the technology as a setting or an intended application. A title that names neither the technology nor one of its methods is N, however likely the technology is behind its topic.
- Reviews of the literature: answer for the technology's role in the work reviewed. A review of models or methods that use the technology is T, or A when it surveys proposed architectures or techniques; a review of the technology's adoption, effects, costs or governance is E.
```

## USER_ADT_PASS2

```text
Title: {title}

Abstract: {abstract}

The technology is {technology}.

Definition: {definition}

Boundary rules for {technology}:
{boundaries}

How does this text relate to {technology}? E, A, T, M or N:
```
