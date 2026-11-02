"""One call: retries, refusals, expect_model and the served model (contract 6.4, D012).

Live runs against an httpx.MockTransport passed as `run(transport=...)`;
nothing reaches a network.
"""

from __future__ import annotations

import json
import warnings

import httpx
import polars as pl
import pytest
from conftest import (
    TEXTS,
    Endpoint,
    chat,
    model_entry,
    never_called,
    score_question,
    write_texts,
    write_workflow,
)

import sdg_tech_impact_tagger as tagger

GOOD = '{"RED": 10, "GREEN": 20, "BLUE": 30}'


def project(tmp_path, *, works: int = 1, model_extra: str = "", pass_extra: str = ""):
    write_texts(tmp_path, TEXTS.head(works))
    score_question(tmp_path / "q")
    body = model_entry(extra=model_extra) + (
        '[[passes]]\nid = "p"\nquestion_dir = "q"\nmodels = ["m1"]\nunits = { rule = "all" }\n'
        + pass_extra
        + "\n"
    )
    return tagger.load_workflow(write_workflow(tmp_path, body))


def chain(exc):
    """The exception, the failures it carries and its causes, recursively."""
    seen, todo = [], [exc]
    while todo:
        current = todo.pop()
        if current is None or any(current is s for s in seen):
            continue
        seen.append(current)
        todo.extend(e for _, e in getattr(current, "failures", None) or [])
        todo.extend([current.__cause__, current.__context__])
    return seen


def cache_files(tmp_path):
    root = tmp_path / "cache"
    return sorted(root.rglob("*.json")) if root.exists() else []


def test_retries_429_and_5xx_then_answers(tmp_path, key_env, no_backoff):
    script = [
        httpx.Response(429, text="slow down"),
        httpx.Response(503, text="busy"),
        chat(GOOD),
    ]
    endpoint = Endpoint(lambda payload, n: script[n])
    [result] = tagger.run(project(tmp_path), transport=endpoint.transport)
    assert len(endpoint.requests) == 3
    table = pl.read_parquet(result.output)
    assert table["score"].to_list() == [0.3, 0.2, 0.1]  # BLUE, GREEN, RED


def test_transport_errors_are_retried(tmp_path, key_env, no_backoff):
    def answer(payload, n):
        if n == 0:
            raise httpx.ConnectError("refused")
        if n == 1:
            raise httpx.ReadTimeout("slow")
        return chat(GOOD)

    endpoint = Endpoint(answer)
    [result] = tagger.run(project(tmp_path), transport=endpoint.transport)
    assert len(endpoint.requests) == 3 and result.output_written


def test_exhausted_retries_fail_the_call(tmp_path, key_env, no_backoff):
    endpoint = Endpoint(lambda payload, n: httpx.Response(500, text="down"))
    workflow = project(
        tmp_path, model_extra="max_retries = 1", pass_extra="attempts = 1"
    )
    with pytest.raises(tagger.LLMCallError):
        tagger.run(workflow, transport=endpoint.transport)
    # max_retries counts the retries after the first attempt.
    assert len(endpoint.requests) == 2
    work = tmp_path / "runs" / "wf" / "p" / "m1"
    assert not (tmp_path / "runs" / "wf" / "p" / "m1.parquet").exists()
    assert not (work / "chunks" / "chunk_00001.parquet").exists()
    # An exception leaves the chunk unwritten and its claim in place (6.6).
    assert (work / "chunks" / "chunk_00001.claim").read_text(
        encoding="utf-8"
    ).strip() == "main"
    assert cache_files(tmp_path) == []


def test_status_code_of_an_exhausted_call(tmp_path, key_env, no_backoff):
    endpoint = Endpoint(lambda payload, n: httpx.Response(502, text="bad gateway"))
    workflow = project(
        tmp_path, model_extra="max_retries = 0", pass_extra="attempts = 1"
    )
    with pytest.raises(tagger.LLMCallError) as info:
        tagger.run(workflow, transport=endpoint.transport)
    # The failed call carries the last status; the error raised carries it or chains to it.
    assert any(getattr(exc, "status_code", None) == 502 for exc in chain(info.value))


@pytest.mark.parametrize("status", [400, 401, 404, 422])
def test_other_status_is_not_retried(tmp_path, key_env, no_backoff, status):
    endpoint = Endpoint(lambda payload, n: httpx.Response(status, text="no"))
    with pytest.raises(tagger.LLMCallError):
        tagger.run(
            project(tmp_path, pass_extra="attempts = 1"), transport=endpoint.transport
        )
    assert len(endpoint.requests) == 1


def test_later_attempt_asks_only_the_failed_calls(tmp_path, key_env, no_backoff):
    seen: dict[str, int] = {}

    def answer(payload, n):
        user = payload["messages"][1]["content"]
        seen[user] = seen.get(user, 0) + 1
        if user.startswith("Text: Green") and seen[user] == 1:
            return httpx.Response(400, text="transient")
        return chat(GOOD)

    endpoint = Endpoint(answer)
    [result] = tagger.run(
        project(tmp_path, works=3, pass_extra="attempts = 2"),
        transport=endpoint.transport,
    )
    assert result.output_written
    # Three works, one failing once: four requests; the answered ones come from the cache.
    assert len(endpoint.requests) == 4
    assert sorted(seen.values()) == [1, 1, 2]


