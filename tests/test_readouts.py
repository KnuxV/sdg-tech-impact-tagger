"""Readouts (contract section 4), from the contract alone, on invented answers.

The readings carried over from the earlier code are also checked against the
earlier tables by the replay tests (test_replay_*.py); here each rule of
section 4 is driven one case at a time through a live run on a stub
endpoint, and the whole table is compared, dtypes included.
"""

from __future__ import annotations

import json
import math
import shutil

import polars as pl
import pytest
from conftest import (
    TEXTS,
    Endpoint,
    chat,
    contract_run_id,
    model_entry,
    never_called,
    write_question,
    write_texts,
    write_workflow,
    yn_question,
)
from polars.testing import assert_frame_equal

import sdg_tech_impact_tagger as tagger

CALL = {
    "model": pl.String,
    "model_served": pl.String,
    "system_fingerprint": pl.String,
    "prompt_id": pl.String,
}
TOKENS = {"tokens_in": pl.Int64, "tokens_out": pl.Int64}
GREEN_TEA = TEXTS.filter(pl.col("id") == "a1")  # title "Green tea", abstract "Leaves."


def live(tmp_path, question_writer, *, texts=GREEN_TEA, model_extra="", pass_extra=""):
    """Write texts, one question and a one-pass workflow; return (loaded workflow, prompt id)."""
    write_texts(tmp_path, texts)
    prompt_id = question_writer(tmp_path / "q")
    body = model_entry(extra=model_extra) + (
        '[[passes]]\nid = "p"\nquestion_dir = "q"\nmodels = ["m1"]\n'
        'units = { rule = "all" }\n' + pass_extra + "\n"
    )
    workflow = tagger.load_workflow(write_workflow(tmp_path, body))
    return workflow, prompt_id


def run_with(tmp_path, workflow, answer):
    endpoint = Endpoint(answer)
    [result] = tagger.run(workflow, transport=endpoint.transport)
    return pl.read_parquet(result.output), endpoint


def expect(table: pl.DataFrame, schema: dict, rows: list[tuple]) -> None:
    """The table equals these rows under this schema, `run_id` after `prompt_id` and set aside."""
    names = list(schema)
    run_at = names.index("prompt_id") + 1
    assert table.columns == [*names[:run_at], "run_id", *names[run_at:]]
    expected = pl.DataFrame(rows, schema=schema, orient="row")
    assert_frame_equal(table.drop("run_id"), expected, check_exact=True)


# --------------------------------------------------------------------------
# score_json (4.2)
# --------------------------------------------------------------------------

SCORE_SCHEMA = {
    "id": pl.String,
    "code": pl.String,
    "repeat": pl.Int64,
    **CALL,
    "score": pl.Float64,
    **TOKENS,
    "parse_failure": pl.Boolean,
}


def score_writer(directory):
    return write_question(
        directory,
        name="test/score",
        blocks={"SYS": "You score colours.", "USR": "Text: {title}"},
        fill_user={"title": "text:title"},
        fields=["title"],
        readout_table='schema_name = "colour_scores"',
    )


def score_rows(prompt_id, scores, failure, tin=10, tout=2):
    return [
        (
            "a1",
            code,
            1,
            "m1",
            "stub-model",
            None,
            prompt_id,
            scores[code],
            tin,
            tout,
            failure,
        )
        for code in ("BLUE", "GREEN", "RED")
    ]


def test_score_json_request_schema(tmp_path, key_env):
    workflow, _ = live(tmp_path, score_writer)
    _, endpoint = run_with(
        tmp_path, workflow, lambda p, n: chat('{"RED": 1, "GREEN": 2, "BLUE": 3}')
    )
    [payload] = endpoint.requests
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "colour_scores",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "RED": {"type": "integer"},
                    "GREEN": {"type": "integer"},
                    "BLUE": {"type": "integer"},
                },
                "required": ["RED", "GREEN", "BLUE"],
                "additionalProperties": False,
            },
        },
    }
    assert set(payload) == {
        "model",
        "messages",
        "temperature",
        "max_tokens",
        "seed",
        "response_format",
    }


def test_score_json_truncates_and_clamps(tmp_path, key_env):
    workflow, prompt_id = live(tmp_path, score_writer)
    content = '{"RED": 150, "GREEN": -0.5, "BLUE": 49.9}'
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(content, tin=31, tout=9))
    scores = {"RED": 1.0, "GREEN": 0.0, "BLUE": 0.49}
    expect(table, SCORE_SCHEMA, score_rows(prompt_id, scores, False, 31, 9))


@pytest.mark.parametrize(
    "content",
    [
        '{"RED": 1, "GREEN": 2}',
        '{"RED": 1, "GREEN": 2, "BLUE": 3, "PINK": 4}',
        '{"RED": true, "GREEN": 2, "BLUE": 3}',
        '{"RED": "10", "GREEN": 2, "BLUE": 3}',
        '{"RED": null, "GREEN": 2, "BLUE": 3}',
        '{"RED": Infinity, "GREEN": 2, "BLUE": 3}',
        '{"RED": NaN, "GREEN": 2, "BLUE": 3}',
        '{"RED": 1e400, "GREEN": 2, "BLUE": 3}',
        "[10, 20, 30]",
        'Scores: {"RED": 1, "GREEN": 2, "BLUE": 3}',
        "",
        None,
    ],
    ids=lambda c: repr(c)[:40],
)
def test_score_json_unreadable(tmp_path, key_env, content):
    workflow, prompt_id = live(tmp_path, score_writer)
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(content))
    zero = {"RED": 0.0, "GREEN": 0.0, "BLUE": 0.0}
    expect(table, SCORE_SCHEMA, score_rows(prompt_id, zero, True))


