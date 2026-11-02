"""Replay of protocol v1 then the impact question, as run in [WS] (contract 7.4, 8.3, 6.9).

The cache under tests/fixtures/protocol_impact/calls/ and the expected tables
under expected/ were written by the earlier code itself (make_oa.py for the
four protocol passes, make_ws.py for the impact pass) on four invented works
and scripted answers. Rebuilt from the cache alone, every table must equal
the earlier one, row for row, in the new columns.
"""

from __future__ import annotations

import hashlib
import json

import polars as pl
import pytest
from conftest import (
    FIXTURES,
    RUN_ID_RE,
    Endpoint,
    assert_table,
    copy_calls,
    frame_digest,
    never_called,
    output_of,
    read_json,
    works_frame,
    write_works,
)

import sdg_tech_impact_tagger as tagger

BASE = FIXTURES / "protocol_impact"
EXPECTED = BASE / "expected"

MODELS = """
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
"""

PROTOCOL_PASSES = """
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
__SDG2_EXTRA__

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
"""

IMPACT_PASS = """
[[passes]]
id = "impact"
question = "impact/p3_2"
models = ["coder", "gemma_thinking"]
attempts = 4
__IMPACT_EXTRA__
units = { rule = "cross", agreed_first = true, a = { from = "adt_pass2", models = ["gemma", "qwen3"], positive = ["E", "A", "T", "M"], combine = "union" }, b = { from = "sdg_pass2", models = ["gemma", "qwen3"], positive = ["Y"], combine = "union" } }

[passes.budgets.coder]
max_tokens = 6000
retry_max_tokens = 20000

[passes.budgets.gemma_thinking]
max_tokens = 4000
retry_max_tokens = 12000
"""

HEAD = """[run]
name = "protocol-v1-impact"
texts = "works.parquet"
cache_dir = "cache"
"""

TABLES = [
    ("sdg_pass1", "qwen3"),
    ("sdg_pass1", "gemma"),
    ("sdg_pass2", "qwen3"),
    ("sdg_pass2", "gemma"),
    ("adt_pass1", "gemma"),
    ("adt_pass1", "qwen3"),
    ("adt_pass2", "gemma"),
    ("adt_pass2", "qwen3"),
    ("impact", "coder"),
    ("impact", "gemma_thinking"),
]


def workflow_text(
    sdg2_extra: str = "", impact_extra: str = 'budget_rule = "tokens"'
) -> str:
    return (
        HEAD
        + MODELS
        + PROTOCOL_PASSES.replace("__SDG2_EXTRA__", sdg2_extra)
        + IMPACT_PASS.replace("__IMPACT_EXTRA__", impact_extra)
    )


def setup(tmp_path, text: str):
    copy_calls(BASE / "calls", tmp_path / "cache")
    write_works(tmp_path, "protocol_impact")
    path = tmp_path / "workflow.toml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def replayed(tmp_path_factory):
    """The whole 7.4 workflow replayed once from the earlier cache, no key, no network."""
    tmp_path = tmp_path_factory.mktemp("protocol")
    path = setup(tmp_path, workflow_text())
    results = tagger.run(
        tagger.load_workflow(path),
        replay=True,
        transport=Endpoint(never_called).transport,
    )
    return tmp_path, path, results


def test_results_in_pass_then_model_order(replayed):
    _, _, results = replayed
    assert [(r.pass_id, r.model) for r in results] == TABLES
    assert all(r.output_written and r.missing == [] for r in results)


@pytest.mark.parametrize(("pass_id", "model"), TABLES)
def test_table_equals_the_earlier_table(replayed, pass_id, model):
    tmp_path, _, results = replayed
    table = output_of(results, pass_id, model)
    assert_table(table, EXPECTED / f"{pass_id}__{model}.json")
    path = tmp_path / "runs" / "protocol-v1-impact" / pass_id / f"{model}.parquet"
    assert (
        next(r for r in results if (r.pass_id, r.model) == (pass_id, model)).output
        == path
    )


@pytest.mark.parametrize(
    ("pass_id", "model", "units"),
    [
        ("sdg_pass1", "qwen3", 4),
        ("sdg_pass2", "qwen3", 6),
        ("sdg_pass2", "gemma", 5),
        ("adt_pass2", "gemma", 6),
        ("adt_pass2", "qwen3", 4),
        ("impact", "coder", 7),
    ],
)
def test_unit_counts(replayed, pass_id, model, units):
    _, _, results = replayed
    result = next(r for r in results if (r.pass_id, r.model) == (pass_id, model))
    assert result.units == units
    assert result.chunks == 1 and result.written == [1]
    assert result.skipped_on_disk == [] and result.skipped_claimed == []


