"""The workflow file (contract 6.1 to 6.3, 7) and the presets (7.5, D009, D018).

Every refusal here is a `WorkflowError` raised by `load_workflow` before any
call and any write (section 11). The body sent for each reasoning setting is
checked on the wire through a stub endpoint.
"""

from __future__ import annotations

import json
import re
import shutil
import tomllib

import pytest
from conftest import (
    PACKAGE,
    TEXTS,
    Endpoint,
    chat,
    model_entry,
    never_called,
    score_question,
    write_question,
    write_texts,
    write_workflow,
    yn_question,
)

import sdg_tech_impact_tagger as tagger

CONTRACT = PACKAGE.parents[1] / "docs" / "contract.md"

PASSES = """
[[passes]]
id = "p"
question_dir = "q"
models = ["m1"]
units = { rule = "all" }

[[passes]]
id = "yn"
question_dir = "yn"
models = ["m1"]
units = { rule = "threshold", from = "p", model = "same", at_least = 0.2 }
"""


def project(tmp_path, body=None, *, models=None, run_extra=""):
    """Texts, the colour score question `q`, the colour Y/N question `yn`, and a workflow."""
    write_texts(tmp_path)
    score_question(tmp_path / "q")
    yn_question(tmp_path / "yn")
    models = model_entry() if models is None else models
    return write_workflow(
        tmp_path, models + (PASSES if body is None else body), run_extra=run_extra
    )


def refused(path):
    with pytest.raises(tagger.WorkflowError) as info:
        tagger.load_workflow(path)
    assert not (path.parent / "runs").exists()
    assert not (path.parent / "cache").exists()
    return str(info.value)


def edit(path, old, new, count=1):
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    return path


def test_the_base_workflow_loads(tmp_path):
    tagger.load_workflow(project(tmp_path))


# --------------------------------------------------------------------------
# unknown keys at every level (D015)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new", "key"),
    [
        ('name = "wf"', 'name = "wf"\nthreads = 4', "threads"),
        ("seed = 7", "seed = 7\ntop_p = 0.9", "top_p"),
        ('id = "p"', 'id = "p"\nnotes = "x"', "notes"),
        ('units = { rule = "all" }', 'units = { rule = "all", every = true }', "every"),
        ("at_least = 0.2", "at_least = 0.2, at_most = 0.9", "at_most"),
    ],
)
def test_unknown_keys_are_refused_with_their_name(tmp_path, old, new, key):
    message = refused(edit(project(tmp_path), old, new))
    assert key in message


def test_unknown_top_level_table(tmp_path):
    path = project(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8") + "\n[extras]\nx = 1\n", encoding="utf-8"
    )
    assert "extras" in refused(path)


def test_unknown_key_in_a_budget_table(tmp_path):
    path = project(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n[passes.budgets.m1]\nmax_tokens = 2\ntemperature = 1.0\n",
        encoding="utf-8",
    )
    assert "temperature" in refused(path)


# --------------------------------------------------------------------------
# missing keys, wrong types and values
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        'endpoint = "http://stub.test/v1"',
        'api_key_env = "TAGGER_TEST_KEY"',
        'model = "m1"',
        "seed = 7",
        'reasoning = "off"',
        'reasoning_style = "omit"',
    ],
)
def test_required_model_keys(tmp_path, line):
    refused(edit(project(tmp_path), line + "\n", ""))


@pytest.mark.parametrize(
    "line", ['id = "p"\n', 'models = ["m1"]\n', 'units = { rule = "all" }\n']
)
def test_required_pass_keys(tmp_path, line):
    refused(edit(project(tmp_path), line, ""))


def test_run_name_is_required(tmp_path):
    refused(edit(project(tmp_path), 'name = "wf"\n', ""))


def test_question_and_question_dir_exactly_one(tmp_path):
    refused(
        edit(
            project(tmp_path),
            'question_dir = "q"',
            'question_dir = "q"\nquestion = "protocol_v1/sdg_pass1"',
        )
    )