BUDGET_REFUSALS = [
    # Contract 3.3: retry_max_tokens only on letter_text and json_object,
    # top_logprobs (0 to 20) only on letter_logprob.
    ("score_json", 'schema_name = "s"', "max_tokens = 5\nretry_max_tokens = 50"),
    ("letter_logprob", 'letters = ["Y", "N"]', "max_tokens = 1\nretry_max_tokens = 50"),
    ("score_json", 'schema_name = "s"', "max_tokens = 5\ntop_logprobs = 5"),
    ("letter_text", 'letters = ["Y", "N"]', "max_tokens = 5\ntop_logprobs = 5"),
    ("json_object", "__FIELDS__", "max_tokens = 5\ntop_logprobs = 5"),
    ("letter_logprob", 'letters = ["Y", "N"]', "max_tokens = 1\ntop_logprobs = 21"),
    ("letter_logprob", 'letters = ["Y", "N"]', "max_tokens = 1\ntop_logprobs = -1"),
]


@pytest.mark.parametrize(("readout", "readout_table", "budget"), BUDGET_REFUSALS)
def test_budget_keys_a_readout_does_not_take(tmp_path, readout, readout_table, budget):
    if readout_table == "__FIELDS__":
        readout_table = FIELDS
    level = "work x list" if readout.startswith("letter_") else "work"
    write_question(
        tmp_path / "q",
        name="test/budget",
        level=level,
        readout=readout,
        blocks={"SYS": "Answer.", "USR": "Text: {title}"},
        fill_user={"title": "text:title"},
        lists={"a": "adt"},
        fields=["title"],
        readout_table=readout_table,
        budget=budget,
    )
    with pytest.raises(tagger.QuestionError):
        tagger.load_question(tmp_path / "q")


def test_top_logprobs_zero_is_taken(tmp_path):
    yn_question(
        tmp_path / "q", budget="max_tokens = 1\ntop_logprobs = 0", lists={"a": "adt"}
    )
    tagger.load_question(tmp_path / "q")


# --------------------------------------------------------------------------
# letter_logprob (4.3)
# --------------------------------------------------------------------------

LOGPROB_SCHEMA = {
    "id": pl.String,
    "code": pl.String,
    "repeat": pl.Int64,
    **CALL,
    "label": pl.String,
    "p_y": pl.Float64,
    "p_n": pl.Float64,
    **TOKENS,
    "parse_failure": pl.Boolean,
}


def logprob_rows(prompt_id, label, p_y, p_n, failure):
    return [
        (
            "a1",
            code,
            1,
            "m1",
            "stub-model",
            None,
            prompt_id,
            label,
            p_y,
            p_n,
            10,
            2,
            failure,
        )
        for code in ("BLUE", "GREEN", "RED")
    ]


def contract_p(top, letters, spelling):
    """Contract 4.3 steps 2, 4 and 5, written out."""
    table = {}
    for token, value in top:
        table[token] = value
    if spelling == "sum":
        mass = {
            letter: sum(math.exp(v) for k, v in table.items() if k.strip() == letter)
            for letter in letters
        }
    else:
        mass = {
            letter: math.exp(table[letter]) if letter in table else 0.0
            for letter in letters
        }
    total = sum(mass[letter] for letter in letters)
    if total == 0.0:
        return [None for _ in letters]
    return [mass[letter] / total for letter in letters]


TOP = [(" Y", -0.1), ("Y", -1.0), ("N", -2.0), (" n", -0.5), ("Yes", -0.7)]


@pytest.mark.parametrize("spelling", ["sum", "exact"])
def test_letter_logprob_spellings(tmp_path, key_env, spelling):
    workflow, prompt_id = live(
        tmp_path, yn_question, pass_extra=f'spelling = "{spelling}"'
    )
    table, _ = run_with(
        tmp_path, workflow, lambda p, n: chat("Y", logprobs=[("Y", TOP)])
    )
    p_y, p_n = contract_p(TOP, ["Y", "N"], spelling)
    if spelling == "sum":
        assert p_y == (math.exp(-0.1) + math.exp(-1.0)) / (
            math.exp(-0.1) + math.exp(-1.0) + math.exp(-2.0)
        )
    else:
        assert p_y == math.exp(-1.0) / (math.exp(-1.0) + math.exp(-2.0))
    expect(table, LOGPROB_SCHEMA, logprob_rows(prompt_id, "Y", p_y, p_n, False))


def test_letter_logprob_repeated_token_keeps_its_last_value(tmp_path, key_env):
    workflow, prompt_id = live(tmp_path, yn_question, pass_extra='spelling = "exact"')
    top = [("Y", -3.0), ("N", -1.0), ("Y", -0.5)]
    table, _ = run_with(
        tmp_path, workflow, lambda p, n: chat("N", logprobs=[("N", top)])
    )
    p_y = math.exp(-0.5) / (math.exp(-0.5) + math.exp(-1.0))
    p_n = math.exp(-1.0) / (math.exp(-0.5) + math.exp(-1.0))
    expect(table, LOGPROB_SCHEMA, logprob_rows(prompt_id, "N", p_y, p_n, False))


def test_letter_logprob_null_content_reads_the_token(tmp_path, key_env):
    workflow, prompt_id = live(tmp_path, yn_question)
    top = [(" N", -0.1), ("Y", -2.5)]
    table, _ = run_with(
        tmp_path, workflow, lambda p, n: chat(None, logprobs=[(" N", top)])
    )
    p_y, p_n = contract_p(top, ["Y", "N"], "sum")
    expect(table, LOGPROB_SCHEMA, logprob_rows(prompt_id, "N", p_y, p_n, False))


def test_letter_logprob_other_keeps_its_probabilities(tmp_path, key_env):
    workflow, prompt_id = live(tmp_path, yn_question)
    top = [("Maybe", -0.1), ("Y", -2.0), ("N", -3.0)]
    table, _ = run_with(
        tmp_path, workflow, lambda p, n: chat("Maybe", logprobs=[("Maybe", top)])
    )
    p_y, p_n = contract_p(top, ["Y", "N"], "sum")
    expect(table, LOGPROB_SCHEMA, logprob_rows(prompt_id, "OTHER", p_y, p_n, True))


def test_letter_logprob_without_logprobs_has_null_probabilities(tmp_path, key_env):
    workflow, prompt_id = live(tmp_path, yn_question)
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(" Y "))
    # The label is read; a null probability is not a parse failure.
    expect(table, LOGPROB_SCHEMA, logprob_rows(prompt_id, "Y", None, None, False))


