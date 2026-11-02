# Journal

## 2026-11-02 17:00  The repository is set up
Done: surveyed the labelling code of the earlier repositories (client,
prompts, passes, unit rules, readouts, caches) and the practice of
declarative annotation pipelines; Kevin settled the design questions,
recorded as D001 to D015. Wrote AGENTS.md, CONTEXT.md, the licence and the
package skeleton.
Tests added: none.
Open / unsure: the contract (`docs/contract.md`) is next.

## 2026-11-02 17:38  The tests are written from the contract
Done: wrote the test suite the implementation is built against, from
docs/contract.md and D001 to D018. Behaviour carried over from the earlier
repositories is checked against values computed by their own code on
invented works and invented model answers, frozen under tests/fixtures/ by
tests/fixtures/make/ (make_all.sh runs make_oa.py, make_ws.py and make_dv.py
with each repository's own interpreter, read-only; a second run gives
byte-identical fixtures). Behaviour new to the package is tested from the
contract alone. No test reaches a network: live runs go through
`run(transport=httpx.MockTransport)`, replays through hand-made or frozen
caches. pyproject.toml gains the `slow` marker and `pythonpath = ["tests"]`
(pytest 9 no longer puts tests/ on the path for `from conftest import`).
`uv run pytest -q`: 542 collected, 486 failed and 50 errors on the missing
package (AttributeError on `tagger.<name>`, ImportError of
`sdg_tech_impact_tagger.client`, missing presets and entry point), 1 passed,
5 skipped for the questions below.
Tests added: test_questions (107), test_lists (14), test_cache_and_wire (21),
test_client (17), test_readouts (95), test_unit_rules (54), test_runs (51),
test_workflow (109), test_replay_protocol (33), test_replay_paper (14),
test_command (27, one marked slow). Oracle-derived fixtures: rendered texts
of every shipped question (render/), the wire body, cache key and cache file
text of the four kinds of call (wire.json), the protocol v1 tables of both
models and their cache, the impact P3.2 tables of coder and gemma_thinking,
the paper-v1 tables and cache, the [DV] impact/p2 and p2_reasoning tables
and cache (exact spelling, null abstract sent as None), threshold, cross and
file unit selections and orders (units/), the shipped list labels
(lists.json).
Left to the implementer, which the tests need: the question.toml of every
shipped question (Appendix A) and their lines in questions/SHA256SUMS,
lists/sdg.toml, lists/adt.toml and lists/SHA256SUMS, presets/*.toml, and the
`[project.scripts]` entry point `sdg-tech-impact-tagger`.
Open / unsure: questions for Kevin, each test loosened or skipped where
named.
1. 3.6: the run id's `readout` value (the name alone, or with layout or
   form), and what `top_logprobs` and `response_format` hold for letter_text
   and json_object. Only its properties are tested (format, equal in rows,
   run.json and manifest, moved by a read setting, not by the endpoint);
   test_run_id_exact_value is skipped.
2. 10.1: what `render(texts, units=())` returns at a list level. Units are
   always passed at list levels.
3. 8.2: whether `impact_pairs_v1` follows the sides rule for its columns.
   The tests follow the readout table and the [WS] table (8.3).
4. 8.2 and 9: model_served when one call of a row gives no model; how a null
   counts in models_served. Skipped (test_model_served_of_sides_with_one_null).
5. 6.7: the key columns of units_sha256. Skipped (test_units_sha256_value).
6. 9: whether question_files lists question.toml itself. Asserted loosely.
7. 3.5: the exception for a prompt_prefix outside recorded_ids
   (WorkflowError or QuestionError both accepted).
8. 3.1 says every file under questions/ is in SHA256SUMS, but IDS.tsv is
   not listed. The test exempts IDS.tsv.
9. 7.5: protocol-v1's pass ids and its client settings (timeout_s,
   concurrency) are not given; only questions, models, thresholds and the
   keys that change an answer are tested. paper-v1: whether 16000/32000 and
   32000/48000 are per pass or per model; not asserted (the paper replay
   checks the budgets through the cache keys). Side models assumed in the
   order coder, gemma; pass ids paper_adt, paper_sdg, paper_impact.
10. 9: `counts.parse_failures` read as a number of rows.
11. 4.5: quotes_ok per label row or for the whole reply. Skipped
    (test_label_object_quotes_ok_scope); the row of the bad quote is false
    either way.
12. 4.5 and 8.2: columns and dtypes of an answer model's fields. Skipped
    (test_answer_model_columns).
13. 4.5: the type schemas of string, boolean, integer and number fields are
    read as the JSON Schema names (`string`, `boolean`, `integer`,
    `number`).
14. 4.2 and 3.3: may a score_json question carry retry_max_tokens? The test
    accepts a refusal at load or no retry.
15. Exception types not given: a bad worker name (6.6; TaggerError or
    ValueError accepted), bad letters (4.3; QuestionError assumed), a pass
    reading a missing output under `passes` (10.1; TaggerError), neither or
    both of path and preset (10.1; WorkflowError, TypeError or ValueError),
    no texts at all (7.2; WorkflowError or TextsError), an optional field in
    an answer model (4.5; TaggerError).
16. 6.1 and 6.8: does `combine_only` without `replay` read the key? The
    command test passes `--replay` with `--combine-only`.
17. 10.2: which call `prompt` prints for a question with sides; the test
    asks that the first side's system and user texts appear.
18. 3.4: whether `[[OPEN` in a work's own text refuses the run ("filled
    system or user text"). Only a marker in a block is tested.
19. 5: `positive = ["OTHER"]` is taken as allowed ("OTHER counts only if
    listed") though OTHER is not a letter of the source question.

## 2026-11-02 17:52  The tests follow the contract clarifications (D019)
Done: tightened the tests to docs/contract.md section 13. The five skipped
tests now run with exact expectations. The run id is checked against the two
values of 3.6 (run-5295f828ba65, run-da78be5306bb, both reproduced from the
19-key record by `conftest.contract_run_id`) and by the formula for the
other letter passes of 7.4, the four wire cases, the table and retry
letter_text, and label_object with declared fields or an answer model.
quotes_ok is per label row. The answer-model columns and types are checked.
model_served is checked over sides with a null, and models_served counts
nulls under "". units_sha256 is exact at level work, for threshold units
and for cross units. Exception types are now single, per 3.3, 4.5, 10.1
and 11. question_files is exact. `prompt` output is exact, sides included.
The three presets are compared in full with 7.5 (protocol-v1-impact is 7.4
without texts). New tests: render at list levels and its refusals,
manifest counts and file format, positive OTHER allowed, `[[OPEN` in
blocks and any label's material refused at load and in a work's text sent
as it is, retry_max_tokens and top_logprobs refused where the readout has
no use for them, budgets keys checked per readout, and restrictions that
name nothing refused. `served_of` in the fixture scripts now reads an empty
string as null (4.1). The fixtures regenerate byte-identical. No
clarification contradicts a frozen fixture: the paper cache was already
made with coder sending no thinking flag and the label passes retried
under the length rule.
`uv run pytest -q`: 616 collected, 554 failed and 60 errors on the missing
package, 2 passed, none skipped.
Tests added: 74 (questions 124, readouts 112, workflow 118, unit_rules 61,
runs 59, replay_protocol 43, command 30, cache_and_wire 24, client 17,
lists 14, replay_paper 14).
Open / unsure: one type is still not named. The contract does not say
whether a source with repeats > 1 is refused as WorkflowError or as
UnitsError (5), so test_cross_source_with_repeats_is_refused accepts
either.

## 2026-11-02 18:19  Implementation of the package against the tests
Done: wrote the package under src/ from docs/contract.md, against the
committed tests, which were not edited. The ten question.toml files of
Appendix A (impact/p2_reasoning a new directory), their lines in
questions/SHA256SUMS (the lines of the imported files unchanged), the sdg
and adt lists with lists/SHA256SUMS, and the three presets copied from 7.4
and 7.5. Modules: blocks and the prompt id rule (every shipped id
reproduced), questions (strict question.toml, filling, impact_work_v1),
lists, client (cache key and file of [OA], retries, batches,
expect_model, injectable transport), readouts, workflow (strict pydantic,
every refusal of section 7 at load), units (all, threshold, cross, file),
runner (chunks, claims, sub-chunks and attempts, budget retry batch, run
id, run.json, combine, call logs, manifest, workflow.json) and the
command with run, check, prompt and preset, installed by
[project.scripts]. Ruff check and format clean.
`uv run pytest -q`, slow included: 616 collected, 614 passed, 2 failed.
Tests added: none (implementation session).
Open / unsure: two tests disagree with the contract and are left failing.
(1) test_readouts.py::test_label_object_one_bad_item_fails_the_reply[not
an object] expects the reply `[{...}]` to be unreadable. Contract 4.5
reads label_object replies from the first `{` to the last `}` ([WS]
paper_pass.py:389-395, which does the same), so the span is the inner
object, which holds every label with its fields, and the reply reads. A
case that is not an object under that rule (a bare string, a number)
would test what the case means; or the contract changes the reading.
(2) test_replay_protocol.py::test_default_budget_rule_asks_a_call_the_
earlier_rule_did_not runs passes=["impact"] alone in a fresh directory
and expects CacheMiss. No protocol pass has written its table there, so
the cross rule cannot read its sources; 10.1 says a missing source table
is a UnitsError naming its path, which is what is raised. Run with every
pass (passes=None, as test_recorded_prefix_writes_the_recorded_id does),
the impact pass is reached and misses the cache as expected.
Choices made where the contract is silent, none changing what a pass
returns: a block name found in two files of one question is refused
(QuestionError); a [readout] key the readout does not take is refused; a
source pass with repeats > 1 is refused at load (WorkflowError) for
threshold, cross and file flags; an item of a label_object reply may hold
keys beyond the declared fields (they are ignored, as Pydantic ignores
them for an answer model); file flags are taken only at level
work x list x list; `--cache-dir` replaces [run].cache_dir and leaves a
pass's [passes.cache_dirs] as written; a restriction naming any pass or
model not in the workflow is refused, not only one naming nothing; limit
below 1 is a WorkflowError; workflow.json is written once the first
(pass, model) is planned, so a refusal before planning writes nothing;
model_changes in the manifest is computed from the call logs of every
worker, in log order; `check` prints the run id of a pass whose sources
are not on disk yet, with the sources it waits on in place of a count.

## 2026-11-02 18:31  Two tests that contradicted the contract are fixed
Done: checked the two failures the implementation session reported
against docs/contract.md, not against the code; in both the implementer
is right. (1) 4.5 reads a label_object reply from its first `{` to its
last `}`, so `[{...}]` is the inner object and reads; the case is now two
objects in a list, whose span `{...}, {...}` does not load. (2) 10.1 makes
a missing source table a UnitsError; the default-budget-rule test now runs
every pass, so the impact pass reaches the call the earlier cache lacks
and raises CacheMiss. `uv run pytest -q`, slow included: 616 passed. The
52 warnings are the ModelChangeWarnings the fixture answers cause on
purpose.
Tests added: none; two changed.
Open / unsure: none of the implementer's choices in the entry of 18:19
contradicts the contract. Three of them go beyond its text and are for
Kevin to confirm. (a) A `passes` or `models` restriction naming any name
not in the workflow is refused; 10.1 names only a restriction naming
nothing. (b) Keys beyond the declared fields of a label_object item are
ignored; 4.5 says each item holds every field with its type, while the
schema it sends has additionalProperties false. (c) File flags are taken
only at level work x list x list; 5 does not say.

## 2026-11-02 18:39  Replay of the earlier runs from their caches
Done: replayed, with `run(..., replay=True)`, the earlier tables of
wos_paper_sample and of the open_alex_adt_gate recall sample, each from
its own caches read in place (`[passes.cache_dirs]`) and from the
documents file its run.json names, in its order. Slices of the first 200
works first, then every table in full. Workflows, outputs and comparison
scripts outside the repository. Compared by 8.3 on (id, code): every
compared column (label, score, p_* to 1e-12, source_score as
pass1_score, relevant, flags, pos/neg labels, retried, tokens,
parse_failure, model, prompt_id, arm, batch_id).

| table | earlier rows | replayed | identical | differing | misses |
|---|---|---|---|---|---|
| WS sdg_pass1 qwen3 / gemma | 2,134,486 each | same | all | 0 | 0 |
| WS sdg_pass2 qwen3 | 386,784 | 386,784 | all | 0 | 0 |
| WS sdg_pass2 gemma | 426,345 | 426,345 | all | 0 | 0 |
| WS adt_pass1 gemma / qwen3 | 753,348 each | same | all | 0 | 0 |
| WS adt_pass2 gemma | 163,255 | 163,255 | all | 0 | 0 |
| WS adt_pass2 qwen3 | 130,115 | 130,115 | all | 0 | 0 |
| WS impact_p3_2 coder / gemma | 307,231 each | same | all | 0 | 0 |
| WS paper_adt coder | 753,348 | 753,348 | all | 0 | 0 |
| WS paper_sdg coder | 2,134,486 | 2,134,486 | all | 0 | 0 |
| OA recall sdg_pass1 qwen3 / gemma | 5,100,017 each | same | all | 0 | 0 |
| OA recall sdg_pass2 qwen3 | 526,799 | 526,799 | all | 0 | 0 |
| OA recall sdg_pass2 gemma | 587,207 | 587,207 | all | 0 | 0 |
| OA recall adt_pass1 qwen3 / gemma | 1,800,006 each | same | all | 0 | 0 |
| OA recall adt_pass2 qwen3 | 39,941 | 39,941 | all | 0 | 0 |
| OA recall adt_pass2 gemma | 61,949 | 61,949 | all | 0 | 0 |

No key only on one side, no repeated key, no cache miss: every call was
read from the cache (fresh_calls 0 in every manifest). The impact pass
read 53 budget retries for coder and 4,184 rows with a retry for gemma
from the cache under budget_rule "tokens". texts_sha256 and
units_sha256 of every run.json equal the documents_sha256 and
units_sha256 of the earlier run.json (WS documents 0416bcea95aa, OA
recall d57e01c87916), so texts, order and units are those of the
earlier runs. Full replay times: WS about 16 min, OA about 13 min.
Not replayed: WS paper_impact (gemma's paper label tables are not on
disk, and the cross reads both models). divergence-validation labels_p2
(gemma, mistral-small) and labels_p3: the call caches
data/cache/llm_p2 and llm_p3 are not on this machine (empty data/cache;
they are on the home server's DVC remote) and were not fetched. Counts:
labels_p2 51,044 rows per model (gemma, mistral-small, gpt-oss; the
51,044 gpt-oss rows are the ones D017 says do not replay); labels_p3
51,044 per model (coder, gemma, gpt-oss); 25,522 triples, 20,823 works,
one text per work, no null title or abstract, so null_text does not
matter there.
Tests added: none.
Open / unsure: the divergence-validation replay waits on its caches
being copied to this machine.