def test_run_record(replayed):
    tmp_path, _, results = replayed
    work = tmp_path / "runs" / "protocol-v1-impact" / "sdg_pass1" / "qwen3"
    text = (work / "run.json").read_text(encoding="utf-8")
    record = json.loads(text)
    assert text == json.dumps(record, indent=2, sort_keys=True) + "\n"
    assert set(record) == {
        "pass",
        "question",
        "model_entry",
        "model",
        "prompt_id",
        "run_id",
        "texts_sha256",
        "units",
        "units_sha256",
        "unit_rule",
        "chunk_size",
        "repeats",
    }
    assert record["pass"] == "sdg_pass1"
    assert record["question"] == "protocol_v1/sdg_pass1"
    assert record["model_entry"] == "qwen3" and record["model"] == "qwen3"
    assert record["prompt_id"] == "sdgp1-ca9ecbb1733d"
    assert (
        record["units"] == 4 and record["chunk_size"] == 1000 and record["repeats"] == 1
    )
    works = works_frame("protocol_impact")
    rows = [[r[0], r[1], r[2] if r[2] is not None else ""] for r in works.rows()]
    assert record["texts_sha256"] == frame_digest(rows)
    table = output_of(results, "sdg_pass1", "qwen3")
    assert record["run_id"] == table["run_id"][0]
    assert RUN_ID_RE.match(record["run_id"])


def test_run_record_per_label_ids(replayed):
    tmp_path, _, _ = replayed
    work = tmp_path / "runs" / "protocol-v1-impact" / "adt_pass2" / "gemma"
    record = json.loads((work / "run.json").read_text(encoding="utf-8"))
    assert "prompt_id" not in record
    expected = {
        line.split("\t")[1]: line.split("\t")[2]
        for line in (tagger_questions_ids())
        if line.startswith("protocol_v1/adt_pass2\t")
    }
    assert record["prompt_ids"] == expected


def tagger_questions_ids() -> list[str]:
    from conftest import QUESTIONS

    return (QUESTIONS / "IDS.tsv").read_text(encoding="utf-8").splitlines()


def test_run_ids_differ_between_passes_and_models(replayed):
    _, _, results = replayed
    run_ids = {
        (r.pass_id, r.model): pl.read_parquet(r.output)["run_id"][0] for r in results
    }
    assert len(set(run_ids.values())) == len(run_ids)