def test_letter_logprob_no_letter_in_the_top(tmp_path, key_env):
    workflow, prompt_id = live(tmp_path, yn_question)
    top = [("Maybe", -0.1), ("Perhaps", -2.0)]
    table, _ = run_with(
        tmp_path, workflow, lambda p, n: chat("Y", logprobs=[("Y", top)])
    )
    expect(table, LOGPROB_SCHEMA, logprob_rows(prompt_id, "Y", None, None, False))


CHANNEL = [
    ("<|channel|>", [("<|channel|>", -0.01)]),
    ("final", [("final", -0.01)]),
    ("<|message|>", [("<|message|>", -0.01)]),
    ("N", [("N", -0.3), ("Y", -1.4)]),
    ("<|return|>", [("<|return|>", -0.01)]),
]


def test_letter_logprob_final_channel(tmp_path, key_env):
    workflow, prompt_id = live(
        tmp_path, yn_question, model_extra='extraction = "final_channel"'
    )
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(None, logprobs=CHANNEL))
    p_y, p_n = contract_p([("N", -0.3), ("Y", -1.4)], ["Y", "N"], "sum")
    expect(table, LOGPROB_SCHEMA, logprob_rows(prompt_id, "N", p_y, p_n, False))


def test_letter_logprob_final_channel_takes_the_last_marker(tmp_path, key_env):
    workflow, prompt_id = live(
        tmp_path, yn_question, model_extra='extraction = "final_channel"'
    )
    entries = [
        ("<|message|>", [("<|message|>", -0.01)]),
        ("Y", [("Y", -0.1), ("N", -2.0)]),
        *CHANNEL,
    ]
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat("N", logprobs=entries))
    p_y, p_n = contract_p([("N", -0.3), ("Y", -1.4)], ["Y", "N"], "sum")
    expect(table, LOGPROB_SCHEMA, logprob_rows(prompt_id, "N", p_y, p_n, False))


@pytest.mark.parametrize(
    "entries",
    [
        [("Y", [("Y", -0.1), ("N", -2.0)])],
        [("Y", [("Y", -0.1), ("N", -2.0)]), ("<|message|>", [("<|message|>", -0.1)])],
    ],
    ids=["no marker", "marker last"],
)
def test_letter_logprob_final_channel_without_an_entry(tmp_path, key_env, entries):
    workflow, prompt_id = live(
        tmp_path, yn_question, model_extra='extraction = "final_channel"'
    )
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(None, logprobs=entries))
    # No entry: the raw text is "" and every probability is null.
    expect(table, LOGPROB_SCHEMA, logprob_rows(prompt_id, "OTHER", None, None, True))


def test_letter_logprob_first_token_is_the_default(tmp_path, key_env):
    workflow, prompt_id = live(tmp_path, yn_question)
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(None, logprobs=CHANNEL))
    # The first entry is "<|channel|>": not a letter, and no letter in its top.
    expect(table, LOGPROB_SCHEMA, logprob_rows(prompt_id, "OTHER", None, None, True))


def test_letter_logprob_word_letters(tmp_path, key_env):
    def writer(directory):
        return yn_question(directory, readout_table='letters = ["Yes", "No", "Maybe"]')

    workflow, prompt_id = live(tmp_path, writer)
    top = [(" Yes", -0.2), ("No", -1.7), ("yes", -0.9)]
    table, _ = run_with(
        tmp_path, workflow, lambda p, n: chat("Yes", logprobs=[("Yes", top)])
    )
    probs = contract_p(top, ["Yes", "No", "Maybe"], "sum")
    assert probs[2] == 0.0
    schema = {
        "id": pl.String,
        "code": pl.String,
        "repeat": pl.Int64,
        **CALL,
        "label": pl.String,
        "p_yes": pl.Float64,
        "p_no": pl.Float64,
        "p_maybe": pl.Float64,
        **TOKENS,
        "parse_failure": pl.Boolean,
    }
    rows = [
        (
            "a1",
            code,
            1,
            "m1",
            "stub-model",
            None,
            prompt_id,
            "Yes",
            *probs,
            10,
            2,
            False,
        )
        for code in ("BLUE", "GREEN", "RED")
    ]
    expect(table, schema, rows)


@pytest.mark.parametrize(
    "letters",
    [
        '["Y", "y"]',
        '["Y", "Y"]',
        '["Y!", "N"]',
        '[""]',
        "[]",
        '["Y", 1]',
        '["OTHER", "N"]',
    ],
)
def test_letter_logprob_bad_letters(tmp_path, letters):
    yn_question(
        tmp_path / "q", readout_table=f"letters = {letters}", lists={"a": "adt"}
    )
    with pytest.raises(tagger.QuestionError):
        tagger.load_question(tmp_path / "q")


# --------------------------------------------------------------------------
# letter_text, single (4.4)
# --------------------------------------------------------------------------

TEXT_SCHEMA = {
    "id": pl.String,
    "repeat": pl.Int64,
    **CALL,
    "label": pl.String,
    "retried": pl.Boolean,
    **TOKENS,
    "parse_failure": pl.Boolean,
}


def single_writer(budget="max_tokens = 5\nretry_max_tokens = 50"):
    def writer(directory):
        return write_question(
            directory,
            name="test/single",
            level="work",
            readout="letter_text",
            blocks={"SYS": "Answer Y or N.", "USR": "Text: {title}"},
            fill_user={"title": "text:title"},
            lists={},
            fields=["title"],
            readout_table='letters = ["Y", "N"]',
            budget=budget,
        )

    return writer


@pytest.mark.parametrize(
    ("content", "label"),
    [(" Y \n", "Y"), ("N", "N"), ("y", "OTHER"), ("Yes", "OTHER"), (None, "OTHER")],
)
def test_letter_text_single_reading(tmp_path, key_env, content, label):
    workflow, prompt_id = live(tmp_path, single_writer("max_tokens = 5"))
    table, endpoint = run_with(tmp_path, workflow, lambda p, n: chat(content))
    expect(
        table,
        TEXT_SCHEMA,
        [
            (
                "a1",
                1,
                "m1",
                "stub-model",
                None,
                prompt_id,
                label,
                False,
                10,
                2,
                label == "OTHER",
            )
        ],
    )
    [payload] = endpoint.requests
    assert payload["top_logprobs"] == 0 and payload["logprobs"] is False


