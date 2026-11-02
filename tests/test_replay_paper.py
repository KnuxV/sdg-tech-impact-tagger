"""Replay of the paper preset (contract 7.5, 8.4) and of the [DV] layers of impact/p2.

paper/: the cache and tables of the [WS] paper passes (make_ws.py): labels read
from a table in the reply (letter_text, layout table), asked again when cut
at their budget (`budget_rule = "length"`), then one call per work over every
triple of the work (json_object, impact_pairs_v1, assembly impact_work_v1).

dv/: the [DV] logprob layer (impact/p2, exact spelling, a null abstract sent
as `None`) and reasoning layer (impact/p2_reasoning, the [DV] budget rule)
over a file of units (make_dv.py).
"""

from __future__ import annotations

import shutil

import polars as pl
import pytest
from conftest import (
    FIXTURES,
    Endpoint,
    assert_table,
    copy_calls,
    never_called,
    output_of,
    write_works,
)

import sdg_tech_impact_tagger as tagger

PAPER = FIXTURES / "paper"
DV = FIXTURES / "dv"

PAPER_TABLES = [
    ("paper_adt", "coder"),
    ("paper_adt", "gemma"),
    ("paper_sdg", "coder"),
    ("paper_sdg", "gemma"),
    ("paper_impact", "coder"),
    ("paper_impact", "gemma"),
]


@pytest.fixture(scope="module")
def paper_replayed(tmp_path_factory):
    """The preset paper-v1, read against the current directory, from the [WS] cache."""
    tmp_path = tmp_path_factory.mktemp("paper")
    copy_calls(PAPER / "calls", tmp_path / "cache")
    write_works(tmp_path, "paper")
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(tmp_path)
        workflow = tagger.load_workflow(preset="paper-v1")
        results = tagger.run(
            workflow,
            texts="works.parquet",
            replay=True,
            transport=Endpoint(never_called).transport,
        )
    return tmp_path, results


def test_paper_results(paper_replayed):
    _, results = paper_replayed
    assert [(r.pass_id, r.model) for r in results] == PAPER_TABLES


@pytest.mark.parametrize(("pass_id", "model"), PAPER_TABLES)
def test_paper_table_equals_the_earlier_table(paper_replayed, pass_id, model):
    _, results = paper_replayed
    assert_table(
        output_of(results, pass_id, model),
        PAPER / "expected" / f"{pass_id}__{model}.json",
    )


def test_paper_outputs_under_the_current_directory(paper_replayed):
    tmp_path, results = paper_replayed
    for result in results:
        assert result.output.resolve().is_relative_to(tmp_path.resolve())
        assert result.output.name == f"{result.model}.parquet"
        assert result.output.parent.name == result.pass_id


def test_paper_texts_as_a_frame(tmp_path, monkeypatch):
    copy_calls(PAPER / "calls", tmp_path / "cache")
    monkeypatch.chdir(tmp_path)
    from conftest import works_frame

    workflow = tagger.load_workflow(preset="paper-v1")
    results = tagger.run(
        workflow,
        texts=works_frame("paper"),
        replay=True,
        passes=["paper_adt"],
        models=["coder"],
        transport=Endpoint(never_called).transport,
    )
    assert_table(
        output_of(results, "paper_adt", "coder"),
        PAPER / "expected" / "paper_adt__coder.json",
    )


# --------------------------------------------------------------------------
# divergence-validation, impact/p2 and impact/p2_reasoning on a file of units
# --------------------------------------------------------------------------

DV_WORKFLOW = """
[run]
name = "dv"
texts = "works.parquet"
cache_dir = "cache"

[models.gemma]
endpoint = "https://conversation.ia.unistra.fr/api"
api_key_env = "UNISTRA_API_KEY"
model = "gemma"
seed = 42
reasoning = "off"
reasoning_style = "omit"

[models.mistral_small]
endpoint = "https://conversation.ia.unistra.fr/api"
api_key_env = "UNISTRA_API_KEY"
model = "mistral-small"
seed = 42
reasoning = "off"
reasoning_style = "omit"

[models.gemma_thinking]
endpoint = "https://conversation.ia.unistra.fr/api"
api_key_env = "UNISTRA_API_KEY"
model = "gemma"
seed = 42
reasoning = "on"
reasoning_style = "enable_thinking"

[[passes]]
id = "p2"
question = "impact/p2"
models = ["gemma", "mistral_small"]
units = { rule = "file", path = "units.csv" }
spelling = "exact"
null_text = "None"

[[passes]]
id = "p2_reasoning"
question = "impact/p2_reasoning"
models = ["gemma_thinking"]
units = { rule = "file", path = "units.csv" }
budget_rule = "tokens"
null_text = "None"

[passes.budgets.gemma_thinking]
max_tokens = 4000
retry_max_tokens = 12000
"""


@pytest.fixture(scope="module")
def dv_replayed(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("dv")
    copy_calls(DV / "calls", tmp_path / "cache")
    write_works(tmp_path, "dv")
    shutil.copy(DV / "units.csv", tmp_path / "units.csv")
    (tmp_path / "workflow.toml").write_text(DV_WORKFLOW, encoding="utf-8")
    workflow = tagger.load_workflow(tmp_path / "workflow.toml")
    return tmp_path, tagger.run(
        workflow, replay=True, transport=Endpoint(never_called).transport
    )


@pytest.mark.parametrize(
    ("pass_id", "model", "fixture"),
    [
        ("p2", "gemma", "p2__gemma"),
        ("p2", "mistral_small", "p2__mistral_small"),
        ("p2_reasoning", "gemma_thinking", "p2_reasoning__gemma"),
    ],
)
def test_dv_table_equals_the_earlier_rows(dv_replayed, pass_id, model, fixture):
    _, results = dv_replayed
    assert_table(
        output_of(results, pass_id, model), DV / "expected" / f"{fixture}.json"
    )


def test_dv_null_text_changes_the_request(tmp_path):
    """Without `null_text = "None"` the null abstract is sent as "" and misses the [DV] cache."""
    copy_calls(DV / "calls", tmp_path / "cache")
    write_works(tmp_path, "dv")
    shutil.copy(DV / "units.csv", tmp_path / "units.csv")
    (tmp_path / "workflow.toml").write_text(
        DV_WORKFLOW.replace('null_text = "None"\n', "", 1), encoding="utf-8"
    )
    with pytest.raises(tagger.CacheMiss):
        tagger.run(
            tagger.load_workflow(tmp_path / "workflow.toml"),
            replay=True,
            passes=["p2"],
            models=["gemma"],
            transport=Endpoint(never_called).transport,
        )


def test_dv_sum_spelling_differs_from_exact(tmp_path):
    copy_calls(DV / "calls", tmp_path / "cache")
    write_works(tmp_path, "dv")
    shutil.copy(DV / "units.csv", tmp_path / "units.csv")
    (tmp_path / "workflow.toml").write_text(
        DV_WORKFLOW.replace('spelling = "exact"\n', ""), encoding="utf-8"
    )
    [result] = tagger.run(
        tagger.load_workflow(tmp_path / "workflow.toml"),
        replay=True,
        passes=["p2"],
        models=["mistral_small"],
        transport=Endpoint(never_called).transport,
    )
    table = pl.read_parquet(result.output)
    row = table.filter(pl.col("code") == "ADDITIVE_MANUFACTURING|SDG-03").row(
        0, named=True
    )
    # Spelled " Y" and " N" only: no letter under the exact reading, both under the sum.
    assert row["pos_label"] == "Y"
    assert row["pos_p_y"] is not None and row["pos_p_y"] > 0.5
