# Paper level: impact, version 1, the preamble

One call per work for every triple of the work at once, under the impact
question P3.2. This file holds only the PREAMBLE block. It depends on P3.2
and its targets file (`../../impact/p3_2/impact_p3_2.md`,
`../../impact/p3_2/impact_sdg_targets.json`), which it does not repeat: the
system message is this block, a blank line, then the SYSTEM block of P3.2;
the user message gives the title and abstract once, then each goal with its
targets and, for each triple, the two questions of P3.2 numbered P1, P2 and
so on, and asks for one JSON object.

First run in `wos_paper_sample`, where a script generated it from the
annotation packet of that repository. Status: experimental. It ships as it
was run, so that its id matches the runs, with a known fault: the P3.2
codebook ends by telling the model to answer with a single character, while
this preamble asks for a JSON object.

Prompt id `p3.2w-50ba3b728c25`: the sha256 of this block, a newline, then
the id of P3.2, `p3.2-f72f01757eef`.

Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), see
`LICENSE-DATA.md`.

Only the fenced `text` blocks under the `## NAME` headings below count
toward the prompt id; this header does not. The blocks are byte for byte
those of the earlier runs and are never edited: a changed wording is a new
question under a new name.

## PREAMBLE

```text
You annotate one scholarly text, read through its title and abstract, for one or more pairs of a technology and a goal, following the codebook below.

For each pair you answer the two questions the message gives for it: the beneficial question (section 2 of the codebook) and the detrimental question (section 3). Answer each pair on its own, as if it were the only pair asked: the other pairs, their number and their order say nothing about it.

Reply with one JSON object and nothing else, with the single key "pairs": a list with one object per pair, in the order asked, each with exactly these keys:
- "pair": the pair's number as the message gives it (P1, P2, ...);
- "beneficial": "Y" or "N", the answer to the beneficial question;
- "beneficial_kind": "outcome" or "utility" when "beneficial" is "Y", the kind of claim of section 2 the answer rests on; "none" when it is "N";
- "beneficial_quote": when "beneficial" is "Y", the sentence that makes the claim, copied character for character from the title or abstract; "" when it is "N";
- "detrimental": "Y" or "N", the answer to the detrimental question;
- "detrimental_quote": when "detrimental" is "Y", the sentence that makes the claim, copied character for character; "" when it is "N".

=== THE CODEBOOK ===
```
