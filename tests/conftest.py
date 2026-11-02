"""Shared helpers of the test suite.

The package is imported as a module (`tagger`) and its names are looked up
inside each test, so that the suite is collected even before the
implementation exists, and fails test by test on what is missing.

Expected values of behaviour carried over from the earlier repositories are
read from tests/fixtures/, frozen by the scripts under tests/fixtures/make/;
behaviour new to the package is tested from docs/contract.md alone.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import pytest
from polars.testing import assert_frame_equal

import sdg_tech_impact_tagger as tagger

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PACKAGE = Path(tagger.__file__).resolve().parent
QUESTIONS = PACKAGE / "questions"
KEY_ENV = "TAGGER_TEST_KEY"
KEY_VALUE = "test-secret-0123"
RUN_ID_RE = re.compile(r"^run-[0-9a-f]{12}$")

DTYPES = {
    "String": pl.String,
    "Float64": pl.Float64,
    "Int64": pl.Int64,
    "Boolean": pl.Boolean,
}


# --------------------------------------------------------------------------
# contract formulas, written out so the tests do not depend on the package
# --------------------------------------------------------------------------


def sha12(text: str) -> str:
    """Contract 3.5: the first 12 hex characters of the sha256 of the UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def contract_key(fields: dict[str, Any]) -> str:
    """Contract 6.5: the cache key of a request's key fields."""
    blob = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def frame_digest(rows: list[list[Any]]) -> str:
    """Contract 6.7: hex sha256 of the rows as JSON lists joined by newlines."""
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# fixtures as frames
# --------------------------------------------------------------------------


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def works_frame(name: str) -> pl.DataFrame:
    """The invented works of a fixture directory as a texts table."""
    data = read_json(FIXTURES / name / "works.json")
    return pl.DataFrame(
        data["rows"],
        schema={c: pl.String for c in data["columns"]},
        orient="row",
    )


def write_works(directory: Path, name: str, file: str = "works.parquet") -> Path:
    path = Path(directory) / file
    works_frame(name).write_parquet(path)
    return path


def expected_table(path: Path) -> tuple[list[str], pl.DataFrame]:
    """(all column names in order, the expected rows without `run_id`)."""
    data = read_json(path)
    names = [c for c in data["columns"] if c != "run_id"]
    schema = {
        name: DTYPES[dtype] for name, dtype in zip(names, data["dtypes"], strict=True)
    }
    frame = pl.DataFrame(data["rows"], schema=schema, orient="row")
    return data["columns"], frame


def assert_table(actual: pl.DataFrame, path: Path, **replace: Any) -> None:
    """The whole table: column names and order, dtypes, every row; `run_id` one
    value of the form run-<12 hex>. `replace` sets a column to one value."""
    columns, expected = expected_table(path)
    for name, value in replace.items():
        expected = expected.with_columns(
            pl.lit(value, dtype=expected.schema[name]).alias(name)
        )
    assert actual.columns == columns
    assert actual.schema["run_id"] == pl.String
    run_ids = actual["run_id"].unique().to_list()
    assert len(run_ids) == 1 and RUN_ID_RE.match(run_ids[0]), run_ids
    assert_frame_equal(
        actual.drop("run_id"), expected, check_dtypes=True, check_exact=True
    )


def copy_calls(source: Path, target: Path) -> Path:
    """Copy a fixture cache, so a run can never touch the frozen files."""
    shutil.copytree(source, target)
    return target


# --------------------------------------------------------------------------
# a stub endpoint
# --------------------------------------------------------------------------


class Endpoint:
    """An httpx MockTransport that records every request and answers by a script.

    `answer(request_json, n)` returns an httpx.Response, a dict (sent as JSON
    with status 200), or raises an httpx exception; `n` counts the requests
    received so far, from 0.
    """

    def __init__(self, answer: Callable[[dict, int], Any]) -> None:
        self.answer = answer
        self.requests: list[dict] = []
        self.headers: list[dict] = []
        self.urls: list[str] = []
        self._lock = threading.Lock()
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        with self._lock:
            n = len(self.requests)
            self.requests.append(payload)
            self.headers.append(dict(request.headers))
            self.urls.append(str(request.url))
        result = self.answer(payload, n)
        if isinstance(result, httpx.Response):
            return result
        return httpx.Response(200, json=result)

    def users(self) -> list[str]:
        return [r["messages"][1]["content"] for r in self.requests]