def test_manifest(replayed):
    tmp_path, path, results = replayed
    work = tmp_path / "runs" / "protocol-v1-impact" / "sdg_pass1" / "gemma"
    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    for key in (
        "package_version",
        "python_version",
        "started_at",
        "combined_at",
        "question_files",
        "lists",
        "model",
        "settings",
        "texts_sha256",
        "unit_rule",
        "sources",
        "model_changes",
        "cache_dir",
    ):
        assert key in manifest, key
    assert manifest["workflow"] == "protocol-v1-impact"
    assert manifest["workflow_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest["pass"] == "sdg_pass1"
    assert manifest["question"] == "protocol_v1/sdg_pass1"
    assert manifest["question_status"] == "record"
    assert manifest["prompt_id"] == "sdgp1-ca9ecbb1733d"
    assert manifest["run_id"] == output_of(results, "sdg_pass1", "gemma")["run_id"][0]
    assert manifest["endpoint"] == "https://conversation.ia.unistra.fr/api"
    assert manifest["replay"] is True
    assert manifest["model"]["api_key_env"] == "UNISTRA_API_KEY"
    assert manifest["model"]["model"] == "gemma"
    counts = manifest["counts"]
    # gemma's pass 1: four works, two of them unreadable (a boolean, a NaN).
    assert counts["units"] == 4
    assert counts["rows"] == 68
    assert counts["parse_failures"] == 34
    assert counts["retried"] == 0
    assert (
        counts["calls"] == 4
        and counts["cached_calls"] == 4
        and counts["fresh_calls"] == 0
    )
    assert counts["distinct_keys"] == 4
    table = output_of(results, "sdg_pass1", "gemma")
    per_call = table.unique("id")
    assert counts["tokens_in"] == per_call["tokens_in"].sum()
    assert counts["tokens_out"] == per_call["tokens_out"].sum()
    assert manifest["models_served"] == {"gemma-3-27b": 4}
    assert manifest["system_fingerprints"] == {"fp-g1": 4}
    from conftest import QUESTIONS

    directory = QUESTIONS / "protocol_v1" / "sdg_pass1"
    sums = {
        hashlib.sha256(p.read_bytes()).hexdigest()
        for p in directory.iterdir()
        if p.is_file()
    }
    values = set(manifest["question_files"].values())
    assert (
        hashlib.sha256((directory / "sdg_pass1.md").read_bytes()).hexdigest() in values
    )
    assert values <= sums
    sdg_list = QUESTIONS.parent / "lists" / "sdg.toml"
    assert manifest["lists"]["sdg"] == hashlib.sha256(sdg_list.read_bytes()).hexdigest()


def test_call_log(replayed):
    tmp_path, _, _ = replayed
    log = (
        tmp_path
        / "runs"
        / "protocol-v1-impact"
        / "impact"
        / "coder"
        / "calls"
        / "main.jsonl"
    )
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    # Seven units, two sides, two calls asked again with the larger budget.
    assert len(lines) == 16
    assert all(line["cached"] for line in lines)
    assert sum(line["retry"] for line in lines) == 2
    for line in lines:
        assert set(line) >= {
            "cache_key",
            "kind",
            "cached",
            "repeat",
            "retry",
            "model_served",
            "system_fingerprint",
            "finish_reason",
            "tokens_in",
            "tokens_out",
            "duration_ms",
            "parse_failure",
        }
        assert line["kind"] == "single_token"
        assert (
            tmp_path / "cache" / line["cache_key"][:2] / f"{line['cache_key']}.json"
        ).exists()


def test_workflow_record(replayed):
    tmp_path, _, _ = replayed
    record = json.loads(
        (tmp_path / "runs" / "protocol-v1-impact" / "workflow.json").read_text("utf-8")
    )
    assert "package_version" in json.dumps(record)


def test_replay_leaves_the_cache_unchanged(replayed):
    tmp_path, _, _ = replayed
    frozen = {
        p.relative_to(BASE / "calls"): p.read_bytes()
        for p in (BASE / "calls").rglob("*.json")
    }
    now = {
        p.relative_to(tmp_path / "cache"): p.read_bytes()
        for p in (tmp_path / "cache").rglob("*")
        if p.is_file()
    }
    assert now == frozen


# --------------------------------------------------------------------------
# read settings: the same cache read another way
# --------------------------------------------------------------------------


def only(tmp_path, text: str, passes: list[str], models: list[str] | None = None):
    path = setup(tmp_path, text)
    return tagger.run(
        tagger.load_workflow(path),
        replay=True,
        passes=passes,
        models=models,
        transport=Endpoint(never_called).transport,
    )


def test_exact_spelling_reads_the_earlier_cache_as_divergence_validation(tmp_path):
    text = workflow_text(sdg2_extra='spelling = "exact"')
    results = only(tmp_path, text, ["sdg_pass1", "sdg_pass2"], ["qwen3"])
    assert_table(
        output_of(results, "sdg_pass2", "qwen3"),
        EXPECTED / "sdg_pass2__qwen3__exact.json",
    )


def test_final_channel_extraction(tmp_path):
    text = workflow_text().replace(
        'reasoning_style = "omit"\ntimeout_s = 180.0\nconcurrency = 6\n\n[models.gemma]',
        'reasoning_style = "omit"\ntimeout_s = 180.0\nconcurrency = 6\nextraction = "final_channel"\n\n[models.gemma]',
    )
    assert 'extraction = "final_channel"' in text
    results = only(tmp_path, text, ["sdg_pass1", "sdg_pass2"], ["qwen3"])
    assert_table(
        output_of(results, "sdg_pass2", "qwen3"),
        EXPECTED / "sdg_pass2__qwen3__final_channel.json",
    )


def test_run_id_moves_with_a_read_setting_but_not_the_prompt_id(tmp_path):
    plain = only(tmp_path / "a", workflow_text(), ["sdg_pass1", "sdg_pass2"], ["qwen3"])
    exact = only(
        tmp_path / "b",
        workflow_text(sdg2_extra='spelling = "exact"'),
        ["sdg_pass1", "sdg_pass2"],
        ["qwen3"],
    )
    first, second = (output_of(r, "sdg_pass2", "qwen3") for r in (plain, exact))
    assert first["prompt_id"].to_list() == second["prompt_id"].to_list()
    assert first["run_id"][0] != second["run_id"][0]
    # Pass 1 is unchanged, so is its run id.
    assert (
        output_of(plain, "sdg_pass1", "qwen3")["run_id"][0]
        == output_of(exact, "sdg_pass1", "qwen3")["run_id"][0]
    )


def test_run_id_ignores_the_endpoint(tmp_path):
    other = workflow_text().replace(
        "https://conversation.ia.unistra.fr/api", "http://elsewhere.test/v1"
    )
    first = only(tmp_path / "a", workflow_text(), ["sdg_pass1"], ["qwen3"])
    second = only(tmp_path / "b", other, ["sdg_pass1"], ["qwen3"])
    assert (
        output_of(first, "sdg_pass1", "qwen3")["run_id"][0]
        == output_of(second, "sdg_pass1", "qwen3")["run_id"][0]
    )


def test_default_budget_rule_asks_a_call_the_earlier_rule_did_not(tmp_path):
    """Contract 4.4: a reply cut by the server below its budget is spent under the
    default rule only; the earlier cache has no such call, so replay misses."""
    with pytest.raises(tagger.CacheMiss):
        only(tmp_path, workflow_text(impact_extra=""), ["impact"], ["coder"])


def test_recorded_prefix_writes_the_recorded_id(tmp_path):
    text = workflow_text(impact_extra='budget_rule = "tokens"\nprompt_prefix = "p3.1"')
    results = only(tmp_path, text, None)
    assert_table(
        output_of(results, "impact", "coder"),
        EXPECTED / "impact__coder.json",
        prompt_id="p3.1-f72f01757eef",
    )


def test_unrecorded_prefix_is_refused(tmp_path):
    text = workflow_text(impact_extra='budget_rule = "tokens"\nprompt_prefix = "p9"')
    path = setup(tmp_path, text)
    # Contract 3.5: the id under another prefix must be one of recorded_ids.
    with pytest.raises((tagger.WorkflowError, tagger.QuestionError)):
        tagger.load_workflow(path)


def test_a_pass_not_run_is_read_from_its_output(tmp_path):
    path = setup(tmp_path, workflow_text())
    workflow = tagger.load_workflow(path)
    first = tagger.run(
        workflow,
        replay=True,
        passes=["sdg_pass1", "sdg_pass2", "adt_pass1", "adt_pass2"],
        transport=Endpoint(never_called).transport,
    )
    assert len(first) == 8
    [coder] = tagger.run(
        workflow,
        replay=True,
        passes=["impact"],
        models=["coder"],
        transport=Endpoint(never_called).transport,
    )
    assert_table(pl.read_parquet(coder.output), EXPECTED / "impact__coder.json")


def test_plan_order_of_the_impact_pass(tmp_path, key_env):
    """Agreed units first, each part by id then code ([WS] impact_pass.py:172-206);
    calls in plan order, the two sides of a unit adjacent (contract 5)."""
    path = setup(
        tmp_path, workflow_text().replace("UNISTRA_API_KEY", "TAGGER_TEST_KEY")
    )
    workflow = tagger.load_workflow(path)
    tagger.run(
        workflow,
        replay=True,
        passes=["sdg_pass1", "sdg_pass2", "adt_pass1", "adt_pass2"],
        transport=Endpoint(never_called).transport,
    )
    record = json.loads(
        (
            tmp_path
            / "runs"
            / "protocol-v1-impact"
            / "adt_pass2"
            / "gemma"
            / "run.json"
        ).read_text()
    )
    assert record["unit_rule"]["rule"] == "threshold"
    # Live, with an empty cache for the impact pass and one call at a time.
    (tmp_path / "cache").rename(tmp_path / "cache_protocol")
    text = path.read_text(encoding="utf-8").replace(
        "concurrency = 8", "concurrency = 1"
    )
    path.write_text(text + '\n[passes.cache_dirs]\ncoder = "fresh"\n', encoding="utf-8")
    endpoint = Endpoint(
        lambda payload, n: {
            "model": "coder",
            "choices": [{"message": {"content": "N"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    )
    tagger.run(
        tagger.load_workflow(path),
        passes=["impact"],
        models=["coder"],
        transport=endpoint.transport,
    )
    plan = read_json(BASE / "impact_plan.json")
    adt_names = {
        "AI": "artificial intelligence",
        "COMPUTING_INFRASTRUCTURE": "computing infrastructure",
        "ADDITIVE_MANUFACTURING": "additive manufacturing",
    }
    sdg_names = {
        "SDG-03": "SDG 3, good health",
        "SDG-07": "SDG 7, affordable",
        "SDG-13": "SDG 13, climate",
    }
    titles = {"w-003": "Kestrel", "w-010": "Basalt"}
    asked = []
    for user in endpoint.users():
        side = "pos" if "make a beneficial claim" in user else "neg"
        work = next(w for w, marker in titles.items() if f"Title: {marker}" in user)
        adt = next(
            code for code, name in adt_names.items() if f"Pair: {name} and" in user
        )
        sdg = next(
            code for code, name in sdg_names.items() if f"The goal is {name}" in user
        )
        asked.append((work, f"{adt}|{sdg}", side))
    assert asked == [
        (work, code, side) for work, code in plan for side in ("pos", "neg")
    ]
