# Decisions

Each entry is a decision about what the package does. Entries are appended,
never edited; a decision that changes gets a new entry that says so.

## D001  The package and its oracle (2026-11-02, Kevin)

The labelling code of three earlier research repositories becomes one
package, `sdg-tech-impact-tagger`: `open_alex_adt_gate`, `wos_paper_sample`
and `divergence-validation` (a fourth, older generation was read for features:
`SDG_ADT_MAVERICK`, `open_question_classification`, `full_text_analysis`).
The first two carry the same client byte for byte; the third a copy that
drifted. The earlier runs are the oracle: given their cached raw answers, the
package must rebuild their tables row for row (replay). Names: distribution
`sdg-tech-impact-tagger`, import `sdg_tech_impact_tagger`, command
`sdg-tech-impact-tagger`. Python 3.13 or later, Polars, httpx, pure Python.

## D002  Public from the start (2026-11-02, Kevin)

The repository and the package are public from the first release, prompts
included.

## D003  Licences (2026-11-02, Kevin)

Code under GPL-3.0-only, as sdg-tech-tagger-rs. The questions and lists
written for the earlier research (prompt files, definitions, boundaries)
under CC BY 4.0. Text taken from elsewhere keeps its source's terms and is
credited in `CREDITS.md`: the official SDG goal and target texts (United
Nations), and the target lists as exported from the Aurora SDG queries v5.0
(CC BY 4.0, doi:10.5281/zenodo.3817445).

## D004  Any list of labels (2026-11-02, Kevin)

The package is not tied to SDGs and ADTs. A list is a file of ids, names and
definitions; from it the package builds the JSON schema of an answer that
covers every label. A new prompt file changes the framing. From Python, a
Pydantic model can define an answer with richer fields, and every answer is
validated against it. The package ships the SDG and ADT lists.

## D005  Any named text fields (2026-11-02, Kevin)

The input is a table with an id column and any text columns. Each question's
template names the fields it uses. The shipped questions use `title` and
`abstract`. The package extracts no sections and filters no works: what
reaches it is what the caller chose to label.

## D006  Four readouts (2026-11-02, follows from D009)

`score_json` (an integer 0 to 100 per label in a strict JSON schema, scaled
to [0, 1]), `letter_logprob` (one generated token from a letter set, with
probabilities from the top logprobs), `letter_text` (a letter written after
reasoning, no probability), `json_object` (a JSON reply with several fields
per label). The three presets of D009 use all four. A question with
`letter_logprob` is refused with reasoning on, since a thinking model's first
token is not its answer.

## D007  Probabilities sum every spelling of a letter (2026-11-02, Kevin)

In `letter_logprob`, the probability of a letter sums `exp(logprob)` over
every top-logprob token whose stripped form is the letter (`"Y"` and `" Y"`),
then renormalises over the letter set, as the client of `open_alex_adt_gate`
does. The exact-token reading of `divergence-validation` is an option,
`spelling = "exact"`, to reproduce its tables.

## D008  Impact question (2026-11-02, Kevin)

The current impact question is P3.2 of `wos_paper_sample`
(`impact_p3_2.md` with `impact_sdg_targets.json`). P2 of
`divergence-validation`, its only frozen impact prompt, ships as a record
under its own name.

## D009  Presets (2026-11-02, Kevin)

Three workflows ship as presets:

1. Protocol v1: SDG and ADT, pass 1 (scores) and pass 2 (letters) on the
   pairs at or above 0.25, as frozen in `open_alex_adt_gate`.
2. Impact at the triple level: P3.2 on the triples crossed from the ADT
   pass 2 labels E, A, T, M and the SDG pass 2 label Y.
3. Paper level: one call per work for the ADTs, one for the SDGs, one for
   every triple of the work, as run in `wos_paper_sample`. Marked
   experimental. Its prompts ship as they were run, so their ids match the
   runs, and their known faults are documented: the codebook they embed
   tells the model to answer with a single letter while the outer
   instruction asks for a table or a JSON object, and the SDG codebook
   speaks of a screening step that did not happen at this level.

## D010  OpenAI-compatible endpoints only, in version 1 (2026-11-02, Kevin)

The client speaks the OpenAI chat completions API (Unistra, vLLM, OpenAI,
Groq, OpenRouter, LiteLLM). The native Anthropic API and batch APIs come in
a later version.

## D011  No default combination of models (2026-11-02, Kevin)

Every model's labels are kept, each unit flagged by the sources that gave it.
A unit rule that reads several models names `union` or `intersection`; there
is no default.

## D012  The model that answered is recorded (2026-11-02, Kevin)

Every row records the model name the endpoint reports and its
`system_fingerprint` when given. A change during a run is warned about. A
model entry may set `expect_model`; an answer from another model is then
refused, not cached, and asked again later.

## D013  The cache key is kept (2026-11-02, Kevin)

The cache key is the one the earlier clients use, so their caches replay
unchanged: sha256 of the canonical JSON of the request fields (model, system,
user, seed, temperature, max_tokens, top_logprobs or response_format,
extra_body, and `kind` for chat calls). It leaves out the endpoint, which is
recorded in the run manifest; one cache directory per endpoint is advised.

## D014  No command-line harnesses (2026-11-02, Kevin)

Annotation through `claude -p` or `codex exec` stays out of the package.
Their outputs can feed a workflow as a file of units.

## D015  The workflow file (2026-11-02)

A workflow is a TOML file loaded into a strict model that refuses unknown
keys, with questions in their own files. TOML rather than YAML because YAML
1.1 reads unquoted `yes` and `no` as booleans. Passes are chained by a closed
set of unit rules implemented in Python (`all`, `threshold`, `cross`,
`file`), never by expressions written in the file.

## D016  The contract's own choices (2026-11-02)

`docs/contract.md` section 12 lists 54 choices the contract makes beyond
D001 to D015, each with its alternative. They are accepted as written,
except 49 and 53, settled by D017 and D018. None changes what an earlier
run returns; replay settings (`spelling`, `budget_rule`, `null_text`,
`prompt_prefix`) exist so that the earlier tables can be rebuilt.

## D017  The reasoning layer of divergence-validation ships (2026-11-02, Kevin)

`impact/p2_reasoning` ships beside `impact/p2`: the same blocks, read by
`letter_text`, prefix `p3`, so the reasoning-layer tables of
`divergence-validation` replay. Its `gpt-oss` rows of the single-token
layer, a letter's logprob read after reasoning, are not reproducible: D006
stays as written.

## D018  Preset models (2026-11-02, Kevin)

`protocol-v1` uses the models as frozen: qwen3 for SDG, gemma for ADT.
`protocol-v1-impact` runs both models on every protocol pass, then P3.2, as
in `wos_paper_sample`.

## D019  Clarifications of the contract (2026-11-02)

The test-writing session journalled 19 places where the contract was silent
or ambiguous. Section 13 of `docs/contract.md` answers each, by the simplest
rule consistent with the earlier code. Three answers correct the paper-v1
preset to what `wos_paper_sample` ran: `coder` sends no thinking flag
(style `omit`), the `length` budget rule applies to the three paper passes,
and no preset names a texts file. No answer changes an earlier table.