def never_called(payload: dict, n: int) -> Any:
    raise AssertionError("the network was reached")


def chat(
    content: Any,
    *,
    served: str | None = "stub-model",
    fp: str | None = None,
    tin: int = 10,
    tout: int = 2,
    finish: str = "stop",
    logprobs: list | None = None,
) -> dict:
    """A chat completion body. `logprobs` is a list of (token, [(top token, logprob)])."""
    body: dict[str, Any] = {"id": "x", "object": "chat.completion"}
    if served is not None:
        body["model"] = served
    if fp is not None:
        body["system_fingerprint"] = fp
    choice: dict[str, Any] = {
        "index": 0,
        "message": {"role": "assistant", "content": content},
        "finish_reason": finish,
    }
    if logprobs is not None:
        choice["logprobs"] = {
            "content": [
                {
                    "token": t,
                    "logprob": top[0][1] if top else 0.0,
                    "top_logprobs": [{"token": a, "logprob": b} for a, b in top],
                }
                for t, top in logprobs
            ]
        }
    body["choices"] = [choice]
    body["usage"] = {
        "prompt_tokens": tin,
        "completion_tokens": tout,
        "total_tokens": tin + tout,
    }
    return body


# --------------------------------------------------------------------------
# a small project on disk: a list, questions, a workflow
# --------------------------------------------------------------------------

COLOUR_LIST = """\
[list]
id = "colour"
name = "Colours"

[[labels]]
id = "RED"
name = "Red"

[[labels]]
id = "GREEN"
name = "Green"

[[labels]]
id = "BLUE"
name = "Blue"
"""

SHADE_LIST = """\
[list]
id = "shade"
name = "Shades"

[[labels]]
id = "DARK"
name = "Dark"

[[labels]]
id = "PALE"
name = "Pale"
"""


def block_file(blocks: dict[str, str]) -> str:
    """A markdown file holding the given blocks, with prose around them."""
    parts = ["# Test question\n\nProse outside the blocks is ignored.\n"]
    for name, body in blocks.items():
        parts.append(f"## {name}\n\n```text\n{body}\n```\n")
    return "\n".join(parts)


def toml_value(value: Any) -> str:
    return (
        json.dumps(value)
        if not isinstance(value, bool)
        else ("true" if value else "false")
    )