# (finish_reason, tokens_out, budget_rule) -> asked again
RETRY_CASES = [
    ("length", 2, "spent", True),
    ("stop", 5, "spent", True),
    ("stop", 9, "spent", True),
    ("stop", 4, "spent", False),
    ("length", 2, "tokens", False),
    ("stop", 5, "tokens", True),
    ("length", 2, "length", True),
    ("stop", 5, "length", False),
]


@pytest.mark.parametrize(("finish", "tout", "rule", "again"), RETRY_CASES)
def test_budget_retry_rules(tmp_path, key_env, finish, tout, rule, again):
    pass_extra = "" if rule == "spent" else f'budget_rule = "{rule}"'
    workflow, prompt_id = live(tmp_path, single_writer(), pass_extra=pass_extra)
    script = [
        chat("Maybe", finish=finish, tout=tout, tin=11, served="first", fp="f1"),
        chat("N", tout=7, tin=12, served="second", fp="f2"),
    ]
    table, endpoint = run_with(tmp_path, workflow, lambda p, n: script[n])
    if again:
        assert len(endpoint.requests) == 2
        first, second = endpoint.requests
        assert first["max_tokens"] == 5 and second["max_tokens"] == 50
        assert {**second, "max_tokens": 5} == first
        row = ("a1", 1, "m1", "second", "f2", prompt_id, "N", True, 12, 7, False)
    else:
        assert len(endpoint.requests) == 1
        row = ("a1", 1, "m1", "first", "f1", prompt_id, "OTHER", False, 11, tout, True)
    expect(table, TEXT_SCHEMA, [row])
    # Contract 3.6: with retry_max_tokens set, the run id holds the pass's rule.
    assert table["run_id"].to_list() == [
        contract_run_id(
            prompt_ids={"": prompt_id},
            readout="letter_text",
            layout="single",
            letters=["Y", "N"],
            model="m1",
            seed=7,
            temperature=0.0,
            max_tokens=5,
            retry_max_tokens=50,
            top_logprobs=0,
            extra_body={"logprobs": False},
            reasoning="off",
            budget_rule=rule,
            null_text="",
        )
    ]


def test_budget_retry_is_made_once(tmp_path, key_env):
    workflow, prompt_id = live(tmp_path, single_writer())
    endpoint_answer = lambda p, n: chat("Maybe", finish="length", tout=p["max_tokens"])
    table, endpoint = run_with(tmp_path, workflow, endpoint_answer)
    assert [r["max_tokens"] for r in endpoint.requests] == [5, 50]
    expect(
        table,
        TEXT_SCHEMA,
        [("a1", 1, "m1", "stub-model", None, prompt_id, "OTHER", True, 10, 50, True)],
    )


def test_readable_answer_is_never_retried(tmp_path, key_env):
    workflow, prompt_id = live(tmp_path, single_writer())
    table, endpoint = run_with(
        tmp_path, workflow, lambda p, n: chat("Y", finish="length", tout=5)
    )
    assert len(endpoint.requests) == 1
    expect(
        table,
        TEXT_SCHEMA,
        [("a1", 1, "m1", "stub-model", None, prompt_id, "Y", False, 10, 5, False)],
    )


def test_no_retry_without_retry_max_tokens(tmp_path, key_env):
    workflow, _ = live(tmp_path, single_writer("max_tokens = 5"))
    _, endpoint = run_with(
        tmp_path, workflow, lambda p, n: chat("Maybe", finish="length", tout=5)
    )
    assert len(endpoint.requests) == 1


def test_retries_go_in_one_batch_after_the_sub_chunk(tmp_path, key_env):
    """Contract 4.4: after a sub-chunk's calls, the spent ones are asked again together."""
    workflow, _ = live(tmp_path, single_writer(), texts=TEXTS)

    def answer(payload, n):
        if payload["max_tokens"] == 50:
            return chat("Y")
        return chat("Maybe", finish="length", tout=5)

    _, endpoint = run_with(tmp_path, workflow, answer)
    assert [r["max_tokens"] for r in endpoint.requests] == [5, 5, 5, 50, 50, 50]
    assert endpoint.users()[:3] == endpoint.users()[3:]


def test_retry_answer_is_cached_under_its_own_key(tmp_path, key_env):
    workflow, _ = live(tmp_path, single_writer())
    script = [chat("Maybe", finish="length", tout=5), chat("N", tout=7)]
    run_with(tmp_path, workflow, lambda p, n: script[n])
    files = sorted((tmp_path / "cache").rglob("*.json"))
    requests = [json.loads(f.read_text("utf-8"))["request"] for f in files]
    assert sorted(r["max_tokens"] for r in requests) == [5, 50]
    shutil.rmtree(tmp_path / "runs")
    [result] = tagger.run(workflow, replay=True)
    table = pl.read_parquet(result.output)
    assert table.select("label", "retried").rows() == [("N", True)]


# --------------------------------------------------------------------------
# letter_text, table (4.4)
# --------------------------------------------------------------------------

TABLE_SCHEMA = {
    "id": pl.String,
    "code": pl.String,
    "repeat": pl.Int64,
    **CALL,
    "label": pl.String,
    "retried": pl.Boolean,
    **TOKENS,
    "parse_failure": pl.Boolean,
}


def table_writer(budget="max_tokens = 300"):
    def writer(directory):
        return write_question(
            directory,
            name="test/table",
            level="work",
            readout="letter_text",
            blocks={"SYS": "Fill the table.", "USR": "Text: {title}"},
            fill_user={"title": "text:title"},
            fields=["title"],
            readout_table='letters = ["Y", "N"]\nlayout = "table"\ntable = "COLOURS"',
            budget=budget,
        )

    return writer


def table_rows(prompt_id, letters, failure, tout=2, retried=False):
    by_code = dict(zip(["RED", "GREEN", "BLUE"], letters, strict=True))
    return [
        (
            "a1",
            code,
            1,
            "m1",
            "stub-model",
            None,
            prompt_id,
            by_code[code],
            retried,
            10,
            tout,
            failure,
        )
        for code in ("BLUE", "GREEN", "RED")
    ]


