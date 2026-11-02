# Contract

What the package consumes and produces, exactly enough that the tests can be
written from this file alone and that the earlier runs can be replayed from
their caches, row for row. When this file and the code disagree, this file
decides. It rests on decisions D001 to D018; the choices it makes beyond
them are listed, one line each, in section 12, accepted by D016.

Earlier code is cited as `[OA]` (`open_alex_adt_gate`), `[WS]`
(`wos_paper_sample`) and `[DV]` (`divergence-validation`). A path without a
directory is under the repository's `src/<package>/`; `params.yaml`, `docs/`
and `scripts/` are at the repository root. `[OA]` and `[WS]` carry the same
`llm/client.py` and `llm_passes.py` (byte for byte, imports aside), so a
citation of one holds for the other.

Python names in this file (`str.format`, `str.strip`, `json.dumps`) mean the
CPython 3.13 behaviour of those functions; the package must reproduce it,
since prompt ids and cache keys depend on it.

## 1. Overview

A **workflow** (one TOML file, section 7) names **models**, and **passes**
in order. Each pass asks one **question** (a directory of prompt files and a
`question.toml`, section 3) with each of its models over a set of **units**
chosen by a **unit rule** (section 5). A question's **readout** (section 4)
turns each answer into rows. Every call goes through one client (section 6)
that caches the raw answer under a key compatible with the earlier caches,
so a pass can be rebuilt from a cache alone (**replay**). Each (pass, model)
writes one parquet table (section 8) and a run manifest (section 9).

## 2. Inputs

### 2.1 The texts table

A Polars `DataFrame` (from Python) or a parquet file (command line, or
`[run].texts`). One row per work.

| rule | behaviour | from |
|---|---|---|
| id column | named by `[run].id_column`, default `id`; dtype `String` | D005 |
| text fields | any other columns; a question names the fields it uses (`[text].fields`); each used field must exist, dtype `String` or `Null` | D005; [OA] `llm_passes.py:149-180` |
| other columns | ignored, never sent | [OA] `llm_passes.py:158-172` |
| null text | sent as the pass's `null_text` (section 7.3), default `""` | [OA] `llm_passes.py:181-185`; [WS] `impact_pass.py:293-294` |
| null or empty id | refused, `TextsError` giving the count | [OA] `llm_passes.py:186-188` |
| repeated id | refused, `TextsError` giving the number of repeated ids and the first in table order | [OA] `llm_passes.py:189-194` |
| empty text | kept and sent as it is; the package filters no work | D005; [OA] `llm_passes.py:163-164` |
| order | the table's row order is the order of the works everywhere below | [OA] `llm_passes.py:309-315` |

No truncation of any text. The output id column is always named `id`,
whatever `id_column` is.

Note on nulls in the earlier runs. The protocol passes of [OA] and [WS] read
the works through `llm_passes.stage_documents` or `run_sdg_pass1.documents`,
which turn a null title or abstract into `""` before any template is filled
([OA] `llm_passes.py:181-185`, `scripts/run_sdg_pass1.py:90-103`), so their
`title=doc["title"]` never formats `None`. [WS] impact and paper passes use
`or ""` ([WS] `impact_pass.py:293-294`, `paper_pass.py:160-161`). [DV]
formats `row["title"]` and `row["abstract"]` with no substitution
([DV] `stages/labels_p1.py:95-99`), so a null would have been sent as the
four characters `None`. `null_text = "None"` reproduces that.

### 2.2 Lists

A list is a TOML file. Shipped lists live in `src/sdg_tech_impact_tagger/lists/<id>.toml`
and are checked by `lists/SHA256SUMS`; a workflow may add its own
(`[lists]`, section 7.2).

```toml
[list]
id = "adt"                       # [a-z][a-z0-9_]*, unique among the lists of a workflow
name = "Advanced digital technologies"
source = "free text: where the material comes from"   # optional

[[labels]]
id = "AI"                        # [A-Za-z0-9_-]+, unique in the list
json_key = "AI"                  # optional, default id; unique; the key a JSON answer uses
name = "Artificial intelligence and big data analytics"
name_impact = "artificial intelligence"
# any further key: a string field (definition, boundaries, targets, another name)
```

| rule | behaviour |
|---|---|
| label order | the order of `[[labels]]` is the list's order: JSON schema `required`, rows of a table readout, `listing` fills, `all` units |
| fields | every value is a string; every label carries the same set of keys; `id`, `json_key`, `name` required |
| derived variable | `slug` = `id.lower().replace("_", "-")` ([OA] `adt_pass2.py:105-111`); not stored |
| refused (`ListError`) | unknown `[list]` key, missing or repeated `id` or `json_key`, a non-string value, labels with different key sets, a list id clashing with another list of the workflow |

Shipped lists, as the earlier runs named the labels:

| list | ids | `json_key` | `name` | other fields |
|---|---|---|---|---|
| `sdg` | `SDG-01` .. `SDG-17` ([OA] `detections.py:36`) | `SDG1` .. `SDG17` ([OA] `sdg_pass1.py:68-72`; [WS] `impact_pass.py:255-257`) | UN short title, `No Poverty` .. `Partnerships for the Goals` ([OA] `sdg_pass1.py:48-66`) | `number` (`01` .. `17`); `name_short` = `SDG <n>, <name>`, e.g. `SDG 13, Climate Action` ([OA] `sdg_pass2.py:95-104`); `name_impact`, e.g. `SDG 13, climate action` ([WS] `params.yaml:370-387`) |
| `adt` | `AI`, `IOT`, `COMPUTING_INFRASTRUCTURE`, `BLOCKCHAIN`, `ROBOTICS`, `ADDITIVE_MANUFACTURING`, in this order ([OA] `detections.py:40-55`) | the id | the first line of the label's block in `adt_descriptions_v3.md`, e.g. `Artificial intelligence and big data analytics` | `name_impact`: `artificial intelligence`, `the Internet of Things`, `computing infrastructure`, `blockchain`, `robotics`, `additive manufacturing` ([WS] `params.yaml:363-369`) |

How the earlier code named a label differs by question, and each shipped
question names the field it was run with (section 3.4, Appendix A):

| question | goal name | technology name |
|---|---|---|
| `protocol_v1/sdg_pass1` | written in the block itself | (none) |
| `protocol_v1/sdg_pass2` | `name_short` (`SDG 13, Climate Action`) | (none) |
| `protocol_v1/adt_pass1`, `adt_pass2` | (none) | the name line of the descriptions block (material `name`, section 3.3) |
| `impact/p3_2`, `impact/p2`, `paper/impact_v1` | `name_impact` (`SDG 13, climate action`) | `name_impact` (`the Internet of Things`) |
| `paper/adt_v1`, `paper/sdg_v1` | written in the block itself | written in the block itself |

Per-label material of the shipped questions (definitions, boundary rules,
goal scope and targets, the impact target lists) stays in the original files
inside each question directory, read as material (section 3.3), so that the
bytes the earlier ids hashed are the bytes read. A list field may serve as
material for a new question (D004).

## 3. Questions

### 3.1 Layout

`src/sdg_tech_impact_tagger/questions/<family>/<name>/` holds the prompt
files as imported (only their fenced blocks count) and `question.toml`. A
shipped question is never edited (AGENTS.md); every file under `questions/`
is in `questions/SHA256SUMS`. A workflow may use a question directory of its
own (`question_dir`, section 7.3) with the same layout.

Shipped: `protocol_v1/{sdg_pass1, sdg_pass2, adt_pass1, adt_pass2}`,
`impact/{p3_2, p2, p2_reasoning}`, `paper/{adt_v1, sdg_v1, impact_v1}`. Their
`question.toml` files are given in full in Appendix A.

### 3.2 Block files

A block is a line `## NAME`, optional spaces or tabs, one or more newlines,
a line ```` ```text ````, the body, then a line ```` ``` ```` (optional
trailing spaces or tabs). In Python: `re.compile(r"^## ([A-Za-z0-9_.-]+)[ \t]*\n+```text\n(.*?)\n```[ \t]*$", re.MULTILINE | re.DOTALL)`,
matches taken in order with `findall`. The body is taken verbatim (no
stripping). Text outside blocks is ignored. A file read by a question may not
hold two blocks of the same name (`QuestionError`).

This is the reader of [WS] `impact_pass.py:43-45` and `paper_pass.py:58-60`
with the name class widened. [OA] `llm/prompts.py:69-107` strips leading and
trailing newlines from a body and [DV] `stages/labels_p1.py:44-47` does not;
on every shipped file the three readers give the same bodies, and all 31
earlier ids of `questions/IDS.tsv` are reproduced by this reader (computed
for this contract with an independent script).

### 3.3 `question.toml`

Unknown keys are refused at every level (`QuestionError`).

| key | type | required | meaning |
|---|---|---|---|
| `[question].name` | string | yes | `<family>/<name>`; equals the directory's place for a shipped question |
| `[question].level` | `"work"`, `"work x list"`, `"work x list x list"` | yes | the shape of a unit |
| `[question].per_call` | `"unit"`, `"work"` | no, `"unit"` | one call per unit (per side), or one call per work holding all its units |
| `[question].readout` | `"score_json"`, `"letter_logprob"`, `"letter_text"`, `"json_object"` | yes | section 4 |
| `[question].fill` | `"format"`, `"replace"` | no, `"format"` | how placeholders are filled (3.4) |
| `[question].prompt_id` | string | one of the two | the expected id when it does not depend on the label |
| `[question].prompt_ids` | table code to string | one of the two | the expected id of every label of list `a`, when parts are per label |
| `[question].recorded_ids` | list of strings | no | other ids under which earlier runs recorded this question (only the prefix differs, 3.5) |
| `[question].status` | `"current"`, `"record"`, `"experimental"` | yes | shown in the manifest; D008, D009 |
| `[lists].a`, `[lists].b` | list id | by level and readout | `a` for `work x list` and for readouts that cover a list; `a` and `b` for `work x list x list` |
| `[text].fields` | list of field names | yes | the text fields the question uses, in this order (also the order of the joined text of a quote check, 4.4) |
| `[blocks].files` | list of paths | yes | files read for blocks, relative to the question directory; may reach a sibling question with `../../<family>/<name>/<file>`, never outside `questions/` |
| `[blocks].system`, `[blocks].user` | block name | yes | the system and user templates |
| `[blocks.fill.system]`, `[blocks.fill.user]` | table placeholder to source | yes (may be empty) | what fills each placeholder (3.4) |
| `[[sides]]` | array of `{name, block}` | no | two or more sides asked as separate calls; `name` `[a-z]+`; `block` the block filling `{question}` |
| `[blocks.fill.side]` | table placeholder to source | with sides | what fills the side block's placeholders |
| `[material.<name>]` | table | no | per-label text read from a file (below) |
| `[listing.<name>]` | table | no | a text rendered over a whole list (3.4) |
| `[assembly].kind` | `"impact_work_v1"` | only with `per_call = "work"` | the user message of a work-level call (3.4) |
| `[readout]` | table | yes | readout settings (section 4) |
| `[budget]` | table | yes | `max_tokens` (int >= 1), `retry_max_tokens` (int > `max_tokens`, optional), `top_logprobs` (int, `letter_logprob` only, default 20) |
| `[id]` | table | yes | the prompt id rule (3.5) |

