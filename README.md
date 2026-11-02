# sdg-tech-impact-tagger

[![PyPI](https://img.shields.io/pypi/v/sdg-tech-impact-tagger)](https://pypi.org/project/sdg-tech-impact-tagger/)
<!-- DOI badge, once the first release is on Zenodo:
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXXX)
-->

Label texts with an LLM behind any OpenAI-compatible endpoint: the UN Sustainable Development Goals (SDGs), advanced digital technologies (ADTs), the impact of a technology on a goal, or any other list of labels you write. Each question is a versioned set of prompt blocks identified by a hash, its prompt id. Questions are chained in a declarative workflow, one TOML file. Every call is cached with its raw answer, every row records the model the endpoint says answered, and a run can be rebuilt from its cache alone, without the network. The package ships the questions and workflows of earlier research runs, and rebuilds the tables of those runs row for row from their caches.

The companion package [sdg-tech-tagger-rs](https://github.com/KnuxV/sdg-tech-tagger-rs) tags the same SDGs and technologies by published keyword queries, with no LLM.

## Install

From PyPI, with Python 3.13 or later. The package is pure Python (it depends on httpx, Polars and Pydantic), so it installs on any platform.

```bash
pip install sdg-tech-impact-tagger     # or: uv add sdg-tech-impact-tagger
```

It imports as `sdg_tech_impact_tagger` and installs the command `sdg-tech-impact-tagger`. From a clone of the repository:

```bash
git clone https://github.com/KnuxV/sdg-tech-impact-tagger
cd sdg-tech-impact-tagger
uv sync            # or: pip install .
```

## Quick start

The texts are a parquet file (or, from Python, a Polars frame) with an `id` column and the text fields the questions read. The shipped questions read `title` and `abstract`:

```python
import polars as pl

works = pl.DataFrame(
    {
        "id": ["w1", "w2"],
        "title": [
            "Solar microgrids for rural health clinics",
            "A survey of graph algorithms",
        ],
        "abstract": [
            "We size solar and battery systems that keep vaccine fridges running.",
            "We compare shortest-path algorithms on sparse graphs.",
        ],
    }
)
works.write_parquet("works.parquet")
```

A workflow names its models and its passes. This one asks the shipped question `protocol_v1/sdg_pass1` (a score from 0 to 100 for each of the 17 goals, in one call per work) with one model. Save it as `workflow.toml`:

```toml
[run]
name = "quickstart"
texts = "works.parquet"

[models.mymodel]
endpoint = "https://llm.example.org/v1"   # any OpenAI-compatible base URL
api_key_env = "MY_LLM_KEY"                 # the variable that holds the key
model = "my-model-name"                    # the model name sent
seed = 42
reasoning = "off"
reasoning_style = "omit"

[[passes]]
id = "sdg_scores"
question = "protocol_v1/sdg_pass1"
models = ["mymodel"]
units = { rule = "all" }
```

`seed`, `reasoning` and `reasoning_style` are required. `reasoning_style` says how the endpoint is told to think or not: `omit` sends nothing, `enable_thinking` sends `chat_template_kwargs.enable_thinking` (as vLLM reads it), `reasoning_effort` sends `reasoning_effort`. The key is read from the environment, or from a `.env` file next to the workflow, and is never written anywhere.

Check the workflow before any call. `check` loads the questions, the lists and the texts, plans every pass, and prints the prompt id, the run id and the number of units of each (pass, model):

```bash
sdg-tech-impact-tagger check workflow.toml
# sdg_scores mymodel: prompt sdgp1-ca9ecbb1733d, run-5b3b976b89e8, 2 units, 1 chunks
```

Run it from the command:

```bash
export MY_LLM_KEY=...
sdg-tech-impact-tagger run workflow.toml
```

or from Python:

```python
import polars as pl
from sdg_tech_impact_tagger import load_workflow, run

workflow = load_workflow("workflow.toml")
results = run(workflow)  # or run(workflow, texts=works) with a Polars frame
for result in results:
    print(result.pass_id, result.model, result.output_written, result.output)

scores = pl.read_parquet(results[0].output)
print(
    scores.filter(pl.col("score") >= 0.25).select("id", "code", "score", "model_served")
)
```

`run(workflow, *, texts=None, replay=False, passes=None, models=None, limit=None, worker="main", reverse=False, combine_only=False, answer_models=None, transport=None)` returns one `RunResult` per (pass, model). `passes` and `models` restrict what is run, `limit` keeps the first works of the texts, `replay=True` makes no call and reads every answer from the cache, and `transport` takes an `httpx.MockTransport` to test a workflow without an endpoint. `load_workflow(path)` reads a file, `load_workflow(preset="protocol-v1")` a preset. The command has the same options (`--texts`, `--replay`, `--pass`, `--model`, `--limit`, `--output-dir`, `--cache-dir`). A run is resumable: it works in chunks, and several workers (`--worker NAME`, `--reverse`) can share one output directory.

What is written:

```
cache/<2 hex>/<key>.json                       one file per call: the request and the raw answer
runs/quickstart/sdg_scores/mymodel.parquet     the table of the pass for that model
runs/quickstart/sdg_scores/mymodel/            run.json, manifest.json, chunks/, calls/
runs/quickstart/workflow.json                  the resolved workflow
```

The table of this pass has one row per (work, goal): `id`, `code` (`SDG-01` to `SDG-17`), `repeat`, `model`, `model_served`, `system_fingerprint`, `prompt_id`, `run_id`, `score` (0 to 1), `tokens_in`, `tokens_out`, `parse_failure`. Every table and column is described in `docs/contract.md`, section 8.

To see exactly what a question sends, the `prompt` command prints every call of one unit, with each text field shown as `<title>`, `<abstract>`. `--a` and `--b` choose the labels, by default the first of each list:

```bash
sdg-tech-impact-tagger prompt protocol_v1/sdg_pass1
sdg-tech-impact-tagger prompt protocol_v1/sdg_pass2 --a SDG-07
sdg-tech-impact-tagger prompt impact/p3_2 --a IOT --b SDG-07
```

## Concepts

| word | meaning |
|---|---|
| **work** | one row of the input table: an id and its text fields. |
| **text** | what the model reads about one work, as named fields of the input table (`title`, `abstract`, an answer to a survey, a section of a full text). |
| **list** | a set of labels with, for each, an id, a name and any material a question shows about it (definition, boundaries, targets). The SDGs and the ADTs are lists; so are themes or harm types. |
| **unit** | one thing a question is asked about: a work, a (work, label) pair, or a (work, label, label) triple. |
| **question** | one prompt version: its template blocks, the lists it uses, its level (`work`, `work x list` or `work x list x list`), its readout, its letter set and its budgets. A question is identified by its **prompt id**, a hash of its blocks. |
| **readout** | how an answer is turned into a label: `score_json` (an integer 0 to 100 per label in a strict JSON schema, scaled to 0 to 1), `letter_logprob` (one token from a letter set, with probabilities from the top logprobs), `letter_text` (a letter written as text, after reasoning or not), `json_object` (a JSON reply with several fields per label). |
| **pass** | one question asked over a set of units with one or more models, resumable, writing one table per model. |
| **unit rule** | how a pass's units are chosen from the works and earlier passes: `all`, `threshold` (the labels an earlier score pass gave at least a given score), `cross` (the labels of two earlier passes crossed into triples), `file` (units read from a file). |
| **workflow** | passes chained by unit rules, written in one TOML file. |
| **preset** | a workflow shipped with the package. |

Every model's labels are kept. When a unit rule reads several models, it says how to combine them, `union` or `intersection`; there is no default.

## Shipped questions

| question | level | readout | status | prompt id |
|---|---|---|---|---|
| `protocol_v1/sdg_pass1` | work | `score_json`, 17 goals | record | `sdgp1-ca9ecbb1733d` |
| `protocol_v1/sdg_pass2` | work x list (goal) | `letter_logprob`, `Y` `N` | record | `sdgp2-dcccffcc8667+sdggoal-<nn>-<hash>`, one per goal |
| `protocol_v1/adt_pass1` | work | `score_json`, 6 technologies | record | `adtp1-eb4f16256516+adtdesc-e8f65488c44f` |
| `protocol_v1/adt_pass2` | work x list (technology) | `letter_logprob`, `N` `M` `T` `A` `E` | record | `adtp2-92e7027dcba2+adtdesc-<label>-<hash>+adtbound-<label>-<hash>`, one per technology |
| `impact/p3_2` | work x list x list (technology, goal) | `letter_text`, `Y` `N`, asked twice (beneficial, detrimental) | current | `p3.2-f72f01757eef` (also recorded as `p3.1-f72f01757eef`) |
| `impact/p2` | work x list x list (technology, goal) | `letter_logprob`, `Y` `N`, asked twice | record | `p2-ed1dd92de43c` |
| `impact/p2_reasoning` | work x list x list (technology, goal) | `letter_text`, `Y` `N`, asked twice | record | `p3-ed1dd92de43c` |
| `paper/adt_v1` | work | `letter_text`, a table of letters for the 6 technologies | experimental | `adt1-d95d2cfc8f17` |
| `paper/sdg_v1` | work | `letter_text`, a table of letters for the 17 goals | experimental | `sdg1-042b7b2c693f` |
| `paper/impact_v1` | work x list x list, one call per work | `json_object`, every triple of the work | experimental | `p3.2w-50ba3b728c25` |

The letters of `protocol_v1/adt_pass2` are `E` (external: the technology as it exists is what the work studies), `A` (artefact: the authors build or adapt it), `T` (tool: the authors use it to obtain a result about something else), `M` (mention: in the text, but nothing is done with it) and `N` (not in the text). Every per-label id is in `src/sdg_tech_impact_tagger/questions/IDS.tsv`.

**Status.** `current` is the question to use for new work. `record` is a question as it was frozen and run, kept so that its tables can be rebuilt and its id stays citable. `experimental` questions ship as they were run, so that their ids match the runs, with known faults: the codebook the `paper/` questions embed tells the model to answer with a single letter while the outer instruction asks for a table or a JSON object, and the SDG codebook speaks of a screening step that did not happen at this level. A shipped question is never edited; a changed question is a new question with a new name. The files are checked by `questions/SHA256SUMS`.

The shipped lists are `sdg` (`SDG-01` to `SDG-17`, the UN goal titles) and `adt` (`AI`, `IOT`, `COMPUTING_INFRASTRUCTURE`, `BLOCKCHAIN`, `ROBOTICS`, `ADDITIVE_MANUFACTURING`).

## Presets

| preset | what it runs | models as shipped |
|---|---|---|
| `protocol-v1` | SDG and ADT, each in two passes: pass 1 scores every label for every work (`score_json`), pass 2 asks a letter question (`letter_logprob`) on each (work, label) scored 0.25 or more | `qwen3` on the SDG passes, `gemma` on the ADT passes, reasoning off |
| `protocol-v1-impact` | the four passes of `protocol-v1` with both models on each, then `impact/p3_2` on the triples crossed from the technologies labelled `E`, `A`, `T` or `M` by either model and the goals labelled `Y` by either model | `qwen3` and `gemma` on the protocol passes; `coder` (reasoning on) and `gemma` with thinking on for the impact pass |
| `paper-v1` (experimental) | one call per work for the technologies (`paper/adt_v1`), one for the goals (`paper/sdg_v1`), then one for every triple of the work (`paper/impact_v1`) | `coder` and `gemma`, both with reasoning on |

The presets keep the endpoint (`https://conversation.ia.unistra.fr/api`, the LLM gateway of the University of Strasbourg), the key variable (`UNISTRA_API_KEY`) and the model aliases they were run with. To run one on your own endpoint, print it, edit the endpoint, `api_key_env` and model names for your own gateway, then check and run your copy:

```bash
sdg-tech-impact-tagger preset protocol-v1 > my-protocol.toml
# edit each [models.*] table: endpoint, api_key_env, model
sdg-tech-impact-tagger check my-protocol.toml --texts works.parquet
sdg-tech-impact-tagger run my-protocol.toml --texts works.parquet
```

No preset names a texts file: give it with `--texts` (or `texts=` from Python). Another model gives other answers, under the same prompt ids but another run id.

## Your own labels

A list is a TOML file. Every label has an `id`, a `name`, an optional `json_key` (the key the model answers with, by default the id) and any further string fields, the same for every label. For example, three themes of answers to a survey, `themes.toml`:

```toml
[list]
id = "theme"
name = "Themes of the survey answers"

[[labels]]
id = "COST"
name = "Cost"
definition = "The answer speaks of prices, fees or what something costs the respondent."

[[labels]]
id = "ACCESS"
name = "Access"
definition = "The answer speaks of distance, opening hours or how hard a service is to reach."

[[labels]]
id = "QUALITY"
name = "Quality"
definition = "The answer judges how good the service itself was."
```

A question is a directory holding a block file and a `question.toml`. Only the fenced `text` blocks under a `## NAME` heading count; prose around them is ignored. `themes_v1/themes.md`:

````markdown
# Survey themes, version 1

## SYSTEM

```text
You read one answer to a survey about a public service and say, for each theme below, whether the answer mentions it.

{themes}

For each theme, give "mentioned" as Y or N and "evidence" as a short phrase copied word for word from the answer, or an empty string when the answer is N.
```

## USER

```text
Answer: {answer}
```
````

`themes_v1/question.toml` says which list and text fields fill the placeholders, how the answer is read (here `json_object`, one object per theme, sent as a strict JSON schema), and how the prompt id is computed (here from the two blocks and the definitions of the list):

```toml
[question]
name = "survey/themes_v1"
level = "work"
readout = "json_object"
status = "current"
prompt_id = "themes-ec3093e9a623+themedef-37a27c2ccec1"

[lists]
a = "theme"

[text]
fields = ["answer"]

[blocks]
files = ["themes.md"]
system = "SYSTEM"
user = "USER"

[blocks.fill.system]
themes = "listing:themes"

[blocks.fill.user]
answer = "text:answer"

[material.definition]
list = "a"
list_field = "definition"

[listing.themes]
list = "a"
item = "{json_key}: {name}. {definition}"
sep = "\n"

[readout]
form = "label_object"
schema = true
schema_name = "survey_themes"

[[readout.fields]]
name = "mentioned"
type = "letter"
letters = ["Y", "N"]

[[readout.fields]]
name = "evidence"
type = "quote"

[budget]
max_tokens = 400

[id]
prefix = "themes"
blocks = ["SYSTEM", "USER"]

[[id.parts]]
per = "list"
prefix = "themedef"
material = ["definition"]
```

The prompt id is checked at load. For a new question, write any value first: `check` refuses it and prints the id it computed, which you copy into `prompt_id`. A later change to a block or a definition changes the id, and the question is refused until `prompt_id` says so.

The workflow adds the list under `[lists]` and points the pass at the directory with `question_dir`. Here the texts are a parquet file with the columns `id` and `answer`:

```toml
[run]
name = "survey"
texts = "answers.parquet"

[lists]
theme = "themes.toml"

[models.mymodel]
endpoint = "https://llm.example.org/v1"
api_key_env = "MY_LLM_KEY"
model = "my-model-name"
seed = 42
reasoning = "off"
reasoning_style = "omit"

[[passes]]
id = "themes"
question_dir = "themes_v1"
models = ["mymodel"]
units = { rule = "all" }
```

`sdg-tech-impact-tagger check survey.toml` and `sdg-tech-impact-tagger run survey.toml` work as in the quick start. The table has one row per (answer, theme), with the columns `mentioned`, `evidence`, `quotes_ok` (true when every non-empty quote field is found word for word in the text), `retried`, the tokens and `parse_failure`. The field types are `letter`, `string`, `quote`, `boolean`, `integer` and `number`.

The `prompt` command knows only the shipped lists. To see the calls of a question that uses a list of your own, render it from Python:

```python
from sdg_tech_impact_tagger import load_list, load_question

themes = load_list("themes.toml")
question = load_question("themes_v1", lists={"theme": themes})
[(system, user)] = question.render({"answer": "The fee went up again."})
print(system)
print(user)
```

From Python, a Pydantic model can define the answer for each label in place of `[[readout.fields]]`. Its JSON schema is sent, every item of the reply is validated against it, and each field becomes a column. Fields typed `Quote` are checked against the text:

```python
from typing import Literal

from pydantic import BaseModel
from sdg_tech_impact_tagger import Quote, load_workflow, run


class Theme(BaseModel):
    mentioned: Literal["Y", "N"]
    sure: bool
    evidence: Quote


results = run(load_workflow("survey.toml"), answer_models={"themes": Theme})
```

Each field must be required and typed as a string (a `Literal` of strings included), a boolean, an integer or a number.

## Reproducibility

- **The model that answered.** Every row records the name the endpoint reports for the model (`model_served`) and its `system_fingerprint` when given, beside the name sent (`model`). A change during a run raises a warning and is counted in the manifest. A model entry may set `expect_model`; an answer from another model is then refused, not cached, and asked again later.
- **The cache keeps the raw answers.** Each call is one JSON file holding the request and the raw response, under a key that hashes the request (model, system and user messages, seed, temperature, budget, response format, extra body). The key leaves out the endpoint: keep one cache directory per endpoint. It is the key the earlier research code used, so the earlier caches are read in place, unchanged.
- **Replay.** `run(..., replay=True)` or `run --replay` rebuilds a pass from its cache alone: no key is read, no request is made, and a call missing from the cache stops the pass with `CacheMiss`. Everything else (units, chunks, budget retries, combining) is as in a live run.
- **The manifest.** Each (pass, model) writes `manifest.json`: the package and Python versions, the sha256 of the workflow, of every file the question read and of every list, the prompt id and run id, the resolved model entry (the name of the key variable, never its value), the endpoint, the budgets and settings, the sha256 of the texts, the unit rule and its sources, the counts (units, rows, parse failures, retries, calls from the cache and fresh, tokens) and the models served. `run.json` records what a run is; resuming it with other settings, texts or units is refused.

**Replay of the earlier runs.** The tables of three earlier research repositories were rebuilt with this package from their own caches, read in place, and from the documents file each run read, in its order: `wos_paper_sample` (protocol v1, the impact question and the paper-level labels), the recall sample of `open_alex_adt_gate` (protocol v1) and `divergence-validation` (`impact/p2` and `impact/p2_reasoning`). Compared column by column (labels, scores, probabilities to 1e-12, source scores, flags, retries, tokens, parse failures, model, prompt id), 22 of the 25 tables are identical and the other 3 differ on 2 rows each, in the count of output tokens only (below). No row is on one side only and no call missed the cache.

| repository | table | model | rows, earlier and rebuilt |
|---|---|---|---|
| `wos_paper_sample` | `sdg_pass1` | qwen3 | 2,134,486 |
| | `sdg_pass1` | gemma | 2,134,486 |
| | `sdg_pass2` | qwen3 | 386,784 |
| | `sdg_pass2` | gemma | 426,345 |
| | `adt_pass1` | gemma | 753,348 |
| | `adt_pass1` | qwen3 | 753,348 |
| | `adt_pass2` | gemma | 163,255 |
| | `adt_pass2` | qwen3 | 130,115 |
| | `impact_p3_2` | coder | 307,231 |
| | `impact_p3_2` | gemma | 307,231 |
| | `paper_adt` | coder | 753,348 |
| | `paper_sdg` | coder | 2,134,486 |
| `open_alex_adt_gate`, recall sample | `sdg_pass1` | qwen3 | 5,100,017 |
| | `sdg_pass1` | gemma | 5,100,017 |
| | `sdg_pass2` | qwen3 | 526,799 |
| | `sdg_pass2` | gemma | 587,207 |
| | `adt_pass1` | qwen3 | 1,800,006 |
| | `adt_pass1` | gemma | 1,800,006 |
| | `adt_pass2` | qwen3 | 39,941 |
| | `adt_pass2` | gemma | 61,949 |
| `divergence-validation` | `impact/p2` | gemma | 51,044 |
| | `impact/p2` | mistral-small | 51,044 |
| | `impact/p2_reasoning` | coder | 51,044 (2 differ in `tokens_out`) |
| | `impact/p2_reasoning` | gemma | 51,044 (2 differ in `tokens_out`) |
| | `impact/p2_reasoning` | gpt-oss | 51,044 (2 differ in `tokens_out`) |

The impact pass read its budget retries from the cache too (53 for coder, 4,184 rows with a retry for gemma). The sha256 of the texts and of the units of every rebuilt run equal those the earlier runs recorded.

The 6 rows that differ come from two works of `divergence-validation` with the same title and abstract and the same triple: their requests are identical, so they share one cache key. The earlier client asked both at once and kept each answer in its row, while the cache file kept only the last; a replay reads that one answer for both. Their labels agree; only `tokens_out` differs.

Not replayed:

- the paper-level impact tables of `wos_paper_sample`: they are built from the paper-level labels of both models, and gemma's paper-level label tables were not on the machine where the replay was run;
- by design, the `gpt-oss` rows of the single-token layer of `divergence-validation` (51,044), which read a letter's logprob after reasoning: the package refuses `letter_logprob` with reasoning on, since a thinking model's first token is not its answer.

## Credits and licences

<!-- Once on Zenodo: Cite this package as: Michoud, K. sdg-tech-impact-tagger. Zenodo. <https://doi.org/10.5281/zenodo.XXXXXXXX> -->
`CITATION.cff` gives the citation of this package and of its sources in machine-readable form. `CREDITS.md` lists every source with its licence, and `LICENSE-DATA.md` says which licence covers which file.

- Code: GNU GPL version 3 only (GPL-3.0-only, `LICENSE`).
- The questions and lists shipped in the package (prompt files, label definitions, boundary rules): CC BY 4.0.
- Text quoted from elsewhere keeps its source's terms and is credited: the official titles and targets of the Sustainable Development Goals (United Nations, General Assembly resolution A/RES/70/1 and the global indicator framework), and the target lists exported from the Aurora SDG queries v5.0 (Vanderfeesten, Otten and Spielberg, Aurora Universities Network, CC BY 4.0, <https://doi.org/10.5281/zenodo.3817445>).
- The definitions of the six technologies follow, in paraphrase, public definitions (OECD, the EU AI Act, ITU-T, ISO, NIST, UNCTAD) listed in `CREDITS.md`.

## How AI was used

<!-- Kevin writes this section. -->
