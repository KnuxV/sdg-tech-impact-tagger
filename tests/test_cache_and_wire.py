"""The request on the wire, the cache key and the cache file (contract 4.1, 6.3, 6.5).

tests/fixtures/wire.json is frozen from the [OA] client (make_oa.py): for four
requests, the body it sent, the cache key, the key with `"repeat": 2` added,
and the exact text of the cache file it wrote. The package, asked the same
question by the same model, must send the same body and write the same file.
"""

from __future__ import annotations

import json
import shutil

import httpx
import polars as pl
import pytest
from conftest import (
    FIXTURES,
    KEY_VALUE,
    Endpoint,
    chat,
    model_entry,
    never_called,
    read_json,
    score_question,
    write_texts,
    write_workflow,
    yn_question,
)

import sdg_tech_impact_tagger as tagger

WIRE = {case["case"]: case for case in read_json(FIXTURES / "wire.json")}


@pytest.mark.parametrize("case", sorted(WIRE))
def test_cache_key_is_the_earlier_key(case):
    fields = WIRE[case]["fields"]
    assert tagger.cache_key(fields) == WIRE[case]["key"]
    # Contract 6.5: a repeat r >= 2 adds "repeat": r to the key fields.
    assert tagger.cache_key({**fields, "repeat": 2}) == WIRE[case]["repeat_2_key"]


def project(tmp_path, case: str) -> tuple:
    """A workflow asking the wire fixture's question of model m1 over three works."""
    write_texts(tmp_path)
    reasoning, style = (
        ("on", "enable_thinking") if case == "letter_text_thinking" else ("off", "omit")
    )
    if case == "score_json":
        score_question(tmp_path / "q")
    elif case == "letter_logprob":
        yn_question(tmp_path / "q")
    else:
        yn_question(tmp_path / "q", readout="letter_text", budget="max_tokens = 300")
    body = model_entry(reasoning=reasoning, style=style) + (
        '[[passes]]\nid = "p"\nquestion_dir = "q"\nmodels = ["m1"]\nunits = { rule = "all" }\n'
    )
    return write_workflow(tmp_path, body)


@pytest.mark.parametrize("case", sorted(WIRE))
def test_wire_body_key_and_cache_file(tmp_path, key_env, case):
    fixture = WIRE[case]
    endpoint = Endpoint(lambda payload, n: fixture["body"])
    workflow = tagger.load_workflow(project(tmp_path, case))
    tagger.run(workflow, transport=endpoint.transport)

    user = fixture["payload"]["messages"][1]["content"]
    sent = [r for r in endpoint.requests if r["messages"][1]["content"] == user]
    assert len(sent) == 1
    assert sent[0] == fixture["payload"]
    assert all(url == "http://stub.test/v1/chat/completions" for url in endpoint.urls)
    assert all(h["authorization"] == f"Bearer {KEY_VALUE}" for h in endpoint.headers)

    key = fixture["key"]
    path = tmp_path / "cache" / key[:2] / f"{key}.json"
    assert path.read_text(encoding="utf-8") == fixture["file_text"]
    # No temporary file is left beside it.
    assert not list((tmp_path / "cache").rglob("*.tmp"))


def test_endpoint_trailing_slash_is_dropped(tmp_path, key_env):
    write_texts(tmp_path)
    score_question(tmp_path / "q")
    body = model_entry().replace('"http://stub.test/v1"', '"http://stub.test/v1/"') + (
        '[[passes]]\nid = "p"\nquestion_dir = "q"\nmodels = ["m1"]\nunits = { rule = "all" }\n'
    )
    endpoint = Endpoint(lambda payload, n: WIRE["score_json"]["body"])
    tagger.run(
        tagger.load_workflow(write_workflow(tmp_path, body)),
        transport=endpoint.transport,
    )
    assert set(endpoint.urls) == {"http://stub.test/v1/chat/completions"}


def test_repeats_key_and_rows(tmp_path, key_env):
    write_texts(tmp_path)
    score_question(tmp_path / "q")
    body = model_entry() + (
        '[[passes]]\nid = "p"\nquestion_dir = "q"\nmodels = ["m1"]\nunits = { rule = "all" }\nrepeats = 2\n'
    )
    content = iter(
        ['{"RED": 1, "GREEN": 2, "BLUE": 3}', '{"RED": 4, "GREEN": 5, "BLUE": 6}'] * 3
    )
    endpoint = Endpoint(lambda payload, n: chat(next(content), tin=10 + n))
    [result] = tagger.run(
        tagger.load_workflow(write_workflow(tmp_path, body)),
        transport=endpoint.transport,
    )
    assert len(endpoint.requests) == 6
    # Contract 5: repeats of a unit are adjacent in plan order.
    users = endpoint.users()
    assert users[0] == users[1] and users[2] == users[3] and users[4] == users[5]
    key = WIRE["score_json"]["key"]
    repeat_key = WIRE["score_json"]["repeat_2_key"]
    assert (tmp_path / "cache" / key[:2] / f"{key}.json").exists()
    stored = json.loads(
        (tmp_path / "cache" / repeat_key[:2] / f"{repeat_key}.json").read_text("utf-8")
    )
    assert stored["cache_key"] == repeat_key
    assert stored["request"] == {**WIRE["score_json"]["fields"], "repeat": 2}
    table = pl.read_parquet(result.output)
    assert table.height == 18
    assert table.select("id", "code", "repeat").rows()[:6] == [
        ("a1", "BLUE", 1),
        ("a1", "BLUE", 2),
        ("a1", "GREEN", 1),
        ("a1", "GREEN", 2),
        ("a1", "RED", 1),
        ("a1", "RED", 2),
    ]
    assert table.schema["repeat"] == pl.Int64
    first, second = (
        table.filter(pl.col("repeat") == r).sort("id", "code")["score"].to_list()
        for r in (1, 2)
    )
    assert first[:3] == [0.03, 0.02, 0.01] and second[:3] == [0.06, 0.05, 0.04]