Material, one entry per name, for the labels of list `a` or `b`:

| key | meaning | from |
|---|---|---|
| `list` | `"a"` or `"b"` | |
| `file` + `block` | a block file and a block name; both may hold `{id}`, `{json_key}`, `{slug}` or a list field, formatted per label | [OA] `adt_pass1.py:39-83`, `llm_passes.py:779-837` |
| `part` | `"whole"` (default), `"name"` (the first line), `"body"` (the lines after the first, which must be followed by one blank line; joined, then `strip("\n")`) | [OA] `adt_pass1.py:39-83` |
| `file` + `json_path` + `key` | a JSON file, the key holding a mapping, and the mapping key per label (a format string, e.g. `"{json_key}"`) | [WS] `impact_pass.py:255-257, 296` |
| `list_field` | instead of a file: the label's list field of that name | D004 |

Refused at load (`QuestionError`), carried over from [OA]
`adt_pass1.py:39-83`, `adt_pass2.py:70-102`: a block file read with
`block = "{id}"` holding a block whose name is not a label id of the list; a
missing block or key; an empty name line; a `body` with no blank line after
the name, or empty; a `whole` block that is empty or white space only.

### 3.4 Filling the templates

Sources a placeholder may name:

| source | value |
|---|---|
| `text:<field>` | the work's field, a null as the pass's `null_text` |
| `a:<field>`, `b:<field>` | the unit's label's list field (or `slug`, `id`, `json_key`) |
| `material:<name>` | the unit's label's material text |
| `block:<NAME>` | another block, verbatim ([OA] `adt_pass2.py:138-146`) |
| `listing:<name>` | `[listing.<name>]`: `list`, `item` (a format string over a label's fields, material and `id`), `sep`; the items of every label in list order joined by `sep` ([OA] `adt_pass1.py:86-97`) |
| `side` | the side's block filled with `[blocks.fill.side]` in the same fill mode ([WS] `impact_pass.py:287-297`) |

`fill = "format"`: the template is filled with one `str.format(**values)`
call holding every placeholder at once, so a value is never scanned for
braces ([OA] `sdg_pass2.py:165-172`; [WS] `impact_pass.py:292-298`). The
template's field names (`string.Formatter().parse`) must equal the keys of
its fill table exactly; a field with a conversion, a format spec, an index or
an attribute is refused ([OA] `llm_passes.py:798-804`). The [OA] SDG pass 2
filled its user block in two steps ([OA] `llm_passes.py:820-827`); with no
brace in a goal block (checked there, `:816-819`) one step gives the same
text.

`fill = "replace"`: for each placeholder in the order of the fill table,
`template = template.replace("{" + name + "}", value)`, each on the result of
the one before ([WS] `paper_pass.py:159-161`). Each `{name}` must occur in
the template.

`[assembly].kind = "impact_work_v1"` builds one work's call over all its
units of a `work x list x list` question ([WS] `paper_pass.py:327-384`,
`docs/paper-pass-contract.md:124-155`):

1. Order the work's units by (`a`, `b`); take the `b` labels in the order of
   their first appearance; under each, its `a` labels in that order. Number
   the units `P1`, `P2`, ... in that order.
2. System: the block `[assembly].preamble`, `"\n\n"`, the system block with
   trailing white space removed (`rstrip()`), `"\n"`.
3. Split the user block at its first `{question}` into head and tail; a tail
   that is not white space only is refused. For each `b` label in order, the
   head filled (`str.format`) with `[blocks.fill.user]` minus `question`;
   the first label's in full, every later one from the first occurrence of
   `[assembly].cut` (`"The goal is"`) on. After it, for each of its units,
   `"P<n>, beneficial: "` + the side `pos` filled, `"P<n>, detrimental: "` +
   the side `neg` filled, and `""`. Then `"Return the JSON object."`. The
   parts are joined with `"\n"`.

A question whose filled system or user text, or any material or listing it
uses, contains `[[OPEN` is refused before any call (`QuestionError`), as
[OA] `llm_passes.py:840-908, 1161-1167`.

### 3.5 Prompt id

`sha12(t)` = the first 12 hex characters of `sha256(t.encode("utf-8"))`.

```
head_text = "\n".join(body[name] for name in id.blocks)
if id.json:   head_text += "\n" + json.dumps(<id.json.file>[<id.json.path>], sort_keys=True, ensure_ascii=False)
if id.inner:  head_text += "\n" + <the prompt id of the question id.inner>
head = id.prefix + "-" + sha12(head_text)
for part in id.parts, in order:
    texts = [ "\n".join(material[m] for m in part.material) for each label ]
    per = "list":  part_id = part.prefix + "-" + sha12("\n".join(texts in list order))
    per = "label": part_id = part.prefix.format(**label) + "-" + sha12(text of the unit's label)
prompt_id = "+".join([head, *part_ids])
```

`json.dumps` here uses its default separators (`", "`, `": "`). Sources:
[OA] `llm/prompts.py:78-107`, `llm_passes.py:727-747, 811-836`,
`adt_pass2.py:114-135`; [WS] `impact_pass.py:83-102`, `paper_pass.py:146-149,
321-324`; [DV] `stages/labels_p1.py:51-69`. The prefix does not enter the
hash. With per-label parts, the prompt id of a row depends on its label of
list `a`.

At load, every computed id must equal `prompt_id` or `prompt_ids[code]`
(`QuestionError` naming both), as [WS] `impact_pass.py:403-407` and
`paper_pass.py:258-260` refuse a question whose id moved. A pass may set
`prompt_prefix` (7.3) to write rows under another prefix; the resulting id
must then be one of `recorded_ids`. This reproduces `p3.1-f72f01757eef`, the
id the [WS] test run of the impact question was recorded under before the
prefix was a setting ([WS] `params.yaml:419-426`).

### 3.6 Run id

The prompt id identifies the text, not the settings ([DV] gave the same text
read two ways the ids `p2-ed1dd92de43c` and `p3-ed1dd92de43c`). Every row
also carries

```
run_id = "run-" + sha12(json.dumps({
    "prompt_ids": {code: id} (or {"": id}), "readout": ..., "model": <name sent>,
    "seed": ..., "temperature": ..., "max_tokens": ..., "retry_max_tokens": ... or None,
    "top_logprobs": ... or None, "response_format": ... or None,
    "extra_body": <keyed extra body, 6.3>, "reasoning": "off" | "on",
    "spelling": ... or None, "extraction": ... or None, "null_text": ...,
}, sort_keys=True, separators=(",", ":")))
```

computed per (pass, model). The endpoint is not in it (recorded in the
manifest, as for the cache key, D013).

## 4. Readouts

### 4.1 What every readout shares

**Kind of call.** Fixed by the readout, so that keys match the earlier
caches:

| readout | layout | cache kind | wire body before `extra_body` | keyed extra body adds |
|---|---|---|---|---|
| `score_json` | | `chat` | `model`, `messages`, `temperature`, `max_tokens`, `seed`, `response_format` | nothing |
| `json_object` | | `chat` | as `score_json`; `response_format` only when the question has a schema (4.5) | `"logprobs": false` |
| `letter_logprob` | | `single_token` | `model`, `messages`, `temperature`, `max_tokens`, `seed`, `"logprobs": true`, `top_logprobs` | nothing |
| `letter_text` | `single` | `single_token` | as `letter_logprob`, `top_logprobs` 0 | `"logprobs": false` |
| `letter_text` | `table` | `chat` | as `json_object`, no `response_format` | `"logprobs": false` |

`messages` is `[{"role": "system", "content": system}, {"role": "user", "content": user}]`.
Sources: [OA] `llm/client.py:81-136, 424-456`; [WS] `params.yaml:395-413,
510-552` (the `logprobs: false` the impact and paper runs sent in
`extra_body`).

**Reading a body.** As [OA] `llm/client.py:188-221, 533-552`: the body is
validated against lenient models (`choices[].message.content` string or
null; `choices[].logprobs.content[]` entries `{token = "", logprob = 0.0,
top_logprobs = [{token, logprob}]}`; `choices[].finish_reason`;
`usage.prompt_tokens`, `usage.completion_tokens`, default 0). A body that
does not fit, including `{"unparseable_body": ...}`, reads as an empty
answer: no content, no logprobs, `finish_reason` `""`, tokens 0. Only the
first choice is read. `tokens_in`, `tokens_out` are the usage counts. The
content is `message.content`, `""` when null (chat kind).

**Model served.** `body["model"]` and `body["system_fingerprint"]` when they
are strings, else null (D012).

**OTHER.** The label of an unreadable answer is the string `OTHER`.

### 4.2 `score_json`

Level `work`, `per_call = "unit"`, one list `a`; rows (work, label) for every
label of `a` ([OA] `sdg_pass1.py:183-209`, `adt_pass1.py:154-228`).

Request: `response_format` =

```json
{"type": "json_schema", "json_schema": {"name": <readout.schema_name>, "strict": true,
  "schema": {"type": "object", "properties": {<json_key>: {"type": "integer"}, ...},
             "required": [<json_key> in list order], "additionalProperties": false}}}
```

no `minimum` or `maximum` ([OA] `sdg_pass1.py:97-121`, `adt_pass1.py:100-120`).

Reading ([OA] `sdg_pass1.py:151-180, 280-297`, `adt_pass1.py:123-151, 205-227`):
`json.loads(content)` must give an object; every key must be a `json_key` of
the list; every value an `int` or `float` and not a `bool`; every `json_key`
present. Then `score = min(1.0, max(0.0, int(value) / 100.0))` (`int`
truncates toward zero). Anything else, including a value `int` cannot take
(NaN, infinity), is unreadable: every label gets `score` 0.0 and
`parse_failure` true; no row is dropped. No budget retry.

### 4.3 `letter_logprob`

Refused with `reasoning = "on"` (D006), at workflow load (`WorkflowError`).

Settings: `[readout].letters` (list of distinct strings matching
`[A-Za-z0-9]+`, distinct once lower-cased), `[budget].max_tokens` (default 1)
and `top_logprobs` (default 20). The pass sets `spelling` (`"sum"` default,
`"exact"`), the model sets `extraction` (`"first_token"` default,
`"final_channel"`).

Reading ([OA] `llm/client.py:554-638`; [DV] `llm/client.py:465-520`):

1. Answer entry: `first_token` takes the first entry of
   `choices[0].logprobs.content`; `final_channel` the entry right after the
   last entry whose `token` is `<|message|>`, none when there is no marker or
   it is last.
2. `top` = a dict built from the entry's `top_logprobs` in order
   (`{t.token: t.logprob}`: a repeated token keeps its first position and its
   last value); empty without an entry.
3. `raw` = `message.content` when it is not null, else the entry's `token`
   (`""` without an entry). `label = raw.strip()` if it is one of the
   letters, else `OTHER`.
4. Mass of a letter. `sum`: `sum(math.exp(v) for k, v in top.items() if k.strip() == letter)`.
   `exact`: `math.exp(top[letter])` if `letter in top` else `0.0`.
5. `total = sum(mass[l] for l in letters)` (in letter order, Python `sum`).
   `p_<l>` = `mass[l] / total` for each letter; every `p_<l>` null when
   `total == 0.0`.

Under `Y`, `N` this gives the earlier `p_yes` bit for bit: [OA]
`client.py:603-612` (sum) and [DV] `client.py:498-508` (exact), with 1.0 or
0.0 when one letter alone is present. `parse_failure` is `label == "OTHER"`
only; a null probability is not folded in ([OA] `sdg_pass2.py:194`,
`adt_pass2.py:198-203, 283`). No budget retry.

### 4.4 `letter_text`

A letter written as text, no probability. `[readout].letters` as in 4.3;
`[readout].layout` `"single"` (default) or `"table"`.

`single` ([WS] `impact_pass.py:260-366`; [DV] `stages/labels_p3.py`): the
label is read as in 4.3 step 3 (content stripped, a letter or `OTHER`); no
logprob is asked.

`table` (level `work`, list `a`, [WS] `paper_pass.py:174-232`), with
`[readout].table` the table name (`ADT`, `SDG`): read the content line by
line; strip each line of white space, then of backticks at both ends, then
of white space; a line matching `^=== ([A-Za-z0-9_]+) ===$` opens that table
and closes any other; inside the question's table, split a line on
`[\s|]+` and drop empty cells; a line whose first cell is `1` is the work
line. Readable when the table was seen, holds exactly one work line, and that
line has exactly one letter per label of `a`, each in the letter set; the
letters go to the labels in list order. Unreadable: every label `OTHER`,
`parse_failure` true.

**Budget retry**, for `letter_text` and `json_object` when
`retry_max_tokens` is set. After a sub-chunk's calls, every call that is
unreadable and **spent** is asked once more, in one batch, the request
unchanged but `max_tokens = retry_max_tokens`; its answer replaces the first
(tokens, model served and fingerprint included) and the row's `retried` is
true. Never more than once. Spent, by the pass's `budget_rule`:

| `budget_rule` | spent when | reproduces |
|---|---|---|
| `"spent"` (default) | `finish_reason == "length"` or `tokens_out >= max_tokens` | new runs |
| `"tokens"` | `tokens_out >= max_tokens` (`max_tokens > 1` always holds here) | [WS] `impact_pass.py:309-311`; [DV] `stages/labels_p3.py:65-67` |
| `"length"` | `finish_reason == "length"` | [WS] `paper_pass.py:105-126` |

For a single-letter answer, unreadable is `label == "OTHER"`; for a table or
a JSON object, the reply cannot be read. A call that the default rule would
retry and the earlier rule did not is a cache miss on replay; the replay
workflows of section 8.4 therefore name the earlier rule.

### 4.5 `json_object`

`[readout].form` is `"label_object"` (new, D004) or `"impact_pairs_v1"`
([WS] paper impact).

**`label_object`**, level `work`, list `a`, rows (work, label). The reply is
one object with one key per `json_key`, each holding an object of the
fields declared in `[[readout.fields]]` (`name`, `type`: `"letter"` with
`letters`, `"string"`, `"quote"`, `"boolean"`, `"integer"`, `"number"`).
With `[readout].schema = true` the request carries

```json
{"type": "json_schema", "json_schema": {"name": <schema_name>, "strict": true, "schema":
  {"type": "object", "properties": {<json_key>: <item>, ...}, "required": [<json_key> in list order],
   "additionalProperties": false}}}
```

with `<item>` = `{"type": "object", "properties": {<field>: <type schema>},
"required": [fields in order], "additionalProperties": false}`, a letter
being `{"type": "string", "enum": [letters]}` and a quote a string. From
Python, an answer model (Pydantic, section 10) replaces the declared fields:
`<item>` is its `model_json_schema()` with `additionalProperties: false` and
every field required (an optional field is refused); each item is checked
with `model_validate`.

Reading: the text from the first `{` to the last `}` of the content
([WS] `paper_pass.py:389-395`), `json.loads`, an object whose keys are
exactly the `json_key`s, each item holding every field with its type. One
item that fails makes the whole reply unreadable: every label's field
columns null, `quotes_ok` null, `parse_failure` true. A quote field is
checked, never rejected: `quotes_ok` is true when every quote that is not
empty after `strip()` is a substring of the joined text, the question's
text fields in `[text].fields` order joined with `"\n"` (nulls as
`null_text`).

**`impact_pairs_v1`**, level `work x list x list`, `per_call = "work"`,
assembly `impact_work_v1`, rows per unit ([WS] `paper_pass.py:387-416,
516-551`). The reply text from its first `{` to its last `}` must load as an
object whose only key is `pairs`, a list whose `pair` values are exactly
`P1` .. `Pn` in order (n the work's units); each item holds `beneficial` and
`detrimental` in `Y`, `N`, and `beneficial_kind` `outcome` or `utility` when
`beneficial` is `Y`, `none` when `N`; other keys are allowed. Per unit:
`pos_label` = `beneficial`, `neg_label` = `detrimental`, `beneficial_kind`,
`quotes_ok` = every `Y` answer's `<beneficial|detrimental>_quote` is a string,
not empty after `strip()`, and a substring of the joined text. Unreadable:
every unit `OTHER`, `OTHER`, `beneficial_kind` null, `quotes_ok` false,
`parse_failure` true.

## 5. Unit rules

A pass's `units` table names one rule. Rules read **sources**: the output
table of an earlier pass for one model (`<output_dir>/<pass>/<model>.parquet`).
A pass may read only passes listed before it in the workflow.

| rule | keys | units | order |
|---|---|---|---|
| `all` | none | level `work`: every work; `work x list`: every work x every label of `a`; `work x list x list`: x every label of `b` | works in table order, labels in list order |
| `threshold` | `from`, `model`, `at_least`, `allow_unscored` (default false) | (work, code) whose score in the source is `>= at_least` | position of the work in the texts table, then `code` (string order) ([OA] `llm_passes.py:298-315`) |
| `cross` | `a`, `b` (sides), `agreed_first` (default false) | per work, the labels of side `a` present crossed with those of side `b` present | sorted by `id`, then `code`; with `agreed_first`, the units whose every flag is true first, each part so sorted ([WS] `impact_pass.py:172-206`) |
| `file` | `path`, `flags` (optional, sides as in `cross`) | the rows of a CSV (all columns read as strings) or parquet file | sorted by `id`, then `code` ([WS] `impact_pass.py:209-247`) |

**`threshold`** ([OA] `llm_passes.py:218-362, 1277-1302`; `sdg_pass2.py:71-92`).
`from` names a `score_json` pass whose list is this question's `a`; the pass
is `work x list`. `model = "same"` reads each model's own source (the model
must be among the source pass's models); `model = "<name>"` reads that
model's source for every model of the pass ([OA] D068: an ADT pass 2 on
another model's pass 1). `at_least` is an int or float, finite, in [0, 1], not
a bool. Before selecting, the whole source is checked, in order, each failure
an `UnitsError`: columns `id`, `code` (String), `score` (Float64),
`parse_failure` (Boolean); no null `id` or `code`; every code in the list; no
score null, NaN or outside [0, 1]; no repeated (id, code); every scored work
has one row per label; every scored work is in the texts table. A work of
the texts table with no row is refused unless `allow_unscored`. A
parse-failure row scores 0.0 and enters only at `at_least = 0`. Each unit
carries the source's score as `source_score`.

**`cross` sides** (`a` and `b`, the question's lists in that order): `from`
(a pass whose rows carry one `label` per (id, code) of that list: a
`letter_logprob` or `letter_text` pass without sides at level `work x list`,
or a `letter_text` table pass), `models` (a non-empty list of that pass's
models, or `"all"`), `positive` (non-empty, letters of the source question),
`combine` (`"union"` or `"intersection"`, required when `models` has more
than one entry, D011). A label is present for a source when that source has
a row (id, code) with a label in `positive`; `OTHER` counts only if listed
([WS] `impact_pass.py:116-148`). `union`: present for at least one source;
`intersection`: for every source. Each unit carries one Boolean flag per
source, `<list id>_<model>`, side `a` then side `b`, models in the side's
order. The two sides must read different lists. Every unit's work must be in
the texts table (`UnitsError` with the count and the first, [WS]
`impact_pass.py:164-169`); a source without `id`, `code` or `label` is
refused ([WS] `impact_pass.py:110-113`).

**`file`**: level `work` needs column `id`; `work x list` needs `id`,
`code`; `work x list x list` needs `id` and the two list ids as columns
(`code` is then `<a>|<b>`). Other columns are ignored. Refused: a missing
column, a repeated unit, a code not in its list, a work not in the texts
table ([WS] `impact_pass.py:220-232`). With `flags`, the flag columns are
computed from the sides as in `cross` and may all be false.

Sources with `repeats > 1` are refused by `threshold`, `cross` and `file`
flags. An empty unit set is refused (`UnitsError`, [OA]
`llm_passes.py:1209-1210, 1300-1301`). The `code` of a `work x list x list`
unit is `<a>|<b>` ([WS] `impact_pass.py:196`).

The unit order is the plan order: chunks are cut from it (6.6). Calls are
made in plan order, sides of a unit adjacent in side order, repeats of a unit
adjacent. Outputs are sorted whatever the plan order (section 8).

## 6. Models and the client

### 6.1 A model entry

`[models.<name>]`, `<name>` matching `[a-z][a-z0-9_]*`.

| key | type | default | meaning |
|---|---|---|---|
| `endpoint` | string | required | base URL; calls `POST <endpoint without trailing "/">/chat/completions` ([OA] `client.py:259-264, 505`) |
| `api_key_env` | string | required | the environment variable holding the key, sent as `Authorization: Bearer <key>` ([OA] `llm_passes.py:1017-1032`) |
| `model` | string | required | the model name sent |
| `seed` | int | required | sent and keyed |
| `temperature` | float | 0.0 | converted to a Python `float` before keying, so `0` keys as `0.0` |
| `reasoning` | `"off"`, `"on"` | required | 6.2 |
| `reasoning_style` | `"omit"`, `"enable_thinking"`, `"reasoning_effort"` | required | 6.2 |
| `reasoning_effort` | string | none | required with style `reasoning_effort` and `reasoning = "on"`, refused otherwise |
| `extra_body` | table | `{}` | merged into the body (6.3) |
| `extraction` | `"first_token"`, `"final_channel"` | `"first_token"` | `letter_logprob` only (4.3) |
| `expect_model` | string or list of strings | none | D012, 6.4 |
| `timeout_s` | float | 60.0 | the httpx timeout of a call ([OA] `client.py:244`) |
| `concurrency` | int >= 1 | 4 | calls in flight ([OA] `client.py:242, 353-378`) |
| `max_retries` | int >= 0 | 3 | HTTP retries after the first attempt ([OA] `client.py:243`) |

The key is read once per run, after loading `[run].env_file` (default
`.env`, next to the workflow) without overriding the environment, as [OA]
`llm_passes.py:958-973` does: lines `KEY=VALUE`, empty lines, `#` comments
and lines without `=` skipped, split at the first `=`, the key stripped of a
leading `export `, the value stripped of surrounding quotes. A missing or
empty variable is refused before any call (`KeyMissing`, naming the variable,
never the value), except in replay.

### 6.2 Reasoning

| `reasoning_style` | `"off"` adds | `"on"` adds |
|---|---|---|
| `omit` | nothing | nothing (the model reasons or not by its own default) |
| `enable_thinking` | `"chat_template_kwargs": {"enable_thinking": false}` | `"chat_template_kwargs": {"enable_thinking": true}` |
| `reasoning_effort` | `"reasoning_effort": "none"` | `"reasoning_effort": <reasoning_effort>` |

What was sent in the earlier runs, and how it is written now:

| earlier run | earlier `extra_body` | now |
|---|---|---|
| protocol v1, every model ([OA] `docs/protocol-freeze-v1.md:19-21`) | none | `reasoning = "off"`, `reasoning_style = "omit"` |
| `coder`, impact and paper ([WS] `params.yaml:396-401, 511-513`) | `{"logprobs": false}` | `"on"`, `"omit"` (the `logprobs` comes from the readout) |
| `gemma` thinking ([WS] `params.yaml:406-413, 531-535`) | `{"chat_template_kwargs": {"enable_thinking": true}, "logprobs": false}` | `"on"`, `"enable_thinking"` |
| [DV] `gpt-oss`, reasoning layer ([DV] `params.yaml:101-107`) | `{"reasoning_effort": "medium", "logprobs": false}` | `"on"`, `"reasoning_effort"`, `reasoning_effort = "medium"` |
| [DV] `gemma`, `mistral-small`, logprob layer of `impact/p2` ([DV] `params.yaml:63-64`) | `{}` | `"off"`, `"omit"` |

### 6.3 The body and the keyed extra body

The wire body is built in this order: the readout's fields (4.1), the
reasoning fields (6.2), the readout's added fields (`"logprobs": false`),
then the model's `extra_body`. `extra_body` may not hold `model`,
`messages`, `temperature`, `max_tokens`, `seed`, `logprobs`,
`top_logprobs`, `response_format`, `reasoning_effort`, `n`, `stream`, nor
`chat_template_kwargs.enable_thinking` (`WorkflowError`). Its
`chat_template_kwargs` table, if any, is merged key by key into the one the
reasoning added. (Earlier, `extra_body` was merged last and silently
overrode `logprobs: true`, [DV] `client.py:356-369`.)

The **keyed extra body** is every top-level wire field outside the readout's
fields of 4.1: the reasoning fields, the readout's added fields and the
model's `extra_body`. It is what the earlier clients keyed as `extra_body`,
so each row of the table of 6.2 keys as before.

### 6.4 One call

As [OA] `llm/client.py:463-528`:

1. Compute the key (6.5). If `<cache_dir>/<key[:2]>/<key>.json` exists, read
   its `response` and make no request.
2. Otherwise, in replay, raise `CacheMiss` (pass, model, key). Else POST the
   wire body. On a 2xx: the JSON body, or `{"unparseable_body": <text>}` when
   it is not JSON (a parse failure, not retried). On 429, 5xx or an
   `httpx.TransportError` (timeouts included): sleep
   `min(BACKOFF_BASE_S * 2**attempt, BACKOFF_CAP_S)` (0.5 and 8.0 s;
   module attributes of `sdg_tech_impact_tagger.client`, patchable by tests)
   and try again, at most `max_retries` times, then raise `LLMCallError`
   carrying the last status (None for transport errors). Any other status
   raises `LLMCallError` at once.
3. With `expect_model` set, a body whose `model` is a string not in
   `expect_model` raises `ModelMismatch` (an `LLMCallError`) and is not
   written to the cache; the call fails like any other (6.6), so it is asked
   again in a later attempt or a later run (D012). A body with no `model`
   passes. A cached body is checked the same way; a cached mismatch raises
   `ModelMismatch` naming the cache file, which is left in place.
4. Write the cache file (6.5) and return the body.

Within a run, the first (`model_served`, `system_fingerprint`) seen is kept;
a later call that differs emits `ModelChangeWarning` once per new (model served, fingerprint) and is
counted in the manifest (D012).

Calls of a batch run in a thread pool of `concurrency`, results in request
order; a failing call does not stop the others, and the batch raises
`LLMCallError` at the end with `failures`, a list of (index, exception)
([OA] `client.py:353-378`). One `httpx.Client` serves a run (the earlier
runners built one per sub-chunk, [OA] `llm_passes.py:1038-1047, 1261`).

### 6.5 Cache key and cache file

D013, [OA] `llm/client.py:382-421, 460-492`.

Key fields, in this insertion order:

| kind | fields |
|---|---|
| `chat` | `model`, `system`, `user`, `seed`, `temperature`, `max_tokens`, `response_format` (null when none), `extra_body` (the keyed extra body), `kind` = `"chat"` |
| `single_token` | `model`, `system`, `user`, `seed`, `temperature`, `max_tokens`, `top_logprobs`, `extra_body` |

With `repeats > 1`, the call of repeat `r >= 2` adds `"repeat": r`; repeat 1
has no such field, so it keys exactly as a plain call.

`key = sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()`,
`ensure_ascii` left at its default (true). `letters`, `spelling` and
`extraction` are read-side only and not keyed; nor is the endpoint.

The file `<cache_dir>/<key[:2]>/<key>.json` holds
`json.dumps({"cache_key": key, "kind": kind, "request": fields, "response": body}, ensure_ascii=False)`
in UTF-8, written to `<key>.<uuid4 hex>.tmp` in the same directory and
renamed onto the file with `os.replace`. A file that cannot be read as JSON
with a `response` key raises `CacheError` naming it. The earlier caches are
read in place, unchanged.

### 6.6 Chunks, workers, attempts

Chunks, claims, partial files and combine are those of [OA]
`llm_passes.py:370-468, 1091-1158`:

- Units are cut, in plan order, into chunks of `chunk_size` units, numbered
  from 1. With `per_call = "work"` a chunk takes whole works and closes once
  it holds `chunk_size` units or more ([WS] `paper_pass.py:419-432`); the
  last holds the rest. At most 99,999 chunks.
- Files under `<work dir>/chunks/`: `chunk_NNNNN.parquet` (5 digits),
  `chunk_NNNNN.claim`, `chunk_NNNNN.<worker>.partial`. A worker name matches
  `^[A-Za-z0-9_-]{1,64}$` (`fullmatch`).
- A worker visits the chunks in order (`reverse`: from the last). It skips a
  chunk whose file exists; claims the others by creating the claim file with
  `O_CREAT | O_EXCL` and writing its name (a claim holding its own name is
  its own); skips a chunk claimed by another; answers the chunk, writes it to
  its partial file, renames it onto the chunk file, deletes the claim. An
  exception leaves the chunk unwritten and its claim in place.
- A chunk is answered in sub-chunks of `sub_chunk` units (whole works with
  `per_call = "work"`). Attempt 1 asks every sub-chunk; each later attempt,
  up to `attempts`, asks again the sub-chunks whose batch raised
  `LLMCallError` (their answered calls come from the cache); then
  `LLMCallError` naming how many still fail. Any other exception propagates
  at once ([OA] `llm_passes.py:476-537`). The budget retry (4.4) is made
  inside the sub-chunk's attempt.
- When every planned chunk is on disk, the run combines (6.8) and writes the
  output; otherwise it reports the missing chunks (held by other workers) and
  writes nothing.

### 6.7 `run.json` and resume

`<work dir>/run.json` records what the run is. If it exists, every key of the
stored and the new record is compared and any difference raises
`ManifestMismatch` with one line per key, sorted,
`"<key>: <stored!r> on disk, <new!r> now"` ([OA] `llm_passes.py:561-601`).
If not, it is created with `O_EXCL` as
`json.dumps(record, indent=2, sort_keys=True) + "\n"`. Keys:

| key | value |
|---|---|
| `pass`, `question`, `model_entry`, `model` | pass id, question name, entry name, name sent |
| `prompt_id` or `prompt_ids` | as the question has it, after `prompt_prefix` |
| `run_id` | 3.6 |
| `texts_sha256` | `frame_digest(texts, ["id", *fields])`, nulls as `null_text` |
| `units`, `units_sha256` | the planned units' count and `frame_digest` over their key columns, in plan order |
| `unit_rule` | the resolved `units` table of the pass |
| `chunk_size`, `repeats` | as resolved |

`frame_digest(frame, columns)` is the hex sha256 of the UTF-8 of
`"\n".join(json.dumps([row[c] for c in columns], ensure_ascii=False) for each row)`
([OA] `llm_passes.py:545-558`). `sub_chunk`, `attempts`, `concurrency`,
`timeout_s` and the endpoint are not recorded: they do not change an answer
([WS] `docs/llm-passes-contract.md:470-473`). `combine_only` needs an
existing `run.json` (`ManifestMismatch` otherwise).

### 6.8 Combine

As [OA] `llm_passes.py:619-707`, raising on the first failure:

1. Every planned chunk file exists (`IncompleteRun`: the number missing and
   the lowest).
2. No `chunk_*.parquet` outside the plan (`CombineError` naming them).
3. Each chunk has exactly the output schema, names, order and dtypes
   (`CombineError` naming the file).
4. Each chunk holds each of its expected keys once and no other
   (`CombineError` with the counts missing, unexpected, repeated).
5. Every row's `model`, `prompt_id` (per code) and `run_id` are the run's
   (`CombineError` with the file and the count).

Then the chunks are concatenated, sorted (section 8) and written to
`<output>.partial`, renamed onto the output. Nothing is dropped or repaired.

### 6.9 Replay

`replay = True` (`--replay`) runs every asked pass with no network: no key
is read, every call must hit the cache, a miss raises `CacheMiss` and the
pass writes nothing. Everything else (units, chunks, budget retries,
combine) is as in a live run, so a pass rebuilds the earlier table from the
earlier cache, given the earlier texts and settings (8.4).

## 7. The workflow file

### 7.1 Loading

TOML, read with `tomllib` into a strict model; any unknown key, at any level,
is refused (D015, `WorkflowError` naming the key and its table). Relative
paths are read against the workflow file's directory (a preset's against the
current directory). All checks of this section are made before any call.

### 7.2 `[run]` and `[lists]`

| key | type | default | meaning |
|---|---|---|---|
| `name` | string `[A-Za-z0-9_-]+` | required | |
| `texts` | path | none | the texts parquet; `--texts` or the `texts` argument overrides; one of them is required |
| `id_column` | string | `"id"` | 2.1 |
| `cache_dir` | path | `"cache"` | default cache directory of every (pass, model) |
| `output_dir` | path | `"runs/<name>"` | 8.1 |
| `env_file` | path | `".env"` | 6.1 |
| `[lists]` | table list id to path | `{}` | lists added to the shipped `sdg` and `adt` |

### 7.3 `[[passes]]`

| key | type | default | meaning |
|---|---|---|---|
| `id` | string `[a-z][a-z0-9_]*` | required | unique |
| `question` / `question_dir` | shipped name / path | exactly one | |
| `models` | list of model entry names | required | non-empty, unique; run one after another in this order |
| `units` | inline table | required | section 5 |
| `chunk_size`, `sub_chunk`, `attempts` | int >= 1 | 1000, 100, 3 | 6.6 |
| `repeats` | int >= 1 | 1 | each unit asked `repeats` times (6.5) |
| `spelling` | `"sum"`, `"exact"` | `"sum"` | `letter_logprob` only (D007) |
| `budget_rule` | `"spent"`, `"tokens"`, `"length"` | `"spent"` | 4.4 |
| `null_text` | string | `""` | 2.1 |
| `prompt_prefix` | string `[a-z0-9.]+` | the question's | 3.5 ([WS] `impact_pass.py:40-41, 94-95`) |
| `[passes.budgets.<model>]` | `max_tokens`, `retry_max_tokens`, `top_logprobs`, `timeout_s` | the question's, the model's | per-model budgets of this pass |
| `[passes.cache_dirs]` | model to path | `[run].cache_dir` | a model's cache for this pass (to read an earlier cache in place) |

Refused (`WorkflowError`): a level, list or readout that does not fit the unit
rule (section 5); `letter_logprob` with a model whose `reasoning` is `"on"`
(D006); a reference to an unknown or later pass or model; `retry_max_tokens`
not above `max_tokens`; a `cross` that names no `combine` with several models
(D011); `spelling` on a readout other than `letter_logprob`.

### 7.4 Example: protocol v1 then the impact question, as run in [WS]

Values from [WS] `params.yaml:17-86, 346-417`.

```toml
[run]
name = "protocol-v1-impact"
texts = "works.parquet"            # id, title, abstract
cache_dir = "cache"

[models.qwen3]
endpoint = "https://conversation.ia.unistra.fr/api"
api_key_env = "UNISTRA_API_KEY"
model = "qwen3"
seed = 42
temperature = 0.0
reasoning = "off"
reasoning_style = "omit"
timeout_s = 180.0
concurrency = 6

[models.gemma]
endpoint = "https://conversation.ia.unistra.fr/api"
api_key_env = "UNISTRA_API_KEY"
model = "gemma"
seed = 42
temperature = 0.0
reasoning = "off"
reasoning_style = "omit"
timeout_s = 180.0
concurrency = 6

[models.coder]
endpoint = "https://conversation.ia.unistra.fr/api"
api_key_env = "UNISTRA_API_KEY"
model = "coder"
seed = 42
temperature = 0.0
reasoning = "on"
reasoning_style = "omit"
timeout_s = 900.0
concurrency = 8

[models.gemma_thinking]
endpoint = "https://conversation.ia.unistra.fr/api"
api_key_env = "UNISTRA_API_KEY"
model = "gemma"
seed = 42
temperature = 0.0
reasoning = "on"
reasoning_style = "enable_thinking"
timeout_s = 900.0
concurrency = 8

[[passes]]
id = "sdg_pass1"
question = "protocol_v1/sdg_pass1"
models = ["qwen3", "gemma"]
units = { rule = "all" }

[[passes]]
id = "sdg_pass2"
question = "protocol_v1/sdg_pass2"
models = ["qwen3", "gemma"]
units = { rule = "threshold", from = "sdg_pass1", model = "same", at_least = 0.25 }
chunk_size = 2000

[[passes]]
id = "adt_pass1"
question = "protocol_v1/adt_pass1"
models = ["gemma", "qwen3"]
units = { rule = "all" }

[[passes]]
id = "adt_pass2"
question = "protocol_v1/adt_pass2"
models = ["gemma", "qwen3"]
units = { rule = "threshold", from = "adt_pass1", model = "same", at_least = 0.25 }
chunk_size = 2000

[[passes]]
id = "impact"
question = "impact/p3_2"
models = ["coder", "gemma_thinking"]
attempts = 4
budget_rule = "tokens"             # as the impact pass of [WS] asked again
units = { rule = "cross", agreed_first = true, a = { from = "adt_pass2", models = ["gemma", "qwen3"], positive = ["E", "A", "T", "M"], combine = "union" }, b = { from = "sdg_pass2", models = ["gemma", "qwen3"], positive = ["Y"], combine = "union" } }

[passes.budgets.coder]
max_tokens = 6000
retry_max_tokens = 20000

[passes.budgets.gemma_thinking]
max_tokens = 4000
retry_max_tokens = 12000
```

The impact table carries the flags `adt_gemma`, `adt_qwen3`, `sdg_gemma`,
`sdg_qwen3`, as [WS] `impact_p3_2_<model>.parquet` does.

### 7.5 Presets

Shipped as `src/sdg_tech_impact_tagger/presets/<name>.toml` (D009):

| preset | passes | models |
|---|---|---|
| `protocol-v1` | the four protocol passes, at 0.25 | as frozen: `qwen3` on the SDG passes, `gemma` on the ADT passes ([OA] `docs/protocol-freeze-v1.md:12-17`) |
| `protocol-v1-impact` | the example of 7.4 | as there |
| `paper-v1` (experimental) | `paper_adt` and `paper_sdg` (`all`), then `paper_impact` (`cross` over both models' paper labels, `union`, no `agreed_first`, `budget_rule = "length"`) | `coder` and `gemma` (reasoning on, style `enable_thinking`), budgets 16000/32000 and 32000/48000, `timeout_s` 1800, `attempts` 4 ([WS] `params.yaml:486-552`) |

## 8. Outputs

### 8.1 Files

| path | content |
|---|---|
| `<output_dir>/<pass>/<model>.parquet` | the table of the pass for that model entry |
| `<output_dir>/<pass>/<model>/run.json`, `manifest.json`, `chunks/`, `calls/<worker>.jsonl` | the run (6.6, 6.7, section 9) |
| `<output_dir>/workflow.json` | the resolved workflow, section 9 |

### 8.2 Columns

Every table starts with the key columns, then the call columns, then the
readout columns. All tables are sorted by `id`, then `code` when present,
then `repeat` (Polars string order, which is code point order).

Key columns:

| column | dtype | when |
|---|---|---|
| `id` | String | always |
| `code` | String | the rows are per label or per unit of a list level; `<a>|<b>` at `work x list x list` |
| `<a list id>`, `<b list id>` | String | `work x list x list` |
| `<list id>_<model>` | Boolean | `cross`, or `file` with `flags` |
| `source_score` | Float64 | `threshold` |
| `repeat` | Int64 | always (1 .. `repeats`) |

Call columns: `model` (String, the name sent), `model_served` (String,
null when not given; when a row stands on several calls that disagree, their
distinct values sorted and joined with `|`), `system_fingerprint` (String,
same rule), `prompt_id` (String), `run_id` (String).

Readout columns:

| readout | columns |
|---|---|
| `score_json` | `score` Float64, `tokens_in` Int64, `tokens_out` Int64, `parse_failure` Boolean (tokens of the work's call on each of its rows) |
| `letter_logprob` | `label` String, `p_<letter lower>` Float64 per letter in letter order, `tokens_in`, `tokens_out`, `parse_failure` |
| `letter_text` single | `label` String, `retried` Boolean, `tokens_in`, `tokens_out`, `parse_failure` |
| `letter_text` table | `label`, `retried`, `tokens_in`, `tokens_out` (the work's call on each row), `parse_failure` |
| `json_object` `label_object` | one column per field (`letter`, `string`, `quote` String; `boolean` Boolean; `integer` Int64; `number` Float64), `quotes_ok` Boolean (when a quote field exists), `retried`, `tokens_in`, `tokens_out`, `parse_failure` |
| `json_object` `impact_pairs_v1` | `pos_label`, `neg_label`, `beneficial_kind` String, `quotes_ok` Boolean, `n_pairs` Int64, `retried`, `tokens_in`, `tokens_out`, `parse_failure` |

A question with sides writes, in place of `label` .. `tokens_out`:
`<side>_label` for each side, then `<side>_p_<l>` (`letter_logprob`) or
`<side>_retried` (`letter_text`) for each side, then `<side>_tokens_in`,
`<side>_tokens_out` for each side, then `tokens_in`, `tokens_out` (the sums),
then `parse_failure` (any side `OTHER`). ([WS] `impact_pass.py:47-58,
349-366`.)

### 8.3 From the earlier tables to the new ones

For a replay to be compared row for row. "drop" means the new column has no
earlier counterpart.

| earlier table | earlier column | new column or rule |
|---|---|---|
| all | `wos_id` | `id` |
| all | (none) | drop `model_served`, `system_fingerprint`, `run_id`, `repeat` |
| `SCORES_SCHEMA` ([OA] `sdg_pass1.py:32-43`) | `code`, `model`, `prompt_id`, `score`, `tokens_in`, `tokens_out`, `parse_failure` | same names |
| | `arm` | `"score17"` (SDG) or `"adt_score"` (ADT) |
| | `batch_id` | `f"{arm}-{model}"` ([OA] `sdg_pass1.py:236`, `adt_pass1.py:380`) |
| `PASS2_SCHEMA` ([OA] `sdg_pass2.py:56-68`) | `label`, `parse_failure`, tokens | same |
| | `p_yes` | `p_y` (drop `p_n`) |
| | `pass1_score` | `source_score` |
| | `batch_id` | `f"pass2-{model}"` |
| `ADT_PASS2_SCHEMA` ([OA] `adt_pass2.py:50-67`) | `p_n` .. `p_e`, `label` | same |
| | `relevant` | `label in {M, T, A, E}`, null when `OTHER` ([OA] `adt_pass2.py:48, 273-275`) |
| | `pass1_score`, `batch_id` | `source_score`; `f"adt-pass2-{model}"` |
| [WS] `impact_p3_2_<model>` ([WS] `impact_pass.py:47-58`) | `code`, `adt`, `sdg`, flags, `pos_label`, `neg_label`, `pos_retried`, `neg_retried`, `tokens_in`, `tokens_out`, `parse_failure` | same (drop `pos_tokens_*`, `neg_tokens_*`) |
| | `batch_id` | `f"impact-{model}"` |
| [WS] `paper_<adt|sdg>_<model>` ([WS] `paper_pass.py:62-73`) | all but `batch_id` | same; `batch_id` = `f"paper-{exercise}-{model}"` |
| [WS] `paper_impact_<model>` ([WS] `paper_pass.py:75-88`) | all but `batch_id` | same; flags `adt_<model>`, `sdg_<model>`; `batch_id` = `f"paper-impact-{model}"` |
| [DV] `LABELS_RAW_SCHEMA` ([DV] `schemas.py:39-55`), logprob layer of `impact/p2` | one row per side | unpivot: `dimension` = side, `label` = `<side>_label`, `p_yes` = `<side>_p_y` (`spelling = "exact"`), tokens = `<side>_tokens_*` |
| | `adt`, `sdg` | the [DV] codes: `COMPUTING_INFRASTRUCTURE` to `CI`, `BLOCKCHAIN` to `BL`, `ROBOTICS` to `ROB`, `ADDITIVE_MANUFACTURING` to `AM`; `SDG-07` to `SDG7` ([DV] `params.yaml:1-5`) |
| | `source`, `sample_id`, `temperature`, `conf` | `"llm"`, 0, the model's temperature, null |
| | `batch_id` | `f"p2-{model}"` |

### 8.4 What a replay needs

| earlier tables | texts | workflow settings beyond the shipped question |
|---|---|---|
| protocol v1 of [OA] (recall sample, pool) and of [WS] | the documents file each pass read, in its order (for the [OA] pool pass 2, the scoped documents files) | the earlier cache directory per (pass, model) in `cache_dirs`; `threshold` with `model` as run (`"gemma"` for the [OA] pool ADT pass 2 on `qwen3`, D068 there); `allow_unscored` where the earlier run allowed it |
| [WS] impact | the [WS] documents | 7.4 as written (`budget_rule = "tokens"`) |
| [WS] paper | the [WS] documents | preset `paper-v1` (`budget_rule = "length"`) |
| [DV] logprob layer of `impact/p2`, `gemma`, `mistral-small` | the works of the [DV] triples, units as a `file` of (id, adt, sdg) | `spelling = "exact"`, `null_text = "None"` if any null reached the earlier run |

## 9. The run manifest

D012, and the record list of the annotation literature (survey
`workflow-practice.md`, section 4). Written by the package, never by the user.

`<output_dir>/<pass>/<model>/calls/<worker>.jsonl`: one line per call made or
read from the cache, in completion order: `cache_key`, `kind`, `cached`,
`repeat`, `retry` (Boolean), `model_served`, `system_fingerprint`,
`finish_reason`, `tokens_in`, `tokens_out`, `duration_ms`, `parse_failure`
(the [OA] `CallRecord`, `client.py:169-179`, never written there, plus the
served model).

`<output_dir>/<pass>/<model>/manifest.json`, rewritten at each combine:

| key | value |
|---|---|
| `package_version`, `python_version` | |
| `started_at`, `combined_at` | UTC ISO 8601: the creation of `run.json`, this combine |
| `workflow`, `workflow_sha256` | name and the sha256 of the workflow file's bytes (or the preset's) |
| `pass`, `question`, `question_status`, `question_files` | file path to sha256 for every file the question read |
| `lists` | list id to sha256 of its file |
| `prompt_id` / `prompt_ids`, `run_id` | |
| `model` | the resolved model entry: every key of 6.1 but the key's value (`api_key_env` only) |
| `endpoint`, `cache_dir`, `replay` | |
| `settings` | the resolved budgets, `spelling`, `budget_rule`, `null_text`, `repeats`, `chunk_size`, `sub_chunk`, `attempts` |
| `texts_sha256`, `unit_rule`, `sources` | the unit rule and, per source, its path and file sha256 |
| `counts` | `units`, `rows`, `parse_failures`, `retried`, from the table; `calls`, `cached_calls`, `fresh_calls`, `distinct_keys`, `tokens_in`, `tokens_out`, from the call logs |
| `models_served`, `system_fingerprints` | value to number of calls |
| `model_changes` | the warnings of 6.4, in order |

`<output_dir>/workflow.json`: the resolved workflow (every default filled),
the package version, and per (pass, model) the paths of its table and
manifest.

## 10. Public interface

### 10.1 Python

All importable from `sdg_tech_impact_tagger`.

| name | signature | returns |
|---|---|---|
| `load_workflow` | `(path: str | Path | None = None, *, preset: str | None = None) -> Workflow` | the checked workflow; exactly one of `path`, `preset` |
| `run` | `(workflow: Workflow, *, texts: pl.DataFrame | str | Path | None = None, replay: bool = False, passes: Sequence[str] | None = None, models: Sequence[str] | None = None, limit: int | None = None, worker: str = "main", reverse: bool = False, combine_only: bool = False, answer_models: Mapping[str, type[pydantic.BaseModel]] | None = None, transport: httpx.BaseTransport | None = None) -> list[RunResult]` | one `RunResult` per (pass, model) asked, in order |
| `load_question` | `(name_or_path: str | Path) -> Question` | a checked question |
| `Question` | attributes `name`, `level`, `readout`, `text_fields`, `lists`, `prompt_ids: dict[str, str]` (`{"": id}` when not per label); method `render(texts: Mapping[str, str | None], units: Sequence[tuple[str, ...]] = (), *, null_text: str = "") -> list[tuple[str, str]]` | the (system, user) of each call, in call order |
| `load_list` | `(name_or_path: str | Path) -> LabelList` | attributes `id`, `name`, `labels: tuple[dict[str, str], ...]` |
| `cache_key` | `(fields: Mapping[str, Any]) -> str` | 6.5 |
| `Quote` | `Annotated[str, ...]` | marks a quote field of an answer model |
| `RunResult` | fields `pass_id`, `model`, `units`, `chunks`, `written`, `skipped_on_disk`, `skipped_claimed`, `missing` (lists of chunk indices), `output_written`, `output` (Path) | [OA] `llm_passes.py:1050-1068` |

`texts` overrides `[run].texts`. `passes` and `models` restrict what is run
(a pass not run must already have its output when another reads it). `limit`
keeps the first `limit` works of the texts table for the whole run.
`answer_models` gives, per pass id, the item model of a `label_object`
question (4.5). `transport` replaces the network (tests use
`httpx.MockTransport`). Passes run in file order; a pass whose output is not
written (chunks held by other workers) stops the passes that read it, which
are returned with `output_written = False` and `units = 0`.

### 10.2 Command

```
sdg-tech-impact-tagger run [WORKFLOW] [--preset NAME] [--texts PATH] [--replay]
    [--pass ID]... [--model NAME]... [--limit N] [--worker NAME] [--reverse]
    [--combine-only] [--output-dir DIR] [--cache-dir DIR]
sdg-tech-impact-tagger check [WORKFLOW] [--preset NAME] [--texts PATH]
sdg-tech-impact-tagger prompt QUESTION [--a CODE] [--b CODE]
sdg-tech-impact-tagger preset NAME
```

| command | does |
|---|---|
| `run` | `run(...)`; exactly one of `WORKFLOW`, `--preset`; prints one line per (pass, model) result |
| `check` | loads the workflow, the questions, the lists and the texts, plans every pass whose sources exist, prints the prompt ids, run ids and unit counts; no call, no write |
| `prompt` | prints the system and user text of one call with placeholder texts `<title>`, `<abstract>` (each field as `<field>`), as [OA] `llm_passes.py:911-950` |
| `preset` | prints the preset's TOML, to copy and edit |

Exit status: 0 when every asked pass finished or waits on chunks of other
workers; 1 on any `TaggerError` (message on standard error, never a key); 2
on a usage error.

## 11. Errors

All derive from `TaggerError(Exception)`. Nothing is written by a refusal
raised before the first call.

| exception | raised when |
|---|---|
| `WorkflowError` | the workflow file: unknown or missing key, wrong type or value, unknown or later pass, unknown model, unfit rule, reserved `extra_body` key, `letter_logprob` with reasoning on (D006), missing `combine` (D011) |
| `QuestionError` | a question: unknown key, missing file or block, repeated block, bad placeholder set, bad material, computed id not the expected one, `[[OPEN` marker |
| `ListError` | a list file (2.2) |
| `TextsError` | the texts table (2.1) |
| `UnitsError` | a unit rule: source checks, unscored works, file rows, works not in the texts, empty unit set |
| `KeyMissing` | the key variable is unset or empty (live run) |
| `ManifestMismatch` | `run.json` differs, or is missing under `combine_only` |
| `IncompleteRun` | combine with planned chunks missing |
| `CombineError` | a chunk outside the plan, of another schema, with wrong keys, or rows of another model, prompt id or run id |
| `LLMCallError` | a call failed (exhausted retries, non-retryable status), or a batch or sub-chunk still fails after its attempts; attributes `status_code`, `failures` |
| `ModelMismatch` (an `LLMCallError`) | an answer, fresh or cached, from a model outside `expect_model` |
| `CacheMiss` | replay, a call not in the cache |
| `CacheError` | an unreadable cache file |
| `ModelChangeWarning` (a `UserWarning`) | the model served or fingerprint changed within a run |

## 12. Choices this contract makes

Each is a design choice not settled by D001 to D015, with its alternative.

1. Per-label material of the shipped questions is read from the original files in each question directory (as imported); lists hold ids, keys and names, and material for new questions. Alternative: all material moved into the list files.
2. Lists are TOML files with `[list]` and `[[labels]]`, every label with the same string fields. Alternative: CSV or JSON lists.
3. Shipped lists are checked by `lists/SHA256SUMS`. Alternative: one `SHA256SUMS` for questions and lists.
4. One block reader for every question file (3.2), verified on the 31 earlier ids. Alternative: keep each earlier reader per question.
5. Paper labels are read by `letter_text` with `layout = "table"`. Alternative: a fifth readout `letter_table` (amending D006).
6. Paper impact uses a named assembly `impact_work_v1` and a named JSON form `impact_pairs_v1`, closed in Python. Alternative: generic item templates in `question.toml`.
7. `fill = "replace"` kept beside `format` to reproduce the paper questions' texts byte for byte. Alternative: `format` only, accepting a different text when a title holds `{abstract}`.
8. The kind of call and the added `logprobs: false` are fixed by the readout (4.1). Alternative: a `call_kind` key in `question.toml`.
9. Budget retry: one default rule (`finish_reason == "length"` or `tokens_out >= max_tokens`) and a `budget_rule` pass key (`tokens`, `length`) to replay each earlier rule. Alternative: a single rule with no override, replay accepting misses.
10. `spelling` is a pass key. Alternative: a question key.
11. `extraction` is a model key. Alternative: a question key.
12. `null_text` is a pass key, default `""`. Alternative: a question key, or a per-field setting.
13. `prompt_prefix` on the pass, limited to the question's `recorded_ids`. Alternative: a second shipped question for each recorded prefix.
14. The run id hashes the fields of 3.6 and leaves out the endpoint. Alternative: include the endpoint.
15. `reasoning` and `reasoning_style` are required, with a style `omit` that sends nothing. Alternative: defaults `off` and `omit`.
16. Reasoning off under style `reasoning_effort` sends `"none"`. Alternative: send nothing.
17. Reserved `extra_body` keys are refused and `chat_template_kwargs` merged key by key. Alternative: shallow merge, the package's fields winning.
18. `expect_model`: a body with no `model` passes; a mismatch fails the call (retried by attempts), is never cached; cached mismatches are refused and left in place. Alternative: check fresh answers only.
19. A row standing on several calls records their distinct served models and fingerprints joined with `|`. Alternative: per-side columns.
20. Questions with sides write one row per unit with per-side columns and summed tokens. Alternative: one row per (unit, side), as [DV].
21. The `model` column is the name sent; the entry name is in the file path and manifest. Alternative: the entry name, with a `model_sent` column.
22. `batch_id` and `arm` are not written (recomputed for comparison, 8.3). Alternative: keep them.
23. `relevant` is not written for the ADT pass 2 (derived from `label`). Alternative: a `positive` column from letters declared in the question.
24. The source score of a `threshold` unit is `source_score`. Alternative: keep `pass1_score`.
25. `repeat` is always a column. Alternative: only when `repeats > 1`.
26. Repeat 1 keys as a plain call; repeats 2 and up add `repeat` to the key. Alternative: every repeat keyed when `repeats > 1`.
27. Cross flags are named `<list id>_<model entry>`, and the two sides must read different lists. Alternative: `a_<model>`, `b_<model>`.
28. `combine` is required only when a side reads more than one model. Alternative: always required.
29. `agreed_first` defaults to false. Alternative: true, the order of the [WS] impact run.
30. Unit rules refuse sources with `repeats > 1`. Alternative: read repeat 1.
31. Threshold units follow the earlier order (work position, then code string order). Alternative: codes in list order.
32. Calls go in plan order; SDG pass 2 no longer groups a chunk's calls by goal ([OA] `llm_passes.py:1515`). Alternative: keep grouping by label.
33. Attempts are per sub-chunk for every question, including the paper impact, which retried whole chunks. Alternative: keep whole-chunk attempts for `per_call = "work"`.
34. Defaults `chunk_size` 1000, `sub_chunk` 100, `attempts` 3; client defaults `timeout_s` 60, `concurrency` 4, `max_retries` 3. Alternative: no defaults, every value required.
35. `seed` required, `temperature` default 0.0. Alternative: both required.
36. A model's passes run one after another, models of a pass in their listed order; parallelism comes from several workers. Alternative: models of a pass in parallel threads, as [DV].
37. A pass may read only passes listed before it. Alternative: order passes by their dependencies.
38. Layout `<output_dir>/<pass>/<model>.parquet` and `<output_dir>/<pass>/<model>/`. Alternative: one directory per workflow run with a timestamp.
39. Cache directory: one default in `[run]`, overridable per (pass, model) by `cache_dirs`. Alternative: per-model cache directories.
40. Three records: `run.json` (resume identity), `manifest.json` (the record), `calls/<worker>.jsonl` (per call). Alternative: one file.
41. `--limit N` keeps the first N works for the whole run. Alternative: the first N units of each pass, as the earlier runners.
42. Texts come as a parquet file or, from Python, a Polars frame. Alternative: also CSV.
43. `label_object`: one failed item makes the whole reply unreadable. Alternative: per-label failures.
44. `label_object` quotes: every non-empty quote must be a substring. Alternative: the paper rule (a quote required for a positive answer).
45. Answer models come from Python through `run(answer_models=...)` with a `Quote` type. Alternative: a registry of models named in the workflow.
46. `score_json` reads NaN or infinity as unreadable (the earlier code raised on infinity). Alternative: refuse the run.
47. An empty unit set is refused, which stops the passes that read it. Alternative: write an empty table and go on.
48. The `[[OPEN` refusal applies to every question. Alternative: only the protocol questions, as before.
49. Settled by D017: `impact/p2` is the [DV] logprob layer (`letter_logprob`) and `impact/p2_reasoning` (`letter_text`, Appendix A) the [DV] reasoning layer on the same blocks, prefix `p3`.
50. [DV] `gpt-oss` rows of the logprob layer (a letter's logprob after reasoning, `final_channel`) cannot be replayed under D006. Alternative: allow `letter_logprob` with reasoning when `extraction = "final_channel"`.
51. Letters are `[A-Za-z0-9]+`, so several characters are allowed, columns lower-cased. Alternative: one character only.
52. Presets keep the Unistra endpoint and aliases as run; `preset NAME` prints one to edit. Alternative: presets with placeholders for endpoint and model names.
53. Settled by D018: `protocol-v1` as frozen (qwen3 SDG, gemma ADT); `protocol-v1-impact` with both on every protocol pass, as [WS].
54. Commands `check`, `prompt` and `preset` beside `run`. Alternative: `run` only.

## Appendix A. The shipped `question.toml` files

Paths in `[blocks].files` and material are relative to the question
directory. Every id below is reproduced by the rule of 3.5 on the imported
files (`questions/IDS.tsv`).

### protocol_v1/sdg_pass1

```toml
[question]
name = "protocol_v1/sdg_pass1"
level = "work"
readout = "score_json"
status = "record"
prompt_id = "sdgp1-ca9ecbb1733d"

[lists]
a = "sdg"

[text]
fields = ["title", "abstract"]

[blocks]
files = ["sdg_pass1.md"]
system = "SYSTEM_SCORE17"
user = "USER_SCORE17"

[blocks.fill.system]

[blocks.fill.user]
title = "text:title"
abstract = "text:abstract"

[readout]
schema_name = "sdg_scores"

[budget]
max_tokens = 1024

[id]
prefix = "sdgp1"
blocks = ["SYSTEM_LIST", "USER_LIST", "SYSTEM_SCORE17", "USER_SCORE17", "SYSTEM_BINARY17", "USER_BINARY17"]
```

### protocol_v1/sdg_pass2

```toml
[question]
name = "protocol_v1/sdg_pass2"
level = "work x list"
readout = "letter_logprob"
status = "record"

[question.prompt_ids]
"SDG-01" = "sdgp2-dcccffcc8667+sdggoal-01-b05a3b57ee53"
"SDG-02" = "sdgp2-dcccffcc8667+sdggoal-02-a0abf5657e91"
"SDG-03" = "sdgp2-dcccffcc8667+sdggoal-03-8a79d5d16d42"
"SDG-04" = "sdgp2-dcccffcc8667+sdggoal-04-ae998db6225b"
"SDG-05" = "sdgp2-dcccffcc8667+sdggoal-05-9fb409d791af"
"SDG-06" = "sdgp2-dcccffcc8667+sdggoal-06-d2d571100fc2"
"SDG-07" = "sdgp2-dcccffcc8667+sdggoal-07-c5656ae949f3"
"SDG-08" = "sdgp2-dcccffcc8667+sdggoal-08-d6070daefc10"
"SDG-09" = "sdgp2-dcccffcc8667+sdggoal-09-1916b68fb388"
"SDG-10" = "sdgp2-dcccffcc8667+sdggoal-10-c718e4343f6c"
"SDG-11" = "sdgp2-dcccffcc8667+sdggoal-11-336f45b5c0d7"
"SDG-12" = "sdgp2-dcccffcc8667+sdggoal-12-36c122498095"
"SDG-13" = "sdgp2-dcccffcc8667+sdggoal-13-5fa43779c36d"
"SDG-14" = "sdgp2-dcccffcc8667+sdggoal-14-f858193eb567"
"SDG-15" = "sdgp2-dcccffcc8667+sdggoal-15-d258a447ed65"
"SDG-16" = "sdgp2-dcccffcc8667+sdggoal-16-159855659488"
"SDG-17" = "sdgp2-dcccffcc8667+sdggoal-17-639f3dbc94ff"

[lists]
a = "sdg"

[text]
fields = ["title", "abstract"]

[blocks]
files = ["sdg_pass2_v3.md"]
system = "SYSTEM_PASS2"
user = "USER_PASS2"

[blocks.fill.system]

[blocks.fill.user]
title = "text:title"
abstract = "text:abstract"
goal = "a:name_short"
scope = "material:scope"
targets = "material:targets"

[material.scope]
list = "a"
file = "sdg_pass2_v3/{id}.md"
block = "GOAL_SCOPE"

[material.targets]
list = "a"
file = "sdg_pass2_v3/{id}.md"
block = "GOAL_TARGETS"

[readout]
letters = ["Y", "N"]

[budget]
max_tokens = 1
top_logprobs = 20

[id]
prefix = "sdgp2"
blocks = ["SYSTEM_PASS2", "USER_PASS2"]

[[id.parts]]
per = "label"
prefix = "sdggoal-{number}"
material = ["scope", "targets"]
```

### protocol_v1/adt_pass1

```toml
[question]
name = "protocol_v1/adt_pass1"
level = "work"
readout = "score_json"
status = "record"
prompt_id = "adtp1-eb4f16256516+adtdesc-e8f65488c44f"

[lists]
a = "adt"

[text]
fields = ["title", "abstract"]

[blocks]
files = ["adt_pass1_v3.md"]
system = "SYSTEM_ADT_SCORE"
user = "USER_ADT_SCORE"

[blocks.fill.system]
descriptions = "listing:descriptions"

[blocks.fill.user]
title = "text:title"
abstract = "text:abstract"

[material.description]
list = "a"
file = "adt_descriptions_v3.md"
block = "{id}"

[material.name]
list = "a"
file = "adt_descriptions_v3.md"
block = "{id}"
part = "name"

[material.definition]
list = "a"
file = "adt_descriptions_v3.md"
block = "{id}"
part = "body"

[listing.descriptions]
list = "a"
item = "{id}: {name}\n{definition}"
sep = "\n\n"

[readout]
schema_name = "adt_scores"

[budget]
max_tokens = 1024

[id]
prefix = "adtp1"
blocks = ["SYSTEM_ADT_SCORE", "USER_ADT_SCORE"]

[[id.parts]]
per = "list"
prefix = "adtdesc"
material = ["description"]
```

### protocol_v1/adt_pass2

```toml
[question]
name = "protocol_v1/adt_pass2"
level = "work x list"
readout = "letter_logprob"
status = "record"

[question.prompt_ids]
AI = "adtp2-92e7027dcba2+adtdesc-ai-6e56892a59fd+adtbound-ai-db58219c6226"
IOT = "adtp2-92e7027dcba2+adtdesc-iot-798f24b085a0+adtbound-iot-6edba242d4c2"
COMPUTING_INFRASTRUCTURE = "adtp2-92e7027dcba2+adtdesc-computing-infrastructure-f285bcadfe5f+adtbound-computing-infrastructure-2b73b01a3e19"
BLOCKCHAIN = "adtp2-92e7027dcba2+adtdesc-blockchain-4b50ccb19ace+adtbound-blockchain-db50c42c89da"
ROBOTICS = "adtp2-92e7027dcba2+adtdesc-robotics-a73ea378205d+adtbound-robotics-ebfc2e7c7445"
ADDITIVE_MANUFACTURING = "adtp2-92e7027dcba2+adtdesc-additive-manufacturing-23384d3273ac+adtbound-additive-manufacturing-8774d4826a7b"

[lists]
a = "adt"

[text]
fields = ["title", "abstract"]

[blocks]
files = ["adt_pass2_v4.md"]
system = "SYSTEM_ADT_PASS2"
user = "USER_ADT_PASS2"

[blocks.fill.system]
role_rules = "block:ROLE_RULES"

[blocks.fill.user]
title = "text:title"
abstract = "text:abstract"
technology = "material:name"
definition = "material:definition"
boundaries = "material:boundaries"

[material.description]
list = "a"
file = "adt_descriptions_v3.md"
block = "{id}"

[material.name]
list = "a"
file = "adt_descriptions_v3.md"
block = "{id}"
part = "name"

[material.definition]
list = "a"
file = "adt_descriptions_v3.md"
block = "{id}"
part = "body"

[material.boundaries]
list = "a"
file = "adt_boundaries_v4.md"
block = "{id}"

[readout]
letters = ["N", "M", "T", "A", "E"]

[budget]
max_tokens = 1
top_logprobs = 20

[id]
prefix = "adtp2"
blocks = ["SYSTEM_ADT_PASS2", "ROLE_RULES", "USER_ADT_PASS2"]

[[id.parts]]
per = "label"
prefix = "adtdesc-{slug}"
material = ["description"]

[[id.parts]]
per = "label"
prefix = "adtbound-{slug}"
material = ["boundaries"]
```

### impact/p3_2

```toml
[question]
name = "impact/p3_2"
level = "work x list x list"
readout = "letter_text"
status = "current"
prompt_id = "p3.2-f72f01757eef"
recorded_ids = ["p3.1-f72f01757eef"]

[lists]
a = "adt"
b = "sdg"

[text]
fields = ["title", "abstract"]

[blocks]
files = ["impact_p3_2.md"]
system = "SYSTEM"
user = "USER_TEMPLATE"

[[sides]]
name = "pos"
block = "Q_POS"

[[sides]]
name = "neg"
block = "Q_NEG"

[blocks.fill.system]

[blocks.fill.user]
title = "text:title"
abstract = "text:abstract"
sdg = "b:name_impact"
targets = "material:targets"
question = "side"

[blocks.fill.side]
adt = "a:name_impact"
sdg = "b:name_impact"

[material.targets]
list = "b"
file = "impact_sdg_targets.json"
json_path = "targets"
key = "{json_key}"

[readout]
letters = ["Y", "N"]
layout = "single"

[budget]
max_tokens = 6000
retry_max_tokens = 20000

[id]
prefix = "p3.2"
blocks = ["SYSTEM", "USER_TEMPLATE", "Q_POS", "Q_NEG"]
json = { file = "impact_sdg_targets.json", path = "targets" }
```

### impact/p2

```toml
[question]
name = "impact/p2"
level = "work x list x list"
readout = "letter_logprob"
status = "record"
prompt_id = "p2-ed1dd92de43c"

[lists]
a = "adt"
b = "sdg"

[text]
fields = ["title", "abstract"]

[blocks]
files = ["p2.md"]
system = "SYSTEM"
user = "USER_TEMPLATE"

[[sides]]
name = "pos"
block = "Q_POS"

[[sides]]
name = "neg"
block = "Q_NEG"

[blocks.fill.system]

[blocks.fill.user]
title = "text:title"
abstract = "text:abstract"
question = "side"

[blocks.fill.side]
adt = "a:name_impact"
sdg = "b:name_impact"

[readout]
letters = ["Y", "N"]

[budget]
max_tokens = 1
top_logprobs = 20

[id]
prefix = "p2"
blocks = ["SYSTEM", "USER_TEMPLATE", "Q_POS", "Q_NEG"]
```

### impact/p2_reasoning

The [DV] reasoning layer: the blocks of `impact/p2`, answered after
reasoning, read from the message text ([DV] `labels_p3.py:1-7`, 219;
`params.yaml:80-108`). Its earlier id is the P2 hash under the prefix `p3`.
To replay [DV], the pass sets `budget_rule = "tokens"` and the model entries
carry the [DV] budgets (coder 6000 and 20000, gemma 4000 and 12000, gpt-oss
6000 and 20000).

```toml
[question]
name = "impact/p2_reasoning"
level = "work x list x list"
readout = "letter_text"
status = "record"
prompt_id = "p3-ed1dd92de43c"

[lists]
a = "adt"
b = "sdg"

[text]
fields = ["title", "abstract"]

[blocks]
files = ["../p2/p2.md"]
system = "SYSTEM"
user = "USER_TEMPLATE"

[[sides]]
name = "pos"
block = "Q_POS"

[[sides]]
name = "neg"
block = "Q_NEG"

[blocks.fill.system]

[blocks.fill.user]
title = "text:title"
abstract = "text:abstract"
question = "side"

[blocks.fill.side]
adt = "a:name_impact"
sdg = "b:name_impact"

[readout]
letters = ["Y", "N"]
layout = "single"

[budget]
max_tokens = 6000
retry_max_tokens = 20000

[id]
prefix = "p3"
blocks = ["SYSTEM", "USER_TEMPLATE", "Q_POS", "Q_NEG"]
```

### paper/adt_v1 (paper/sdg_v1 alike)

`paper/sdg_v1` differs only in `name`, `prompt_id = "sdg1-042b7b2c693f"`,
`a = "sdg"`, `files = ["paper_sdg_v1.md"]`, `letters = ["Y", "N"]`,
`table = "SDG"` and `prefix = "sdg1"`.

```toml
[question]
name = "paper/adt_v1"
level = "work"
readout = "letter_text"
fill = "replace"
status = "experimental"
prompt_id = "adt1-d95d2cfc8f17"

[lists]
a = "adt"

[text]
fields = ["title", "abstract"]

[blocks]
files = ["paper_adt_v1.md"]
system = "SYSTEM"
user = "USER_TEMPLATE"

[blocks.fill.system]

[blocks.fill.user]
title = "text:title"
abstract = "text:abstract"

[readout]
letters = ["E", "A", "T", "M", "N"]
layout = "table"
table = "ADT"

[budget]
max_tokens = 16000
retry_max_tokens = 32000

[id]
prefix = "adt1"
blocks = ["SYSTEM", "USER_TEMPLATE"]
```

### paper/impact_v1

```toml
[question]
name = "paper/impact_v1"
level = "work x list x list"
per_call = "work"
readout = "json_object"
status = "experimental"
prompt_id = "p3.2w-50ba3b728c25"

[lists]
a = "adt"
b = "sdg"

[text]
fields = ["title", "abstract"]

[blocks]
files = ["../../impact/p3_2/impact_p3_2.md", "impact_p3_2_work.md"]
system = "SYSTEM"
user = "USER_TEMPLATE"

[[sides]]
name = "pos"
block = "Q_POS"

[[sides]]
name = "neg"
block = "Q_NEG"

[blocks.fill.system]

[blocks.fill.user]
title = "text:title"
abstract = "text:abstract"
sdg = "b:name_impact"
targets = "material:targets"
question = "side"

[blocks.fill.side]
adt = "a:name_impact"
sdg = "b:name_impact"

[material.targets]
list = "b"
file = "../../impact/p3_2/impact_sdg_targets.json"
json_path = "targets"
key = "{json_key}"

[assembly]
kind = "impact_work_v1"
preamble = "PREAMBLE"
cut = "The goal is"

[readout]
form = "impact_pairs_v1"

[budget]
max_tokens = 32000
retry_max_tokens = 48000

[id]
prefix = "p3.2w"
blocks = ["PREAMBLE"]
inner = "impact/p3_2"
```
