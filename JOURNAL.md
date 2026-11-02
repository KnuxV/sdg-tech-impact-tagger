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