def test_neither_question_nor_question_dir(tmp_path):
    refused(edit(project(tmp_path), 'question_dir = "q"\n', ""))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('name = "wf"', 'name = "w f"'),
        ('name = "wf"', 'name = ""'),
        ("[models.m1]", "[models.M1]"),
        ("[models.m1]", "[models.1m]"),
        ('id = "p"', 'id = "P"'),
        ('id = "p"', 'id = "1p"'),
        ("seed = 7", 'seed = "7"'),
        ("seed = 7", "seed = 7.5"),
        ("temperature = 0.0", 'temperature = "0"'),
        ("concurrency = 1", "concurrency = 0"),
        ('reasoning = "off"', 'reasoning = "maybe"'),
        ('reasoning = "off"', "reasoning = false"),
        ('reasoning_style = "omit"', 'reasoning_style = "think"'),
        ('units = { rule = "all" }', 'units = { rule = "every" }'),
        ("at_least = 0.2", "at_least = true"),
        ('model = "same"', 'model = "m9"'),
    ],
)
def test_wrong_values(tmp_path, old, new):
    refused(edit(project(tmp_path), old, new))


@pytest.mark.parametrize(
    "line",
    [
        "chunk_size = 0",
        "sub_chunk = 0",
        "attempts = 0",
        "repeats = 0",
        'chunk_size = "10"',
        'budget_rule = "never"',
        "null_text = 3",
        'prompt_prefix = "P3!"',
        'spelling = "both"',
    ],
)
def test_wrong_pass_values(tmp_path, line):
    refused(
        edit(
            project(tmp_path),
            'units = { rule = "all" }\n',
            'units = { rule = "all" }\n' + line + "\n",
        )
    )


@pytest.mark.parametrize(
    "line",
    [
        "max_retries = -1",
        'timeout_s = "fast"',
        'extraction = "last_token"',
        "expect_model = 3",
    ],
)
def test_wrong_model_values(tmp_path, line):
    refused(edit(project(tmp_path), "seed = 7\n", "seed = 7\n" + line + "\n"))


def test_repeated_pass_id(tmp_path):
    refused(edit(project(tmp_path), 'id = "yn"', 'id = "p"'))


@pytest.mark.parametrize("models", ["[]", '["m1", "m1"]', '"m1"'])
def test_pass_models_non_empty_and_unique(tmp_path, models):
    refused(edit(project(tmp_path), 'models = ["m1"]', f"models = {models}"))


def test_unknown_model(tmp_path):
    refused(edit(project(tmp_path), 'models = ["m1"]', 'models = ["m2"]'))


def test_unknown_pass_in_a_rule(tmp_path):
    refused(edit(project(tmp_path), 'from = "p"', 'from = "nowhere"'))


def test_a_later_pass_in_a_rule(tmp_path):
    body = """
[[passes]]
id = "yn"
question_dir = "yn"
models = ["m1"]
units = { rule = "threshold", from = "p", model = "same", at_least = 0.2 }

[[passes]]
id = "p"
question_dir = "q"
models = ["m1"]
units = { rule = "all" }
"""
    refused(project(tmp_path, body))


def test_budgets_of_an_unknown_model(tmp_path):
    path = project(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8") + "\n[passes.budgets.m9]\nmax_tokens = 2\n",
        encoding="utf-8",
    )
    refused(path)


@pytest.mark.parametrize(("max_tokens", "retry"), [(5, 5), (5, 4)])
def test_retry_max_tokens_must_be_above_max_tokens(tmp_path, max_tokens, retry):
    write_texts(tmp_path)
    yn_question(tmp_path / "yn", readout="letter_text", budget="max_tokens = 5")
    body = model_entry() + (
        '[[passes]]\nid = "yn"\nquestion_dir = "yn"\nmodels = ["m1"]\nunits = { rule = "all" }\n\n'
        f"[passes.budgets.m1]\nmax_tokens = {max_tokens}\nretry_max_tokens = {retry}\n"
    )
    refused(write_workflow(tmp_path, body))


def test_retry_max_tokens_in_a_question_must_be_above_max_tokens(tmp_path):
    write_texts(tmp_path)
    yn_question(
        tmp_path / "yn",
        readout="letter_text",
        budget="max_tokens = 5\nretry_max_tokens = 5",
    )
    body = (
        model_entry()
        + '[[passes]]\nid = "yn"\nquestion_dir = "yn"\nmodels = ["m1"]\nunits = { rule = "all" }\n'
    )
    with pytest.raises((tagger.QuestionError, tagger.WorkflowError)):
        tagger.load_workflow(write_workflow(tmp_path, body))