READABLE_TABLES = {
    "plain": "=== COLOURS ===\n1 Y N Y",
    "pipes and header": (
        "Here is the table.\n=== COLOURS ===\n| # | RED | GREEN | BLUE |\n"
        "|---|---|---|---|\n| 1 | Y | N | Y |\n"
    ),
    "in a code fence": "```\n=== COLOURS ===\n1 | Y | N | Y\n```",
    "backticks on lines": "  `=== COLOURS ===`  \n `1 | Y | N | Y` ",
    "another table first": "=== SHADES ===\n1 N N N\n=== COLOURS ===\n1 Y N Y",
    "another table after": "=== COLOURS ===\n1 Y N Y\n=== SHADES ===\n1 N N N",
}

UNREADABLE_TABLES = {
    "no table": "1 Y N Y",
    "two work lines": "=== COLOURS ===\n1 Y N Y\n1 Y N Y",
    "no work line": "=== COLOURS ===\n2 Y N Y",
    "too few letters": "=== COLOURS ===\n1 Y N",
    "too many letters": "=== COLOURS ===\n1 Y N Y N",
    "letter outside the set": "=== COLOURS ===\n1 Y N Q",
    "work line in another table": "=== COLOURS ===\n=== SHADES ===\n1 Y N Y",
    "spaced title": "=== COLOURS  ===\n1 Y N Y",
    "empty": "",
}


@pytest.mark.parametrize("case", sorted(READABLE_TABLES))
def test_letter_text_table_readable(tmp_path, key_env, case):
    workflow, prompt_id = live(tmp_path, table_writer())
    table, endpoint = run_with(
        tmp_path, workflow, lambda p, n: chat(READABLE_TABLES[case])
    )
    expect(table, TABLE_SCHEMA, table_rows(prompt_id, ["Y", "N", "Y"], False))
    [payload] = endpoint.requests
    assert set(payload) == {
        "model",
        "messages",
        "temperature",
        "max_tokens",
        "seed",
        "logprobs",
    }
    assert payload["logprobs"] is False
    assert table["run_id"].unique().to_list() == [
        contract_run_id(
            prompt_ids={"": prompt_id},
            readout="letter_text",
            layout="table",
            letters=["Y", "N"],
            model="m1",
            seed=7,
            temperature=0.0,
            max_tokens=300,
            extra_body={"logprobs": False},
            reasoning="off",
            null_text="",
        )
    ]


@pytest.mark.parametrize("case", sorted(UNREADABLE_TABLES))
def test_letter_text_table_unreadable(tmp_path, key_env, case):
    workflow, prompt_id = live(tmp_path, table_writer())
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(UNREADABLE_TABLES[case]))
    expect(table, TABLE_SCHEMA, table_rows(prompt_id, ["OTHER"] * 3, True))


def test_letter_text_table_budget_retry(tmp_path, key_env):
    workflow, prompt_id = live(
        tmp_path,
        table_writer("max_tokens = 300\nretry_max_tokens = 900"),
        pass_extra='budget_rule = "length"',
    )
    script = [
        chat("=== COLOURS ===\n1 Y", finish="length"),
        chat("=== COLOURS ===\n1 N N Y", tout=4),
    ]
    table, endpoint = run_with(tmp_path, workflow, lambda p, n: script[n])
    assert [r["max_tokens"] for r in endpoint.requests] == [300, 900]
    expect(
        table,
        TABLE_SCHEMA,
        table_rows(prompt_id, ["N", "N", "Y"], False, tout=4, retried=True),
    )


# --------------------------------------------------------------------------
# json_object, label_object (4.5)
# --------------------------------------------------------------------------

FIELDS = """\
form = "label_object"
schema = true
schema_name = "colour_items"

[[readout.fields]]
name = "verdict"
type = "letter"
letters = ["Y", "N"]

[[readout.fields]]
name = "reason"
type = "string"

[[readout.fields]]
name = "evidence"
type = "quote"

[[readout.fields]]
name = "certain"
type = "boolean"

[[readout.fields]]
name = "rank"
type = "integer"

[[readout.fields]]
name = "weight"
type = "number"
"""

OBJECT_SCHEMA = {
    "id": pl.String,
    "code": pl.String,
    "repeat": pl.Int64,
    **CALL,
    "verdict": pl.String,
    "reason": pl.String,
    "evidence": pl.String,
    "certain": pl.Boolean,
    "rank": pl.Int64,
    "weight": pl.Float64,
    "quotes_ok": pl.Boolean,
    "retried": pl.Boolean,
    **TOKENS,
    "parse_failure": pl.Boolean,
}


def object_writer(readout_table=FIELDS, budget="max_tokens = 400"):
    def writer(directory):
        return write_question(
            directory,
            name="test/object",
            level="work",
            readout="json_object",
            blocks={"SYS": "Judge each colour.", "USR": "Text: {title}\n{abstract}"},
            fill_user={"title": "text:title", "abstract": "text:abstract"},
            readout_table=readout_table,
            budget=budget,
        )

    return writer


def item(verdict="Y", reason="r", evidence="", certain=True, rank=1, weight=0.5):
    return {
        "verdict": verdict,
        "reason": reason,
        "evidence": evidence,
        "certain": certain,
        "rank": rank,
        "weight": weight,
    }


GOOD_ITEMS = {
    "RED": item("Y", "red", "tea\nLeav", True, 1, 0.25),
    "GREEN": item("N", "green", "  ", False, 2, 1.5),
    "BLUE": item("Y", "blue", "", True, -3, 2.0),
}


# Contract 4.5: the item schema of the declared fields, by the type table.
DECLARED_ITEM = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["Y", "N"]},
        "reason": {"type": "string"},
        "evidence": {"type": "string"},
        "certain": {"type": "boolean"},
        "rank": {"type": "integer"},
        "weight": {"type": "number"},
    },
    "required": ["verdict", "reason", "evidence", "certain", "rank", "weight"],
    "additionalProperties": False,
}


