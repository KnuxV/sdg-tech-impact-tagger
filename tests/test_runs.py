"""Runs: chunks, workers, resume, combine, restrictions and the texts table.

Contract 2.1, 6.6 to 6.8, 9 and 10.1. The chunk files, claims and the
result fields are those of [OA] `llm_passes.py` (`_run_chunks`, `_result`:
`units` and `chunks` are counts, the other four lists of chunk indices).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import polars as pl
import pytest
from conftest import (
    TEXTS,
    Endpoint,
    chat,
    model_entry,
    never_called,
    score_question,
    write_question,
    write_texts,
    write_workflow,
)

import sdg_tech_impact_tagger as tagger

GOOD = '{"RED": 10, "GREEN": 20, "BLUE": 30}'


def answer(payload, n):
    return chat(GOOD)


def project(
    tmp_path,
    *,
    pass_extra="chunk_size = 1",
    models='["m1"]',
    texts=TEXTS,
    run_extra="",
    model_extra="",
):
    write_texts(tmp_path, texts)
    score_question(tmp_path / "q")
    body = (
        model_entry("m1", model="m1", extra=model_extra)
        + model_entry("m2", model="m2")
        + (
            f'[[passes]]\nid = "p"\nquestion_dir = "q"\nmodels = {models}\n'
            f'units = {{ rule = "all" }}\n{pass_extra}\n'
        )
    )
    return write_workflow(tmp_path, body, run_extra=run_extra)


def work_dir(tmp_path, pass_id="p", model="m1"):
    return tmp_path / "runs" / "wf" / pass_id / model


def first_words(endpoint):
    return [u.split("\n")[0].removeprefix("Text: ") for u in endpoint.users()]


# --------------------------------------------------------------------------
# the result and the files of a run
# --------------------------------------------------------------------------


def test_result_of_a_full_run(tmp_path, key_env):
    path = project(tmp_path)
    [result] = tagger.run(
        tagger.load_workflow(path), transport=Endpoint(answer).transport
    )
    assert result.pass_id == "p" and result.model == "m1"
    assert result.units == 3 and result.chunks == 3
    assert list(result.written) == [1, 2, 3]
    assert list(result.skipped_on_disk) == []
    assert list(result.skipped_claimed) == []
    assert list(result.missing) == []
    assert result.output_written is True
    assert (
        result.output.resolve()
        == (tmp_path / "runs" / "wf" / "p" / "m1.parquet").resolve()
    )
    chunks = work_dir(tmp_path) / "chunks"
    assert sorted(p.name for p in chunks.iterdir()) == [
        "chunk_00001.parquet",
        "chunk_00002.parquet",
        "chunk_00003.parquet",
    ]
    assert not list(work_dir(tmp_path).parent.rglob("*.partial"))


def test_units_in_table_order_one_chunk_each(tmp_path, key_env):
    endpoint = Endpoint(answer)
    tagger.run(tagger.load_workflow(project(tmp_path)), transport=endpoint.transport)
    assert first_words(endpoint) == [
        "Red kite été {abstract}",
        "Green tea",
        "Blue whale",
    ]
    chunk_ids = [
        pl.read_parquet(work_dir(tmp_path) / "chunks" / f"chunk_0000{i}.parquet")["id"]
        .unique()
        .to_list()
        for i in (1, 2, 3)
    ]
    assert chunk_ids == [["b2"], ["a1"], ["c3"]]


def test_a_second_run_finds_the_chunks_on_disk(tmp_path, key_env):
    workflow = tagger.load_workflow(project(tmp_path))
    [first] = tagger.run(workflow, transport=Endpoint(answer).transport)
    table = pl.read_parquet(first.output)
    [again] = tagger.run(workflow, transport=Endpoint(never_called).transport)
    assert list(again.written) == [] and list(again.skipped_on_disk) == [1, 2, 3]
    assert again.output_written
    assert pl.read_parquet(again.output).equals(table)


def test_reverse_visits_the_chunks_from_the_last(tmp_path, key_env):
    endpoint = Endpoint(answer)
    [result] = tagger.run(
        tagger.load_workflow(project(tmp_path)),
        reverse=True,
        transport=endpoint.transport,
    )
    assert first_words(endpoint) == [
        "Blue whale",
        "Green tea",
        "Red kite été {abstract}",
    ]
    assert list(result.written) == [3, 2, 1]
    # Outputs are sorted whatever the plan order.
    assert pl.read_parquet(result.output)["id"].unique(
        maintain_order=True
    ).to_list() == ["a1", "b2", "c3"]


def test_chunk_size_cuts_the_plan(tmp_path, key_env):
    path = project(tmp_path, pass_extra="chunk_size = 2")
    [result] = tagger.run(
        tagger.load_workflow(path), transport=Endpoint(answer).transport
    )
    assert result.chunks == 2 and list(result.written) == [1, 2]
    second = pl.read_parquet(work_dir(tmp_path) / "chunks" / "chunk_00002.parquet")
    assert second["id"].unique().to_list() == ["c3"]


# --------------------------------------------------------------------------
# claims and workers
# --------------------------------------------------------------------------


def claim(tmp_path, index, worker):
    chunks = work_dir(tmp_path) / "chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    (chunks / f"chunk_{index:05d}.claim").write_text(worker, encoding="utf-8")


def test_a_chunk_claimed_by_another_worker_is_skipped(tmp_path, key_env):
    workflow = tagger.load_workflow(project(tmp_path))
    claim(tmp_path, 2, "other")
    endpoint = Endpoint(answer)
    [result] = tagger.run(workflow, transport=endpoint.transport)
    assert first_words(endpoint) == ["Red kite été {abstract}", "Blue whale"]
    assert list(result.written) == [1, 3]
    assert list(result.skipped_claimed) == [2]
    assert list(result.missing) == [2]
    assert result.output_written is False
    assert not (tmp_path / "runs" / "wf" / "p" / "m1.parquet").exists()
    # The other worker finds its own claim and finishes the run.
    [other] = tagger.run(workflow, worker="other", transport=Endpoint(answer).transport)
    assert list(other.written) == [2]
    assert list(other.skipped_on_disk) == [1, 3]
    assert other.output_written is True
    assert not (work_dir(tmp_path) / "chunks" / "chunk_00002.claim").exists()


def test_a_claim_holding_its_own_name_is_its_own(tmp_path, key_env):
    workflow = tagger.load_workflow(project(tmp_path))
    claim(tmp_path, 1, "main")
    [result] = tagger.run(workflow, transport=Endpoint(answer).transport)
    assert list(result.written) == [1, 2, 3] and result.output_written


@pytest.mark.parametrize("worker", ["", "two words", "a/b", "x" * 65, "é"])
def test_worker_name_is_checked(tmp_path, key_env, worker):
    workflow = tagger.load_workflow(project(tmp_path))
    with pytest.raises((tagger.TaggerError, ValueError)):
        tagger.run(workflow, worker=worker, transport=Endpoint(never_called).transport)


def test_worker_name_of_64_characters(tmp_path, key_env):
    workflow = tagger.load_workflow(project(tmp_path))
    [result] = tagger.run(
        workflow, worker="w-_9" * 16, transport=Endpoint(answer).transport
    )
    assert result.output_written


# --------------------------------------------------------------------------
# run.json and resume (6.7)
# --------------------------------------------------------------------------


def test_run_json_differs(tmp_path, key_env):
    tagger.run(
        tagger.load_workflow(project(tmp_path)), transport=Endpoint(answer).transport
    )
    record = json.loads((work_dir(tmp_path) / "run.json").read_text(encoding="utf-8"))
    assert record["chunk_size"] == 1 and record["units"] == 3
    changed = tagger.load_workflow(project(tmp_path, pass_extra="chunk_size = 2"))
    with pytest.raises(tagger.ManifestMismatch) as info:
        tagger.run(changed, limit=2, transport=Endpoint(never_called).transport)
    lines = [line for line in str(info.value).splitlines() if " on disk, " in line]
    assert "chunk_size: 1 on disk, 2 now" in lines
    assert "units: 3 on disk, 2 now" in lines
    keys = [line.split(":")[0] for line in lines]
    assert keys == sorted(keys)
    assert set(keys) == {"chunk_size", "texts_sha256", "units", "units_sha256"}


def test_settings_outside_run_json_do_not_stop_a_resume(tmp_path, key_env):
    tagger.run(
        tagger.load_workflow(project(tmp_path)), transport=Endpoint(answer).transport
    )
    (tmp_path / "runs" / "wf" / "p" / "m1.parquet").unlink()
    path = project(
        tmp_path,
        pass_extra="chunk_size = 1\nsub_chunk = 7\nattempts = 5",
        model_extra="max_retries = 1\ntimeout_s = 3.0",
    )
    text = path.read_text(encoding="utf-8").replace(
        "http://stub.test/v1", "http://elsewhere.test/v2", 1
    )
    text = text.replace("concurrency = 1", "concurrency = 3", 1)
    path.write_text(text, encoding="utf-8")
    [result] = tagger.run(
        tagger.load_workflow(path), transport=Endpoint(never_called).transport
    )
    assert result.output_written and list(result.skipped_on_disk) == [1, 2, 3]


def test_seed_change_is_a_mismatch(tmp_path, key_env):
    tagger.run(
        tagger.load_workflow(project(tmp_path)), transport=Endpoint(answer).transport
    )
    path = project(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8").replace("seed = 7", "seed = 8", 1),
        encoding="utf-8",
    )
    with pytest.raises(tagger.ManifestMismatch) as info:
        tagger.run(
            tagger.load_workflow(path), transport=Endpoint(never_called).transport
        )
    assert "run_id: " in str(info.value)


# --------------------------------------------------------------------------
# combine (6.8)
# --------------------------------------------------------------------------


def test_combine_only_needs_run_json(tmp_path, key_env):
    workflow = tagger.load_workflow(project(tmp_path))
    with pytest.raises(tagger.ManifestMismatch):
        tagger.run(
            workflow, combine_only=True, transport=Endpoint(never_called).transport
        )


def test_combine_only_makes_no_call(tmp_path, key_env):
    workflow = tagger.load_workflow(project(tmp_path))
    [first] = tagger.run(workflow, transport=Endpoint(answer).transport)
    table = pl.read_parquet(first.output)
    first.output.unlink()
    [result] = tagger.run(
        workflow, combine_only=True, transport=Endpoint(never_called).transport
    )
    assert result.output_written and pl.read_parquet(result.output).equals(table)


def test_combine_with_missing_chunks(tmp_path, key_env):
    workflow = tagger.load_workflow(project(tmp_path))
    tagger.run(workflow, transport=Endpoint(answer).transport)
    for index in (2, 3):
        (work_dir(tmp_path) / "chunks" / f"chunk_0000{index}.parquet").unlink()
    with pytest.raises(tagger.IncompleteRun) as info:
        tagger.run(
            workflow, combine_only=True, transport=Endpoint(never_called).transport
        )
    assert "2" in str(info.value)


def chunk_frame(tmp_path, index=1):
    return pl.read_parquet(work_dir(tmp_path) / "chunks" / f"chunk_{index:05d}.parquet")


def broken_chunks():
    return {
        "stray chunk": lambda tmp, frame: frame.write_parquet(
            work_dir(tmp) / "chunks" / "chunk_00009.parquet"
        ),
        "missing column": lambda tmp, frame: frame.drop("tokens_out").write_parquet(
            work_dir(tmp) / "chunks" / "chunk_00001.parquet"
        ),
        "columns reordered": lambda tmp, frame: frame.select(
            list(reversed(frame.columns))
        ).write_parquet(work_dir(tmp) / "chunks" / "chunk_00001.parquet"),
        "dtype changed": lambda tmp, frame: frame.with_columns(
            pl.col("tokens_in").cast(pl.Int32)
        ).write_parquet(work_dir(tmp) / "chunks" / "chunk_00001.parquet"),
        "repeated row": lambda tmp, frame: pl.concat(
            [frame, frame.head(1)]
        ).write_parquet(work_dir(tmp) / "chunks" / "chunk_00001.parquet"),
        "missing row": lambda tmp, frame: frame.tail(2).write_parquet(
            work_dir(tmp) / "chunks" / "chunk_00001.parquet"
        ),
        "row of another work": lambda tmp, frame: pl.concat(
            [frame, frame.head(1).with_columns(pl.lit("zz").alias("id"))]
        ).write_parquet(work_dir(tmp) / "chunks" / "chunk_00001.parquet"),
        "another model": lambda tmp, frame: frame.with_columns(
            pl.lit("m9").alias("model")
        ).write_parquet(work_dir(tmp) / "chunks" / "chunk_00001.parquet"),
        "another prompt id": lambda tmp, frame: frame.with_columns(
            pl.lit("tq-000000000000").alias("prompt_id")
        ).write_parquet(work_dir(tmp) / "chunks" / "chunk_00001.parquet"),
        "another run id": lambda tmp, frame: frame.with_columns(
            pl.lit("run-000000000000").alias("run_id")
        ).write_parquet(work_dir(tmp) / "chunks" / "chunk_00001.parquet"),
    }


@pytest.mark.parametrize("case", sorted(broken_chunks()))
def test_combine_refuses_a_bad_chunk(tmp_path, key_env, case):
    workflow = tagger.load_workflow(project(tmp_path))
    [first] = tagger.run(workflow, transport=Endpoint(answer).transport)
    first.output.unlink()
    broken_chunks()[case](tmp_path, chunk_frame(tmp_path))
    with pytest.raises(tagger.CombineError) as info:
        tagger.run(
            workflow, combine_only=True, transport=Endpoint(never_called).transport
        )
    name = "chunk_00009" if case == "stray chunk" else "chunk_00001"
    if case not in {"repeated row", "missing row", "row of another work"}:
        assert name in str(info.value)
    assert not first.output.exists()


# --------------------------------------------------------------------------
# restrictions (10.1)
# --------------------------------------------------------------------------


def test_limit_keeps_the_first_works(tmp_path, key_env):
    endpoint = Endpoint(answer)
    [result] = tagger.run(
        tagger.load_workflow(project(tmp_path)), limit=2, transport=endpoint.transport
    )
    assert first_words(endpoint) == ["Red kite été {abstract}", "Green tea"]
    assert result.units == 2
    assert pl.read_parquet(result.output)["id"].unique().sort().to_list() == [
        "a1",
        "b2",
    ]


def test_models_restriction(tmp_path, key_env):
    path = project(tmp_path, models='["m1", "m2"]')
    endpoint = Endpoint(answer)
    results = tagger.run(
        tagger.load_workflow(path), models=["m2"], transport=endpoint.transport
    )
    assert [(r.pass_id, r.model) for r in results] == [("p", "m2")]
    assert {r["model"] for r in endpoint.requests} == {"m2"}


def test_models_run_in_pass_order(tmp_path, key_env):
    path = project(tmp_path, models='["m2", "m1"]')
    endpoint = Endpoint(answer)
    results = tagger.run(tagger.load_workflow(path), transport=endpoint.transport)
    assert [r.model for r in results] == ["m2", "m1"]
    assert [r["model"] for r in endpoint.requests] == ["m2"] * 3 + ["m1"] * 3


def two_passes(tmp_path):
    """`scores` (score_json over the colour list) then `pick` (threshold from it)."""
    write_texts(tmp_path)
    score_question(tmp_path / "q")
    write_question(
        tmp_path / "pick",
        name="test/pick",
        level="work x list",
        readout="letter_text",
        blocks={"SYS": "Answer Y or N.", "USR": "{title}|{colour}"},
        fill_user={"title": "text:title", "colour": "a:id"},
        fields=["title"],
        readout_table='letters = ["Y", "N"]',
        budget="max_tokens = 5",
    )
    body = model_entry() + (
        '[[passes]]\nid = "scores"\nquestion_dir = "q"\nmodels = ["m1"]\nunits = { rule = "all" }\nchunk_size = 1\n\n'
        '[[passes]]\nid = "pick"\nquestion_dir = "pick"\nmodels = ["m1"]\n'
        'units = { rule = "threshold", from = "scores", model = "same", at_least = 0.2 }\n'
    )
    return write_workflow(tmp_path, body)


def two_pass_answer(payload, n):
    if payload.get("response_format"):
        return chat(GOOD)
    return chat("Y")


def test_passes_restriction_reads_an_earlier_output(tmp_path, key_env):
    workflow = tagger.load_workflow(two_passes(tmp_path))
    tagger.run(
        workflow, passes=["scores"], transport=Endpoint(two_pass_answer).transport
    )
    endpoint = Endpoint(two_pass_answer)
    results = tagger.run(workflow, passes=["pick"], transport=endpoint.transport)
    assert [(r.pass_id, r.model) for r in results] == [("pick", "m1")]
    # GREEN 0.2 and BLUE 0.3 pass at_least 0.2, for each of the three works.
    assert results[0].units == 6
    assert all(r.get("response_format") is None for r in endpoint.requests)


def test_a_source_without_output_stops_the_reading_pass(tmp_path, key_env):
    workflow = tagger.load_workflow(two_passes(tmp_path))
    chunks = tmp_path / "runs" / "wf" / "scores" / "m1" / "chunks"
    chunks.mkdir(parents=True)
    (chunks / "chunk_00002.claim").write_text("other", encoding="utf-8")
    endpoint = Endpoint(two_pass_answer)
    results = tagger.run(workflow, transport=endpoint.transport)
    assert [(r.pass_id, r.model, r.output_written) for r in results] == [
        ("scores", "m1", False),
        ("pick", "m1", False),
    ]
    assert results[1].units == 0
    assert all(r.get("response_format") for r in endpoint.requests)


def test_a_pass_reading_a_missing_output_is_refused(tmp_path, key_env):
    workflow = tagger.load_workflow(two_passes(tmp_path))
    with pytest.raises(tagger.TaggerError):
        tagger.run(
            workflow, passes=["pick"], transport=Endpoint(never_called).transport
        )


# --------------------------------------------------------------------------
# the texts table (2.1)
# --------------------------------------------------------------------------


BAD_TEXTS = {
    "null id": (
        TEXTS.with_columns(
            pl.when(pl.col("id") == "a1").then(None).otherwise(pl.col("id")).alias("id")
        ),
        None,
    ),
    "empty id": (
        TEXTS.with_columns(
            pl.when(pl.col("id") == "a1")
            .then(pl.lit(""))
            .otherwise(pl.col("id"))
            .alias("id")
        ),
        None,
    ),
    "repeated id": (pl.concat([TEXTS, TEXTS.head(1)]), "b2"),
    "missing field": (TEXTS.drop("abstract"), "abstract"),
    "field not a string": (TEXTS.with_columns(pl.lit(3).alias("title")), "title"),
    "id not a string": (TEXTS.with_columns(pl.Series("id", [1, 2, 3])), None),
}


@pytest.mark.parametrize("case", sorted(BAD_TEXTS))
def test_bad_texts_are_refused_before_any_call(tmp_path, key_env, case):
    frame, named = BAD_TEXTS[case]
    workflow = tagger.load_workflow(project(tmp_path))
    with pytest.raises(tagger.TextsError) as info:
        tagger.run(workflow, texts=frame, transport=Endpoint(never_called).transport)
    if named:
        assert named in str(info.value)
    assert not (tmp_path / "runs").exists()


def test_repeated_ids_are_counted(tmp_path, key_env):
    frame = pl.concat([TEXTS, TEXTS.head(2)])
    workflow = tagger.load_workflow(project(tmp_path))
    with pytest.raises(tagger.TextsError) as info:
        tagger.run(workflow, texts=frame, transport=Endpoint(never_called).transport)
    # Two repeated ids, the first in table order is b2.
    assert "2" in str(info.value) and "b2" in str(info.value)


def test_a_null_field_column_is_accepted(tmp_path, key_env):
    frame = TEXTS.with_columns(pl.lit(None).alias("abstract"))
    assert frame.schema["abstract"] == pl.Null
    endpoint = Endpoint(answer)
    tagger.run(
        tagger.load_workflow(project(tmp_path)),
        texts=frame,
        transport=endpoint.transport,
    )
    assert endpoint.users()[1] == "Text: Green tea\n"


def test_empty_text_is_sent_as_it_is(tmp_path, key_env):
    frame = TEXTS.with_columns(pl.lit("").alias("title"))
    endpoint = Endpoint(answer)
    [result] = tagger.run(
        tagger.load_workflow(project(tmp_path)),
        texts=frame,
        transport=endpoint.transport,
    )
    assert endpoint.users() == [
        "Text: \n",
        "Text: \nLeaves.",
        "Text: \nA large animal.",
    ]
    assert result.units == 3


def test_id_column_is_written_as_id(tmp_path, key_env):
    frame = TEXTS.rename({"id": "work_id"})
    write_texts(tmp_path, frame)
    path = project(tmp_path, texts=frame, run_extra='id_column = "work_id"')
    [result] = tagger.run(
        tagger.load_workflow(path), transport=Endpoint(answer).transport
    )
    table = pl.read_parquet(result.output)
    assert table.columns[0] == "id" and "work_id" not in table.columns
    assert table["id"].unique().sort().to_list() == ["a1", "b2", "c3"]


def test_texts_argument_overrides_the_workflow(tmp_path, key_env):
    path = project(tmp_path)
    other = tmp_path / "other.parquet"
    TEXTS.head(1).write_parquet(other)
    [result] = tagger.run(
        tagger.load_workflow(path), texts=other, transport=Endpoint(answer).transport
    )
    assert result.units == 1


def test_no_texts_at_all_is_refused(tmp_path, key_env):
    write_texts(tmp_path)
    score_question(tmp_path / "q")
    body = (
        model_entry()
        + '[[passes]]\nid = "p"\nquestion_dir = "q"\nmodels = ["m1"]\nunits = { rule = "all" }\n'
    )
    path = write_workflow(tmp_path, body, texts=None)
    with pytest.raises((tagger.WorkflowError, tagger.TextsError)):
        tagger.run(
            tagger.load_workflow(path), transport=Endpoint(never_called).transport
        )


def test_open_marker_is_refused_before_any_call(tmp_path, key_env):
    write_texts(tmp_path)
    write_question(
        tmp_path / "q",
        name="test/open",
        blocks={
            "SYS": "You score colours. [[OPEN: finish this]]",
            "USR": "Text: {title}",
        },
        fill_user={"title": "text:title"},
        fields=["title"],
        readout_table='schema_name = "colour_scores"',
    )
    body = (
        model_entry()
        + '[[passes]]\nid = "p"\nquestion_dir = "q"\nmodels = ["m1"]\nunits = { rule = "all" }\n'
    )
    path = write_workflow(tmp_path, body)
    with pytest.raises(tagger.QuestionError):
        tagger.run(
            tagger.load_workflow(path), transport=Endpoint(never_called).transport
        )
    assert not (tmp_path / "runs").exists()


# --------------------------------------------------------------------------
# the manifest of a live run (9)
# --------------------------------------------------------------------------


def test_manifest_counts_fresh_and_cached_calls(tmp_path, key_env):
    workflow = tagger.load_workflow(project(tmp_path))
    tagger.run(
        workflow,
        transport=Endpoint(lambda p, n: chat(GOOD, tin=20 + n, tout=4)).transport,
    )
    manifest = json.loads(
        (work_dir(tmp_path) / "manifest.json").read_text(encoding="utf-8")
    )
    counts = manifest["counts"]
    assert (
        counts["units"] == 3 and counts["rows"] == 9 and counts["parse_failures"] == 0
    )
    assert counts["retried"] == 0
    assert (counts["calls"], counts["cached_calls"], counts["fresh_calls"]) == (3, 0, 3)
    assert counts["distinct_keys"] == 3
    assert (counts["tokens_in"], counts["tokens_out"]) == (63, 12)
    assert manifest["replay"] is False
    assert manifest["model"]["api_key_env"] == "TAGGER_TEST_KEY"
    assert "test-secret" not in json.dumps(manifest)
    for key in (
        "started_at",
        "combined_at",
        "package_version",
        "python_version",
        "settings",
        "sources",
    ):
        assert key in manifest

    # A second run from the cache: the call logs gain three cached calls.
    shutil.rmtree(tmp_path / "runs")
    tagger.run(workflow, transport=Endpoint(never_called).transport)
    manifest = json.loads(
        (work_dir(tmp_path) / "manifest.json").read_text(encoding="utf-8")
    )
    assert (manifest["counts"]["cached_calls"], manifest["counts"]["fresh_calls"]) == (
        3,
        0,
    )
    lines = (
        (work_dir(tmp_path) / "calls" / "main.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert [json.loads(line)["cached"] for line in lines] == [True, True, True]
    assert set(json.loads(lines[0])) == {
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


def test_keys_and_env_never_in_the_run_files(tmp_path, key_env):
    tagger.run(
        tagger.load_workflow(project(tmp_path)), transport=Endpoint(answer).transport
    )
    for root, _, files in os.walk(tmp_path / "runs"):
        for name in files:
            if name.endswith((".json", ".jsonl")):
                assert "test-secret" not in Path(root, name).read_text(encoding="utf-8")


@pytest.mark.skip(
    reason="contract 6.7: the key columns over which units_sha256 is computed (with "
    "or without repeat, flags and source_score) are not listed; question "
    "journalled 2026-11-02"
)
def test_units_sha256_value():
    """units_sha256 equals frame_digest over the planned units' key columns."""