def test_a_failing_call_does_not_stop_the_others(tmp_path, key_env, no_backoff):
    def answer(payload, n):
        if payload["messages"][1]["content"].startswith("Text: Green"):
            return httpx.Response(400, text="no")
        return chat(GOOD)

    endpoint = Endpoint(answer)
    with pytest.raises(tagger.LLMCallError):
        tagger.run(
            project(tmp_path, works=3, pass_extra="attempts = 1"),
            transport=endpoint.transport,
        )
    assert len(cache_files(tmp_path)) == 2


def test_non_json_success_is_an_unreadable_answer(tmp_path, key_env, no_backoff):
    endpoint = Endpoint(
        lambda payload, n: httpx.Response(200, text="<html>oops</html>")
    )
    [result] = tagger.run(project(tmp_path), transport=endpoint.transport)
    assert len(endpoint.requests) == 1
    table = pl.read_parquet(result.output)
    assert table["parse_failure"].to_list() == [True, True, True]
    assert table["score"].to_list() == [0.0, 0.0, 0.0]
    assert table["tokens_in"].to_list() == [0, 0, 0]
    assert table["model_served"].to_list() == [None, None, None]
    [path] = cache_files(tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["response"] == {
        "unparseable_body": "<html>oops</html>"
    }


# --------------------------------------------------------------------------
# expect_model (D012)
# --------------------------------------------------------------------------


def test_model_mismatch_is_an_llm_call_error():
    assert issubclass(tagger.ModelMismatch, tagger.LLMCallError)
    assert issubclass(tagger.LLMCallError, tagger.TaggerError)


def test_fresh_mismatch_is_refused_and_not_cached(tmp_path, key_env, no_backoff):
    endpoint = Endpoint(lambda payload, n: chat(GOOD, served="impostor"))
    workflow = project(
        tmp_path, model_extra='expect_model = "m1-served"', pass_extra="attempts = 2"
    )
    with pytest.raises(tagger.LLMCallError):
        tagger.run(workflow, transport=endpoint.transport)
    assert cache_files(tmp_path) == []
    # Asked again in the later attempt.
    assert len(endpoint.requests) == 2


def test_mismatch_then_expected_model(tmp_path, key_env, no_backoff):
    script = [chat(GOOD, served="impostor"), chat(GOOD, served="m1-served")]
    endpoint = Endpoint(lambda payload, n: script[n])
    workflow = project(
        tmp_path, model_extra='expect_model = "m1-served"', pass_extra="attempts = 2"
    )
    [result] = tagger.run(workflow, transport=endpoint.transport)
    assert pl.read_parquet(result.output)["model_served"].to_list() == ["m1-served"] * 3
    [path] = cache_files(tmp_path)
    assert (
        json.loads(path.read_text(encoding="utf-8"))["response"]["model"] == "m1-served"
    )


def test_expect_model_list_and_missing_model(tmp_path, key_env):
    script = [chat(GOOD, served="b"), chat(GOOD, served=None), chat(GOOD, served="a")]
    endpoint = Endpoint(lambda payload, n: script[n])
    workflow = project(tmp_path, works=3, model_extra='expect_model = ["a", "b"]')
    [result] = tagger.run(workflow, transport=endpoint.transport)
    table = pl.read_parquet(result.output)
    by_id = dict(table.select("id", "model_served").unique().iter_rows())
    assert by_id == {"b2": "b", "a1": None, "c3": "a"}


def test_cached_mismatch_is_refused_and_left_in_place(tmp_path, key_env, no_backoff):
    workflow = project(tmp_path, pass_extra="attempts = 1")
    tagger.run(
        workflow,
        transport=Endpoint(lambda payload, n: chat(GOOD, served="other")).transport,
    )
    [path] = cache_files(tmp_path)
    before = path.read_bytes()
    (tmp_path / "runs").rename(tmp_path / "runs_before")
    strict = project(
        tmp_path, model_extra='expect_model = "m1-served"', pass_extra="attempts = 1"
    )
    with pytest.raises(tagger.LLMCallError) as info:
        tagger.run(strict, transport=Endpoint(never_called).transport)
    assert path.read_bytes() == before
    mismatches = [
        exc for exc in chain(info.value) if isinstance(exc, tagger.ModelMismatch)
    ]
    assert mismatches and any(path.stem in str(exc) for exc in mismatches)


# --------------------------------------------------------------------------
# the served model within a run (D012)
# --------------------------------------------------------------------------


def test_model_change_warns_once_per_new_model(tmp_path, key_env):
    served = {
        "Text: Red": ("m-a", "fp1"),
        "Text: Green": ("m-b", "fp1"),
        "Text: Blue": ("m-a", "fp1"),
    }

    def answer(payload, n):
        user = payload["messages"][1]["content"]
        model, fp = next(v for k, v in served.items() if user.startswith(k))
        return chat(GOOD, served=model, fp=fp)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        [result] = tagger.run(
            project(tmp_path, works=3), transport=Endpoint(answer).transport
        )
    changes = [w for w in caught if issubclass(w.category, tagger.ModelChangeWarning)]
    assert len(changes) == 1
    assert issubclass(tagger.ModelChangeWarning, UserWarning)
    manifest = json.loads(
        (tmp_path / "runs" / "wf" / "p" / "m1" / "manifest.json").read_text("utf-8")
    )
    assert len(manifest["model_changes"]) == 1
    assert manifest["models_served"] == {"m-a": 2, "m-b": 1}
    assert manifest["system_fingerprints"] == {"fp1": 3}
    table = pl.read_parquet(result.output)
    assert dict(table.select("id", "model_served").unique().iter_rows()) == {
        "b2": "m-a",
        "a1": "m-b",
        "c3": "m-a",
    }
    assert set(table["system_fingerprint"].to_list()) == {"fp1"}