def test_label_object_request(tmp_path, key_env):
    workflow, _ = live(tmp_path, object_writer())
    _, endpoint = run_with(
        tmp_path, workflow, lambda p, n: chat(json.dumps(GOOD_ITEMS))
    )
    [payload] = endpoint.requests
    item_schema = DECLARED_ITEM
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "colour_items",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "RED": item_schema,
                    "GREEN": item_schema,
                    "BLUE": item_schema,
                },
                "required": ["RED", "GREEN", "BLUE"],
                "additionalProperties": False,
            },
        },
    }
    assert payload["logprobs"] is False
    assert "top_logprobs" not in payload


def test_label_object_without_schema_sends_no_response_format(tmp_path, key_env):
    workflow, _ = live(
        tmp_path, object_writer(FIELDS.replace("schema = true", "schema = false"))
    )
    _, endpoint = run_with(
        tmp_path, workflow, lambda p, n: chat(json.dumps(GOOD_ITEMS))
    )
    [payload] = endpoint.requests
    assert set(payload) == {
        "model",
        "messages",
        "temperature",
        "max_tokens",
        "seed",
        "logprobs",
    }


def test_label_object_reading(tmp_path, key_env):
    workflow, prompt_id = live(tmp_path, object_writer())
    content = "Sure.\n" + json.dumps(GOOD_ITEMS) + "\nDone."
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(content))
    # "tea\nLeav" is in "Green tea\nLeaves."; empty quotes are not checked.
    rows = [
        (
            "a1",
            "BLUE",
            1,
            "m1",
            "stub-model",
            None,
            prompt_id,
            "Y",
            "blue",
            "",
            True,
            -3,
            2.0,
            True,
            False,
            10,
            2,
            False,
        ),
        (
            "a1",
            "GREEN",
            1,
            "m1",
            "stub-model",
            None,
            prompt_id,
            "N",
            "green",
            "  ",
            False,
            2,
            1.5,
            True,
            False,
            10,
            2,
            False,
        ),
        (
            "a1",
            "RED",
            1,
            "m1",
            "stub-model",
            None,
            prompt_id,
            "Y",
            "red",
            "tea\nLeav",
            True,
            1,
            0.25,
            True,
            False,
            10,
            2,
            False,
        ),
    ]
    expect(table, OBJECT_SCHEMA, rows)


def test_label_object_quote_not_in_the_text(tmp_path, key_env):
    workflow, _ = live(tmp_path, object_writer())
    items = {**GOOD_ITEMS, "BLUE": item(evidence="coffee")}
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(json.dumps(items)))
    # Checked, never rejected: the reply stays readable. quotes_ok is per label
    # row (4.5): GREEN's quote is blank, RED's is in the text.
    assert table.select("code", "quotes_ok").rows() == [
        ("BLUE", False),
        ("GREEN", True),
        ("RED", True),
    ]
    assert table["parse_failure"].to_list() == [False, False, False]
    assert table["evidence"].to_list() == ["coffee", "  ", "tea\nLeav"]


def test_label_object_quote_uses_null_text(tmp_path, key_env):
    """The joined text is the fields in order, a null as the pass's null_text."""
    b2 = TEXTS.filter(
        pl.col("id") == "b2"
    )  # title "Red kite été {abstract}", abstract null
    workflow, _ = live(
        tmp_path, object_writer(), texts=b2, pass_extra='null_text = "n/a"'
    )
    items = {**GOOD_ITEMS, "RED": item(evidence="été {abstract}\nn/a")}
    table, endpoint = run_with(tmp_path, workflow, lambda p, n: chat(json.dumps(items)))
    assert endpoint.users() == ["Text: Red kite été {abstract}\nn/a"]
    assert table["quotes_ok"].to_list() == [True, True, True]


UNREADABLE_OBJECTS = {
    "missing label": {"RED": GOOD_ITEMS["RED"], "GREEN": GOOD_ITEMS["GREEN"]},
    "extra label": {**GOOD_ITEMS, "PINK": item()},
    "missing field": {
        **GOOD_ITEMS,
        "BLUE": {k: v for k, v in item().items() if k != "rank"},
    },
    "letter outside the set": {**GOOD_ITEMS, "BLUE": item(verdict="Maybe")},
    "string not a string": {**GOOD_ITEMS, "BLUE": item(reason=3)},
    "boolean not a boolean": {**GOOD_ITEMS, "BLUE": item(certain="yes")},
    "integer not an integer": {**GOOD_ITEMS, "BLUE": item(rank=1.5)},
    "number not a number": {**GOOD_ITEMS, "BLUE": item(weight="0.5")},
    "item not an object": {**GOOD_ITEMS, "BLUE": "Y"},
    # Read from the first "{" to the last "}" (4.5): two objects in a list leave
    # "{...}, {...}", which does not load.
    "two objects": [GOOD_ITEMS, GOOD_ITEMS],
}


@pytest.mark.parametrize("case", sorted(UNREADABLE_OBJECTS))
def test_label_object_one_bad_item_fails_the_reply(tmp_path, key_env, case):
    workflow, prompt_id = live(tmp_path, object_writer())
    content = json.dumps(UNREADABLE_OBJECTS[case])
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(content))
    rows = [
        (
            "a1",
            code,
            1,
            "m1",
            "stub-model",
            None,
            prompt_id,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            10,
            2,
            True,
        )
        for code in ("BLUE", "GREEN", "RED")
    ]
    expect(table, OBJECT_SCHEMA, rows)


@pytest.mark.parametrize("content", ["no braces at all", "{not json}", "", None])
def test_label_object_unloadable_reply(tmp_path, key_env, content):
    workflow, _ = live(tmp_path, object_writer())
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(content))
    assert table["parse_failure"].to_list() == [True, True, True]
    assert table["verdict"].to_list() == [None, None, None]
    assert table["quotes_ok"].to_list() == [None, None, None]


def test_label_object_without_quote_field_has_no_quotes_ok(tmp_path, key_env):
    fields = FIELDS.split('[[readout.fields]]\nname = "evidence"')[0] + (
        '[[readout.fields]]\nname = "certain"\ntype = "boolean"\n'
    )
    workflow, _ = live(tmp_path, object_writer(fields))
    items = {
        code: {"verdict": "Y", "reason": "x", "certain": True}
        for code in ("RED", "GREEN", "BLUE")
    }
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(json.dumps(items)))
    assert "quotes_ok" not in table.columns
    assert table.columns[-6:] == [
        "reason",
        "certain",
        "retried",
        "tokens_in",
        "tokens_out",
        "parse_failure",
    ]