# --------------------------------------------------------------------------
# readouts and models (D006, D007, D011)
# --------------------------------------------------------------------------


def test_letter_logprob_with_reasoning_on_is_refused(tmp_path):
    refused(
        project(tmp_path, models=model_entry(reasoning="on", style="enable_thinking"))
    )


def test_letter_logprob_with_one_reasoning_model_among_several(tmp_path):
    models = model_entry() + model_entry("m2", model="m2", reasoning="on")
    body = PASSES.replace('models = ["m1"]', 'models = ["m1", "m2"]')
    refused(project(tmp_path, body, models=models))


def test_score_json_with_reasoning_on_loads(tmp_path):
    models = model_entry() + model_entry("m2", model="m2", reasoning="on")
    body = PASSES.replace('models = ["m1"]', 'models = ["m1", "m2"]', 1)
    tagger.load_workflow(project(tmp_path, body, models=models))


def test_spelling_only_on_letter_logprob(tmp_path):
    path = project(tmp_path)
    tagger.load_workflow(
        edit(path, "at_least = 0.2 }\n", 'at_least = 0.2 }\nspelling = "exact"\n')
    )
    refused(
        edit(
            path,
            'units = { rule = "all" }\n',
            'units = { rule = "all" }\nspelling = "sum"\n',
        )
    )


PAIR_MODELS = model_entry() + model_entry("m2", model="m2")
PAIR_BODY = (
    '[[passes]]\nid = "yn"\nquestion_dir = "yn"\nmodels = ["m1", "m2"]\nunits = { rule = "all" }\n\n'
    '[[passes]]\nid = "ys"\nquestion_dir = "ys"\nmodels = ["m1"]\nunits = { rule = "all" }\n\n'
    '[[passes]]\nid = "pair"\nquestion_dir = "pair"\nmodels = ["m1"]\n'
    'units = { rule = "cross", a = { from = "yn", models = ["m1", "m2"], positive = ["Y"]__A__ }, '
    'b = { from = "ys", models = ["m1"], positive = ["Y"] } }\n'
)


def pair_project(tmp_path, side_a: str):
    """Colour and shade Y/N passes, then a cross over both: side `a` gets `side_a` appended."""
    write_texts(tmp_path)
    yn_question(tmp_path / "yn")
    yn_question(tmp_path / "ys", lists={"a": "shade"})
    write_question(
        tmp_path / "pair",
        name="test/pair",
        level="work x list x list",
        readout="letter_text",
        blocks={"SYS": "Answer Y or N.", "USR": "{title}|{a}|{b}"},
        fill_user={"title": "text:title", "a": "a:id", "b": "b:id"},
        lists={"a": "colour", "b": "shade"},
        fields=["title"],
        readout_table='letters = ["Y", "N"]',
        budget="max_tokens = 5",
    )
    return write_workflow(tmp_path, PAIR_MODELS + PAIR_BODY.replace("__A__", side_a))


def test_cross_without_combine_over_several_models(tmp_path):
    tagger.load_workflow(pair_project(tmp_path, ', combine = "union"'))
    refused(pair_project(tmp_path, ""))
    refused(pair_project(tmp_path, ', combine = "majority"'))


def test_unknown_key_in_a_cross_side(tmp_path):
    assert "weight" in refused(
        pair_project(tmp_path, ', combine = "union", weight = 2')
    )


def test_cross_sides_must_read_different_lists(tmp_path):
    path = pair_project(tmp_path, ', combine = "union"')
    refused(edit(path, 'b = { from = "ys"', 'b = { from = "yn"'))


@pytest.mark.parametrize(
    ("units", "why"),
    [
        (
            '{ rule = "threshold", from = "p", model = "same", at_least = 0.2 }',
            "threshold on a work question",
        ),
        (
            '{ rule = "cross", a = { from = "yn", models = ["m1"], positive = ["Y"] }, b = { from = "yn", models = ["m1"], positive = ["N"] } }',
            "cross on a work question",
        ),
    ],
)
def test_a_rule_that_does_not_fit_the_level(tmp_path, units, why):
    body = (
        PASSES
        + f'\n[[passes]]\nid = "z"\nquestion_dir = "q"\nmodels = ["m1"]\nunits = {units}\n'
    )
    refused(project(tmp_path, body))