def write_question(
    directory: Path,
    *,
    name: str = "test/question",
    level: str = "work",
    readout: str = "score_json",
    blocks: dict[str, str],
    system: str = "SYS",
    user: str = "USR",
    fill_system: dict[str, str] | None = None,
    fill_user: dict[str, str],
    lists: dict[str, str] | None = None,
    fields: list[str] | None = None,
    readout_table: str = "",
    budget: str = "max_tokens = 50",
    prefix: str = "tq",
    id_blocks: list[str] | None = None,
    extra: str = "",
    question_extra: str = "",
    prompt_id: str | None = None,
) -> str:
    """Write a question directory; return its prompt id, computed by the contract rule."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "q.md").write_text(block_file(blocks), encoding="utf-8")
    id_blocks = id_blocks or [system, user]
    computed = prefix + "-" + sha12("\n".join(blocks[b] for b in id_blocks))
    lists = lists if lists is not None else {"a": "colour"}
    fields = fields if fields is not None else ["title", "abstract"]
    text = [
        "[question]",
        f"name = {toml_value(name)}",
        f"level = {toml_value(level)}",
        f"readout = {toml_value(readout)}",
        'status = "current"',
        f"prompt_id = {toml_value(prompt_id or computed)}",
        question_extra,
        "",
        "[lists]",
        *[f"{k} = {toml_value(v)}" for k, v in lists.items()],
        "",
        "[text]",
        f"fields = {toml_value(fields)}",
        "",
        "[blocks]",
        'files = ["q.md"]',
        f"system = {toml_value(system)}",
        f"user = {toml_value(user)}",
        "",
        "[blocks.fill.system]",
        *[f"{k} = {toml_value(v)}" for k, v in (fill_system or {}).items()],
        "",
        "[blocks.fill.user]",
        *[f"{k} = {toml_value(v)}" for k, v in fill_user.items()],
        "",
        extra,
        "",
        "[readout]",
        readout_table,
        "",
        "[budget]",
        budget,
        "",
        "[id]",
        f"prefix = {toml_value(prefix)}",
        f"blocks = {toml_value(id_blocks)}",
        "",
    ]
    (directory / "question.toml").write_text("\n".join(text), encoding="utf-8")
    return computed


def model_entry(
    name: str = "m1",
    *,
    model: str = "m1",
    extra: str = "",
    reasoning: str = "off",
    style: str = "omit",
) -> str:
    return "\n".join(
        [
            f"[models.{name}]",
            'endpoint = "http://stub.test/v1"',
            f'api_key_env = "{KEY_ENV}"',
            f"model = {toml_value(model)}",
            "seed = 7",
            "temperature = 0.0",
            f'reasoning = "{reasoning}"',
            f'reasoning_style = "{style}"',
            "concurrency = 1",
            extra,
            "",
        ]
    )


def write_workflow(
    directory: Path,
    body: str,
    *,
    name: str = "wf",
    texts: str | None = "works.parquet",
    lists: dict[str, str] | None = None,
    run_extra: str = "",
) -> Path:
    """A workflow file: [run], [lists] (the colour and shade lists by default), then `body`."""
    directory = Path(directory)
    (directory / "lists").mkdir(parents=True, exist_ok=True)
    (directory / "lists" / "colour.toml").write_text(COLOUR_LIST, encoding="utf-8")
    (directory / "lists" / "shade.toml").write_text(SHADE_LIST, encoding="utf-8")
    lists = (
        lists
        if lists is not None
        else {"colour": "lists/colour.toml", "shade": "lists/shade.toml"}
    )
    head = ["[run]", f"name = {toml_value(name)}"]
    if texts is not None:
        head.append(f"texts = {toml_value(texts)}")
    head.append(run_extra)
    head += ["", "[lists]", *[f"{k} = {toml_value(v)}" for k, v in lists.items()], ""]
    path = directory / "workflow.toml"
    path.write_text("\n".join(head) + "\n" + body, encoding="utf-8")
    return path


TEXTS = pl.DataFrame(
    {
        "id": ["b2", "a1", "c3"],
        "title": ["Red kite été {abstract}", "Green tea", "Blue whale"],
        "abstract": [None, "Leaves.", "A large animal."],
        "ignored": ["x", "y", "z"],
    }
)


def write_texts(
    directory: Path, frame: pl.DataFrame = TEXTS, file: str = "works.parquet"
) -> Path:
    path = Path(directory) / file
    frame.write_parquet(path)
    return path


SCORE_BLOCKS = {"SYS": "You score colours.", "USR": "Text: {title}\n{abstract}"}
YN_BLOCKS = {"SYS": "Answer Y or N.", "USR": "Text: {title}\nColour: {colour}\nY or N:"}


def score_question(directory: Path, **kw: Any) -> str:
    """The colour score_json question of the wire fixture."""
    return write_question(
        directory,
        name="test/colour_score",
        blocks=SCORE_BLOCKS,
        fill_user={"title": "text:title", "abstract": "text:abstract"},
        readout_table='schema_name = "colour_scores"',
        **kw,
    )


def yn_question(
    directory: Path,
    *,
    readout: str = "letter_logprob",
    readout_table: str = 'letters = ["Y", "N"]',
    budget: str = "max_tokens = 1\ntop_logprobs = 5",
    **kw: Any,
) -> str:
    """The colour Y/N question of the wire fixture, level work x list."""
    return write_question(
        directory,
        name="test/colour_yn",
        level="work x list",
        readout=readout,
        blocks=YN_BLOCKS,
        fill_user={"title": "text:title", "colour": "a:name"},
        fields=["title"],
        readout_table=readout_table,
        budget=budget,
        **kw,
    )


@pytest.fixture
def key_env(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv(KEY_ENV, KEY_VALUE)
    return KEY_VALUE


@pytest.fixture
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Contract 6.4: the backoff constants are module attributes tests may patch."""
    from sdg_tech_impact_tagger import client

    monkeypatch.setattr(client, "BACKOFF_BASE_S", 0.0)
    monkeypatch.setattr(client, "BACKOFF_CAP_S", 0.0)


def output_of(results: list, pass_id: str, model: str) -> pl.DataFrame:
    for result in results:
        if result.pass_id == pass_id and result.model == model:
            assert result.output_written
            return pl.read_parquet(result.output)
    raise AssertionError(f"no result for {pass_id} {model}")