def test_label_object_budget_retry(tmp_path, key_env):
    workflow, _ = live(
        tmp_path, object_writer(budget="max_tokens = 400\nretry_max_tokens = 800")
    )
    script = [
        chat('{"RED": {"verdict"', finish="length", tout=400),
        chat(json.dumps(GOOD_ITEMS)),
    ]
    table, endpoint = run_with(tmp_path, workflow, lambda p, n: script[n])
    assert [r["max_tokens"] for r in endpoint.requests] == [400, 800]
    assert table["retried"].to_list() == [True, True, True]
    assert table["parse_failure"].to_list() == [False, False, False]


# --------------------------------------------------------------------------
# answer models from Python (4.5, 10.1)
# --------------------------------------------------------------------------


def answer_items(**fields):
    return chat(json.dumps({c: dict(fields) for c in ("RED", "GREEN", "BLUE")}))


def test_answer_model_schema_columns_and_run_id(tmp_path, key_env):
    """Contract 4.5: the item schema, one column per field in model order, typed."""
    from typing import Literal

    import pydantic

    class Item(pydantic.BaseModel):
        verdict: Literal["Y", "N"]
        evidence: tagger.Quote
        strong: bool
        rank: int = pydantic.Field(ge=0)
        weight: float

    workflow, prompt_id = live(tmp_path, object_writer())
    reply = answer_items(verdict="Y", evidence="Green", strong=True, rank=2, weight=0.5)
    endpoint = Endpoint(lambda p, n: reply)
    [result] = tagger.run(
        workflow, answer_models={"p": Item}, transport=endpoint.transport
    )
    [payload] = endpoint.requests
    expected_item = {**Item.model_json_schema(), "additionalProperties": False}
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "colour_items",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {c: expected_item for c in ("RED", "GREEN", "BLUE")},
                "required": ["RED", "GREEN", "BLUE"],
                "additionalProperties": False,
            },
        },
    }
    assert payload["response_format"] == response_format
    schema = {
        "id": pl.String,
        "code": pl.String,
        "repeat": pl.Int64,
        **CALL,
        "verdict": pl.String,
        "evidence": pl.String,
        "strong": pl.Boolean,
        "rank": pl.Int64,
        "weight": pl.Float64,
        "quotes_ok": pl.Boolean,
        "retried": pl.Boolean,
        **TOKENS,
        "parse_failure": pl.Boolean,
    }
    rows = [
        (
            "a1",
            c,
            1,
            "m1",
            "stub-model",
            None,
            prompt_id,
            "Y",
            "Green",
            True,
            2,
            0.5,
            True,
            False,
            10,
            2,
            False,
        )
        for c in ("BLUE", "GREEN", "RED")
    ]
    table = pl.read_parquet(result.output)
    expect(table, schema, rows)
    assert table["run_id"].unique().to_list() == [
        contract_run_id(
            prompt_ids={"": prompt_id},
            readout="json_object",
            form="label_object",
            answer_schema=expected_item,
            model="m1",
            seed=7,
            temperature=0.0,
            max_tokens=400,
            response_format=response_format,
            extra_body={"logprobs": False},
            reasoning="off",
            null_text="",
        )
    ]


def test_declared_fields_run_id(tmp_path, key_env):
    """The answer_schema of the run id is the item schema, sent or not (3.6)."""
    without = FIELDS.replace("schema = true", "schema = false")
    workflow, prompt_id = live(tmp_path, object_writer(without))
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(json.dumps(GOOD_ITEMS)))
    assert table["run_id"].unique().to_list() == [
        contract_run_id(
            prompt_ids={"": prompt_id},
            readout="json_object",
            form="label_object",
            answer_schema=DECLARED_ITEM,
            model="m1",
            seed=7,
            temperature=0.0,
            max_tokens=400,
            extra_body={"logprobs": False},
            reasoning="off",
            null_text="",
        )
    ]


def test_answer_model_validation_failure(tmp_path, key_env):
    import pydantic

    class Item(pydantic.BaseModel):
        verdict: str
        score: int = pydantic.Field(ge=0, le=10)

    workflow, _ = live(tmp_path, object_writer())
    items = {
        "RED": {"verdict": "Y", "score": 3},
        "GREEN": {"verdict": "Y", "score": 11},
        "BLUE": {"verdict": "N", "score": 0},
    }
    endpoint = Endpoint(lambda p, n: chat(json.dumps(items)))
    [result] = tagger.run(
        workflow, answer_models={"p": Item}, transport=endpoint.transport
    )
    table = pl.read_parquet(result.output)
    assert table.columns[-7:] == [
        "run_id",
        "verdict",
        "score",
        "retried",
        "tokens_in",
        "tokens_out",
        "parse_failure",
    ]
    assert table["parse_failure"].to_list() == [True, True, True]
    assert table["score"].to_list() == [None, None, None]


def unfit_models():
    import pydantic

    class Optional_(pydantic.BaseModel):
        verdict: str
        note: str | None

    class Default(pydantic.BaseModel):
        verdict: str
        note: str = "none"

    class Listed(pydantic.BaseModel):
        verdict: str
        notes: list[str]

    class Inner(pydantic.BaseModel):
        text: str

    class Nested(pydantic.BaseModel):
        verdict: str
        inner: Inner

    return {
        "nullable": Optional_,
        "default": Default,
        "array": Listed,
        "nested": Nested,
    }