# --------------------------------------------------------------------------
# reasoning and extra_body on the wire (6.2, 6.3)
# --------------------------------------------------------------------------


def wire(tmp_path, key_env_value, *, reasoning, style, extra=""):
    write_texts(tmp_path, TEXTS.head(1))
    score_question(tmp_path / "q")
    body = model_entry(reasoning=reasoning, style=style, extra=extra) + (
        '[[passes]]\nid = "p"\nquestion_dir = "q"\nmodels = ["m1"]\nunits = { rule = "all" }\n'
    )
    endpoint = Endpoint(lambda p, n: chat('{"RED": 1, "GREEN": 2, "BLUE": 3}'))
    tagger.run(
        tagger.load_workflow(write_workflow(tmp_path, body)),
        transport=endpoint.transport,
    )
    [payload] = endpoint.requests
    [cache_file] = (tmp_path / "cache").rglob("*.json")
    request = json.loads(cache_file.read_text(encoding="utf-8"))["request"]
    return payload, request


BASE_FIELDS = {
    "model",
    "messages",
    "temperature",
    "max_tokens",
    "seed",
    "response_format",
}


@pytest.mark.parametrize(
    ("reasoning", "style", "extra", "added"),
    [
        ("off", "omit", "", {}),
        ("on", "omit", "", {}),
        (
            "off",
            "enable_thinking",
            "",
            {"chat_template_kwargs": {"enable_thinking": False}},
        ),
        (
            "on",
            "enable_thinking",
            "",
            {"chat_template_kwargs": {"enable_thinking": True}},
        ),
        ("off", "reasoning_effort", "", {"reasoning_effort": "none"}),
        (
            "on",
            "reasoning_effort",
            'reasoning_effort = "medium"',
            {"reasoning_effort": "medium"},
        ),
        (
            "on",
            "enable_thinking",
            "extra_body = { top_k = 20, chat_template_kwargs = { tools = false } }",
            {
                "chat_template_kwargs": {"enable_thinking": True, "tools": False},
                "top_k": 20,
            },
        ),
    ],
)
def test_reasoning_fields_on_the_wire_and_in_the_key(
    tmp_path, key_env, reasoning, style, extra, added
):
    payload, request = wire(
        tmp_path, key_env, reasoning=reasoning, style=style, extra=extra
    )
    assert {k: v for k, v in payload.items() if k not in BASE_FIELDS} == added
    # The keyed extra body is every wire field outside the readout's own (6.3).
    assert request["extra_body"] == added


@pytest.mark.parametrize(
    "extra",
    [
        "extra_body = { model = 'x' }",
        "extra_body = { messages = [] }",
        "extra_body = { temperature = 1.0 }",
        "extra_body = { max_tokens = 9 }",
        "extra_body = { seed = 1 }",
        "extra_body = { logprobs = true }",
        "extra_body = { top_logprobs = 3 }",
        "extra_body = { response_format = { type = 'text' } }",
        "extra_body = { reasoning_effort = 'high' }",
        "extra_body = { n = 2 }",
        "extra_body = { stream = true }",
        "extra_body = { chat_template_kwargs = { enable_thinking = true } }",
    ],
)
def test_reserved_extra_body_keys(tmp_path, extra):
    refused(project(tmp_path, models=model_entry(extra=extra)))


@pytest.mark.parametrize(
    ("reasoning", "style", "effort", "ok"),
    [
        ("on", "reasoning_effort", None, False),
        ("on", "reasoning_effort", "high", True),
        ("off", "reasoning_effort", "high", False),
        ("off", "reasoning_effort", None, True),
        ("on", "omit", "high", False),
        ("on", "enable_thinking", "high", False),
    ],
)
def test_reasoning_effort_rules(tmp_path, reasoning, style, effort, ok):
    extra = f'reasoning_effort = "{effort}"' if effort else ""
    write_texts(tmp_path)
    score_question(tmp_path / "q")
    body = model_entry(reasoning=reasoning, style=style, extra=extra) + (
        '[[passes]]\nid = "p"\nquestion_dir = "q"\nmodels = ["m1"]\nunits = { rule = "all" }\n'
    )
    path = write_workflow(tmp_path, body)
    if ok:
        tagger.load_workflow(path)
    else:
        refused(path)