def test_unreadable_cache_file(tmp_path, key_env):
    workflow = project(tmp_path, "score_json")
    key = WIRE["score_json"]["key"]
    path = tmp_path / "cache" / key[:2] / f"{key}.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"cache_key": "x", "kind": "chat"}', encoding="utf-8"
    )  # no response
    with pytest.raises(tagger.CacheError) as info:
        tagger.run(
            tagger.load_workflow(workflow),
            transport=Endpoint(lambda p, n: chat("{}")).transport,
        )
    assert key in str(info.value)


def test_cache_file_not_json(tmp_path, key_env):
    workflow = project(tmp_path, "score_json")
    key = WIRE["score_json"]["key"]
    path = tmp_path / "cache" / key[:2] / f"{key}.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(tagger.CacheError):
        tagger.run(
            tagger.load_workflow(workflow),
            transport=Endpoint(lambda p, n: chat("{}")).transport,
        )


def test_cached_answer_makes_no_request(tmp_path, key_env):
    workflow = tagger.load_workflow(project(tmp_path, "score_json"))
    first = Endpoint(lambda payload, n: WIRE["score_json"]["body"])
    tagger.run(workflow, transport=first.transport)
    assert len(first.requests) == 3
    shutil.rmtree(tmp_path / "runs")
    second = Endpoint(never_called)
    [result] = tagger.run(workflow, transport=second.transport)
    assert result.output_written and second.requests == []


def test_replay_miss_raises_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("TAGGER_TEST_KEY", raising=False)
    workflow = tagger.load_workflow(project(tmp_path, "score_json"))
    with pytest.raises(tagger.CacheMiss):
        tagger.run(workflow, replay=True, transport=Endpoint(never_called).transport)
    assert not (tmp_path / "runs" / "wf" / "p" / "m1.parquet").exists()
    assert (
        not list((tmp_path / "cache").rglob("*.json"))
        if (tmp_path / "cache").exists()
        else True
    )


def test_replay_reads_no_key(tmp_path, monkeypatch, key_env):
    workflow = tagger.load_workflow(project(tmp_path, "score_json"))
    tagger.run(
        workflow,
        transport=Endpoint(lambda payload, n: WIRE["score_json"]["body"]).transport,
    )
    shutil.rmtree(tmp_path / "runs")
    monkeypatch.delenv("TAGGER_TEST_KEY")
    [result] = tagger.run(
        workflow, replay=True, transport=Endpoint(never_called).transport
    )
    assert result.output_written


def test_live_run_without_key_is_refused_before_any_call(tmp_path, monkeypatch):
    monkeypatch.delenv("TAGGER_TEST_KEY", raising=False)
    workflow = tagger.load_workflow(project(tmp_path, "score_json"))
    with pytest.raises(tagger.KeyMissing) as info:
        tagger.run(workflow, transport=Endpoint(never_called).transport)
    assert "TAGGER_TEST_KEY" in str(info.value)
    assert not (tmp_path / "runs").exists()


def test_empty_key_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGGER_TEST_KEY", "")
    workflow = tagger.load_workflow(project(tmp_path, "score_json"))
    with pytest.raises(tagger.KeyMissing):
        tagger.run(workflow, transport=Endpoint(never_called).transport)


def test_env_file_next_to_the_workflow(tmp_path, monkeypatch):
    monkeypatch.delenv("TAGGER_TEST_KEY", raising=False)
    path = project(tmp_path, "score_json")
    (tmp_path / ".env").write_text(
        '# a comment\n\nno equals sign\nexport TAGGER_TEST_KEY = "from-file=1"\nOTHER=x\n',
        encoding="utf-8",
    )
    endpoint = Endpoint(lambda payload, n: WIRE["score_json"]["body"])
    tagger.run(tagger.load_workflow(path), transport=endpoint.transport)
    assert {h["authorization"] for h in endpoint.headers} == {"Bearer from-file=1"}


def test_environment_wins_over_env_file(tmp_path, key_env):
    path = project(tmp_path, "score_json")
    (tmp_path / ".env").write_text("TAGGER_TEST_KEY='from-file'\n", encoding="utf-8")
    endpoint = Endpoint(lambda payload, n: WIRE["score_json"]["body"])
    tagger.run(tagger.load_workflow(path), transport=endpoint.transport)
    assert {h["authorization"] for h in endpoint.headers} == {f"Bearer {KEY_VALUE}"}


def test_key_never_in_the_error_message(tmp_path, key_env, no_backoff):
    path = project(tmp_path, "score_json")
    endpoint = Endpoint(lambda payload, n: httpx.Response(401, text="bad key"))
    with pytest.raises(tagger.LLMCallError) as info:
        tagger.run(tagger.load_workflow(path), transport=endpoint.transport)
    assert KEY_VALUE not in str(info.value)


@pytest.mark.skip(
    reason="contract 3.6: the value of `readout` in the run id (the name, or the "
    "name with its layout or form) and the `top_logprobs` and `response_format` "
    "of letter_text and json_object are not spelled out; question journalled 2026-11-02"
)
def test_run_id_exact_value():
    """The run id equals the contract formula computed from the resolved settings."""