@pytest.mark.parametrize("case", ["nullable", "default", "array", "nested"])
def test_answer_model_with_a_field_it_cannot_type(tmp_path, key_env, case):
    workflow, _ = live(tmp_path, object_writer())
    with pytest.raises(tagger.QuestionError):
        tagger.run(
            workflow,
            answer_models={"p": unfit_models()[case]},
            transport=Endpoint(never_called).transport,
        )
    assert not (tmp_path / "cache").exists()
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("target", ["nowhere", "not_label_object"])
def test_answer_model_for_an_unknown_or_unfit_pass(tmp_path, key_env, target):
    import pydantic

    class Item(pydantic.BaseModel):
        verdict: str

    write_texts(tmp_path, GREEN_TEA)
    object_writer()(tmp_path / "q")
    score_writer(tmp_path / "s")
    body = model_entry() + (
        '[[passes]]\nid = "p"\nquestion_dir = "q"\nmodels = ["m1"]\nunits = { rule = "all" }\n\n'
        '[[passes]]\nid = "not_label_object"\nquestion_dir = "s"\nmodels = ["m1"]\n'
        'units = { rule = "all" }\n'
    )
    workflow = tagger.load_workflow(write_workflow(tmp_path, body))
    with pytest.raises(tagger.WorkflowError):
        tagger.run(
            workflow,
            answer_models={target: Item},
            transport=Endpoint(never_called).transport,
        )
    assert not (tmp_path / "runs").exists()


# --------------------------------------------------------------------------
# quotes_ok per label row (4.5)
# --------------------------------------------------------------------------


def test_label_object_quotes_ok_scope(tmp_path, key_env):
    workflow, _ = live(tmp_path, object_writer())
    items = {
        "RED": item(evidence=""),
        "GREEN": item(evidence=" \n "),
        "BLUE": item(evidence="Green tea\nLeaves."),
    }
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(json.dumps(items)))
    # A label whose quotes are all blank is true; the whole joined text is a substring.
    assert table["quotes_ok"].to_list() == [True, True, True]


def test_label_object_quotes_ok_with_two_quote_fields(tmp_path, key_env):
    fields = FIELDS + '\n[[readout.fields]]\nname = "second"\ntype = "quote"\n'
    workflow, _ = live(tmp_path, object_writer(fields))
    items = {
        "RED": {**item(evidence="Green"), "second": "tea"},
        "GREEN": {**item(evidence="Green"), "second": "coffee"},
        "BLUE": {**item(evidence="milk"), "second": ""},
    }
    table, _ = run_with(tmp_path, workflow, lambda p, n: chat(json.dumps(items)))
    assert table.select("code", "quotes_ok").rows() == [
        ("BLUE", False),
        ("GREEN", False),
        ("RED", True),
    ]


# --------------------------------------------------------------------------
# the served model of a row standing on two calls (4.1, 8.2, 9)
# --------------------------------------------------------------------------

SIDES = """
[[sides]]
name = "pos"
block = "POS"

[[sides]]
name = "neg"
block = "NEG"

[blocks.fill.side]
colour = "a:name"
"""


def sides_writer(directory):
    return write_question(
        directory,
        name="test/sides",
        level="work x list",
        readout="letter_text",
        blocks={
            "SYS": "Answer Y or N.",
            "USR": "Text: {title}\n{question}",
            "POS": "Good for {colour}?",
            "NEG": "Bad for {colour}?",
        },
        fill_user={"title": "text:title", "question": "side"},
        fields=["title"],
        readout_table='letters = ["Y", "N"]',
        budget="max_tokens = 5",
        extra=SIDES,
    )


def test_model_served_of_sides_with_one_null(tmp_path, key_env):
    workflow, prompt_id = live(tmp_path, sides_writer)
    # Plan order RED, GREEN, BLUE; per unit pos then neg.
    served = [("m-a", None), (None, None), ("m-b", "m-a")]
    fingerprints = [(None, "f1"), (None, None), ("f2", "f2")]
    script = [
        chat(
            "Y",
            served=served[n // 2][n % 2],
            fp=fingerprints[n // 2][n % 2],
            tin=3 + n,
            tout=1,
        )
        for n in range(6)
    ]
    endpoint = Endpoint(lambda p, n: script[n])
    [result] = tagger.run(workflow, transport=endpoint.transport)
    assert endpoint.users()[:2] == [
        "Text: Green tea\nGood for Red?",
        "Text: Green tea\nBad for Red?",
    ]
    schema = {
        "id": pl.String,
        "code": pl.String,
        "repeat": pl.Int64,
        **CALL,
        "pos_label": pl.String,
        "neg_label": pl.String,
        "pos_retried": pl.Boolean,
        "neg_retried": pl.Boolean,
        "pos_tokens_in": pl.Int64,
        "pos_tokens_out": pl.Int64,
        "neg_tokens_in": pl.Int64,
        "neg_tokens_out": pl.Int64,
        **TOKENS,
        "parse_failure": pl.Boolean,
    }
    rows = [
        (
            "a1",
            "BLUE",
            1,
            "m1",
            "m-a|m-b",
            "f2",
            prompt_id,
            "Y",
            "Y",
            False,
            False,
            7,
            1,
            8,
            1,
            15,
            2,
            False,
        ),
        (
            "a1",
            "GREEN",
            1,
            "m1",
            None,
            None,
            prompt_id,
            "Y",
            "Y",
            False,
            False,
            5,
            1,
            6,
            1,
            11,
            2,
            False,
        ),
        (
            "a1",
            "RED",
            1,
            "m1",
            "m-a",
            "f1",
            prompt_id,
            "Y",
            "Y",
            False,
            False,
            3,
            1,
            4,
            1,
            7,
            2,
            False,
        ),
    ]
    expect(pl.read_parquet(result.output), schema, rows)
    manifest = json.loads(
        (tmp_path / "runs" / "wf" / "p" / "m1" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    # A null is counted under "" (contract 9).
    assert manifest["models_served"] == {"m-a": 2, "m-b": 1, "": 3}
    assert manifest["system_fingerprints"] == {"f1": 1, "f2": 2, "": 3}


@pytest.mark.parametrize("value", ["", 7, ["m"]])
def test_model_served_must_be_a_non_empty_string(tmp_path, key_env, value):
    workflow, _ = live(tmp_path, score_writer)
    body = chat('{"RED": 1, "GREEN": 2, "BLUE": 3}', served=None)
    body["model"] = value
    body["system_fingerprint"] = value
    table, _ = run_with(tmp_path, workflow, lambda p, n: body)
    assert table["model_served"].to_list() == [None, None, None]
    assert table["system_fingerprint"].to_list() == [None, None, None]