def test_integer_temperature_keys_as_a_float(tmp_path, key_env):
    _, request = wire(tmp_path, key_env, reasoning="off", style="omit")
    shutil.rmtree(tmp_path / "cache")
    shutil.rmtree(tmp_path / "runs")
    path = tmp_path / "workflow.toml"
    edit(path, "temperature = 0.0", "temperature = 0")
    endpoint = Endpoint(lambda p, n: chat('{"RED": 1, "GREEN": 2, "BLUE": 3}'))
    tagger.run(tagger.load_workflow(path), transport=endpoint.transport)
    [cache_file] = (tmp_path / "cache").rglob("*.json")
    again = json.loads(cache_file.read_text(encoding="utf-8"))["request"]
    assert again == request and isinstance(again["temperature"], float)


# --------------------------------------------------------------------------
# paths (7.1, 7.2)
# --------------------------------------------------------------------------


def test_relative_paths_are_read_against_the_workflow(tmp_path, key_env, monkeypatch):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    path = project(project_dir, run_extra='output_dir = "out"\ncache_dir = "store"')
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    results = tagger.run(
        tagger.load_workflow(path),
        passes=["p"],
        transport=Endpoint(
            lambda p, n: chat('{"RED": 1, "GREEN": 2, "BLUE": 3}')
        ).transport,
    )
    assert (
        results[0].output.resolve()
        == (project_dir / "out" / "p" / "m1.parquet").resolve()
    )
    assert list((project_dir / "store").rglob("*.json"))
    assert (project_dir / "out" / "workflow.json").exists()
    assert not list(elsewhere.iterdir())


def test_cache_dirs_per_pass_and_model(tmp_path, key_env):
    path = project(tmp_path)
    edit(
        path,
        'units = { rule = "all" }\n',
        'units = { rule = "all" }\n\n[passes.cache_dirs]\nm1 = "old_cache"\n',
    )
    tagger.run(
        tagger.load_workflow(path),
        passes=["p"],
        transport=Endpoint(
            lambda p, n: chat('{"RED": 1, "GREEN": 2, "BLUE": 3}')
        ).transport,
    )
    assert len(list((tmp_path / "old_cache").rglob("*.json"))) == 3
    assert not (tmp_path / "cache").exists()


def test_env_file_setting(tmp_path, monkeypatch):
    monkeypatch.delenv("TAGGER_TEST_KEY", raising=False)
    path = project(tmp_path, run_extra='env_file = "secrets/keys.env"')
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "keys.env").write_text(
        "TAGGER_TEST_KEY=from-env-file\n", encoding="utf-8"
    )
    endpoint = Endpoint(lambda p, n: chat('{"RED": 1, "GREEN": 2, "BLUE": 3}'))
    tagger.run(tagger.load_workflow(path), passes=["p"], transport=endpoint.transport)
    assert {h["authorization"] for h in endpoint.headers} == {"Bearer from-env-file"}


def test_load_needs_exactly_one_of_path_and_preset(tmp_path):
    with pytest.raises((tagger.WorkflowError, TypeError, ValueError)):
        tagger.load_workflow()
    with pytest.raises((tagger.WorkflowError, TypeError, ValueError)):
        tagger.load_workflow(project(tmp_path), preset="protocol-v1")


def test_unknown_preset(tmp_path):
    with pytest.raises(tagger.WorkflowError):
        tagger.load_workflow(preset="protocol-v9")


def test_missing_workflow_file(tmp_path):
    with pytest.raises(tagger.WorkflowError):
        tagger.load_workflow(tmp_path / "absent.toml")


def test_not_toml(tmp_path):
    path = tmp_path / "workflow.toml"
    path.write_text("[run\nname = ", encoding="utf-8")
    with pytest.raises(tagger.WorkflowError):
        tagger.load_workflow(path)


def test_a_check_against_the_texts_happens_before_any_call(tmp_path, key_env):
    """A refusal raised by `run` before the first call writes nothing (11)."""
    path = project(tmp_path)
    with pytest.raises(tagger.TextsError):
        tagger.run(
            tagger.load_workflow(path),
            texts=TEXTS.drop("title"),
            transport=Endpoint(never_called).transport,
        )
    assert not (tmp_path / "runs").exists() and not (tmp_path / "cache").exists()


# --------------------------------------------------------------------------
# presets (7.5)
# --------------------------------------------------------------------------

PRESETS = PACKAGE / "presets"


def contract_example() -> dict:
    """The TOML of contract 7.4, read from docs/contract.md."""
    text = CONTRACT.read_text(encoding="utf-8")
    section = text.split("### 7.4 ", 1)[1].split("### 7.5 ", 1)[0]
    [block] = re.findall(r"```toml\n(.*?)```", section, flags=re.DOTALL)
    return tomllib.loads(block)


def preset(name: str) -> dict:
    return tomllib.loads((PRESETS / f"{name}.toml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["protocol-v1", "protocol-v1-impact", "paper-v1"])
def test_presets_ship_and_load(name):
    assert (PRESETS / f"{name}.toml").exists()
    tagger.load_workflow(preset=name)


def test_protocol_v1_impact_is_the_example_of_7_4():
    assert preset("protocol-v1-impact") == contract_example()


def test_protocol_v1_is_frozen_protocol():
    data = preset("protocol-v1")
    example = contract_example()
    passes = data["passes"]
    assert [p["question"] for p in passes] == [
        "protocol_v1/sdg_pass1",
        "protocol_v1/sdg_pass2",
        "protocol_v1/adt_pass1",
        "protocol_v1/adt_pass2",
    ]
    by_question = {p["question"]: p for p in passes}
    for question, model in [
        ("protocol_v1/sdg_pass1", "qwen3"),
        ("protocol_v1/sdg_pass2", "qwen3"),
        ("protocol_v1/adt_pass1", "gemma"),
        ("protocol_v1/adt_pass2", "gemma"),
    ]:
        [entry] = by_question[question]["models"]
        # What changes an answer, as frozen ([OA] docs/protocol-freeze-v1.md:19-21).
        keys = (
            "endpoint",
            "model",
            "seed",
            "temperature",
            "reasoning",
            "reasoning_style",
        )
        assert {k: data["models"][entry].get(k) for k in keys} == {
            k: example["models"][model][k] for k in keys
        }
        assert "extra_body" not in data["models"][entry]
    for question, source in [
        ("protocol_v1/sdg_pass2", "protocol_v1/sdg_pass1"),
        ("protocol_v1/adt_pass2", "protocol_v1/adt_pass1"),
    ]:
        units = by_question[question]["units"]
        assert units["rule"] == "threshold" and units["at_least"] == 0.25
        assert units["from"] == by_question[source]["id"]


def test_paper_v1_preset():
    data = preset("paper-v1")
    passes = {p["id"]: p for p in data["passes"]}
    assert list(passes) == ["paper_adt", "paper_sdg", "paper_impact"]
    assert passes["paper_adt"]["question"] == "paper/adt_v1"
    assert passes["paper_sdg"]["question"] == "paper/sdg_v1"
    assert passes["paper_impact"]["question"] == "paper/impact_v1"
    assert passes["paper_adt"]["units"] == {"rule": "all"}
    assert passes["paper_sdg"]["units"] == {"rule": "all"}
    impact = passes["paper_impact"]
    assert impact["budget_rule"] == "length"
    assert impact["units"]["rule"] == "cross"
    assert impact["units"].get("agreed_first", False) is False
    for side, source in (("a", "paper_adt"), ("b", "paper_sdg")):
        assert impact["units"][side]["from"] == source
        assert impact["units"][side]["combine"] == "union"
        assert sorted(impact["units"][side]["models"]) == ["coder", "gemma"]
    for p in passes.values():
        assert sorted(p["models"]) == ["coder", "gemma"]
        assert p["attempts"] == 4
    assert data["models"]["gemma"]["reasoning"] == "on"
    assert data["models"]["gemma"]["reasoning_style"] == "enable_thinking"
    assert data["models"]["coder"]["reasoning"] == "on"
    for entry in data["models"].values():
        assert entry["timeout_s"] == 1800.0
