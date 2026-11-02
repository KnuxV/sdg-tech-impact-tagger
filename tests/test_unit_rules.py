"""Unit rules (contract section 5): which units a pass asks about, in which order.

Selections and orders carried over are frozen from the earlier code:
tests/fixtures/units/threshold.json from [OA] `adt_candidates`, and
units/cross.json from [WS] `impact_units` and `_pairs_units`. The unit order
is observed as the order of the calls (plan order, one call at a time), the
units themselves as the rows of the table.
"""

from __future__ import annotations

import polars as pl
import pytest
from conftest import (
    FIXTURES,
    TEXTS,
    Endpoint,
    chat,
    model_entry,
    read_json,
    write_question,
    write_texts,
    write_workflow,
    write_works,
)

import sdg_tech_impact_tagger as tagger

THRESHOLD = read_json(FIXTURES / "units" / "threshold.json")
CROSS = read_json(FIXTURES / "units" / "cross.json")
TITLE_TO_ID = {
    "Kestrel study: solar microgrids that power rural clinics": "w-003",
    "Juniper ledger: a {abstract} record of {0} fishing quotas": "w-001",
    "Basalt hands: printed prosthetics for children": "w-010",
    "Quokka seminar notes": "w-002",
}


def probe_question(directory, level: str, lists: dict[str, str]) -> None:
    """A cheap letter_text question whose user text names its unit: `title|a|b`."""
    template = {
        "work": "{title}",
        "work x list": "{title}|{a}",
        "work x list x list": "{title}|{a}|{b}",
    }[level]
    fill = {"title": "text:title"}
    if "a" in lists:
        fill["a"] = "a:id"
    if "b" in lists:
        fill["b"] = "b:id"
    write_question(
        directory,
        name="test/probe",
        level=level,
        readout="letter_text",
        blocks={"SYS": "Answer Y or N.", "USR": template},
        fill_user=fill,
        lists=lists,
        fields=["title"],
        readout_table='letters = ["Y", "N"]',
        budget="max_tokens = 5",
    )


def asked(endpoint: Endpoint) -> list[tuple[str, ...]]:
    units = []
    for user in endpoint.users():
        title, *codes = user.split("|")
        units.append((TITLE_TO_ID.get(title, title), *codes))
    return units


def yes(payload, n):
    return chat("Y")


def place(tmp_path, pass_id: str, model: str, frame: pl.DataFrame) -> None:
    """An earlier pass's output, where a later pass reads it (contract 5)."""
    path = tmp_path / "runs" / "wf" / pass_id / f"{model}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)


MODELS = model_entry("m1", model="m1") + model_entry("m2", model="m2")


# --------------------------------------------------------------------------
# all
# --------------------------------------------------------------------------


def test_all_at_work_x_list_is_works_in_table_order_then_list_order(tmp_path, key_env):
    write_texts(tmp_path)
    probe_question(tmp_path / "probe", "work x list", {"a": "colour"})
    body = (
        MODELS
        + '[[passes]]\nid = "pick"\nquestion_dir = "probe"\nmodels = ["m1"]\nunits = { rule = "all" }\n'
    )
    endpoint = Endpoint(yes)
    [result] = tagger.run(
        tagger.load_workflow(write_workflow(tmp_path, body)),
        transport=endpoint.transport,
    )
    titles = dict(zip(TEXTS["title"], TEXTS["id"], strict=True))
    order = [(titles[t], c) for t, c in asked(endpoint)]
    assert order == [
        (w, c) for w in ["b2", "a1", "c3"] for c in ["RED", "GREEN", "BLUE"]
    ]
    table = pl.read_parquet(result.output)
    assert table.select("id", "code").rows() == sorted(order)


def test_all_at_work_x_list_x_list(tmp_path, key_env):
    write_texts(tmp_path, TEXTS.head(2))
    probe_question(
        tmp_path / "probe", "work x list x list", {"a": "colour", "b": "shade"}
    )
    body = (
        MODELS
        + '[[passes]]\nid = "pick"\nquestion_dir = "probe"\nmodels = ["m1"]\nunits = { rule = "all" }\n'
    )
    endpoint = Endpoint(yes)
    [result] = tagger.run(
        tagger.load_workflow(write_workflow(tmp_path, body)),
        transport=endpoint.transport,
    )
    titles = dict(zip(TEXTS["title"], TEXTS["id"], strict=True))
    order = [(titles[t], a, b) for t, a, b in asked(endpoint)]
    assert order == [
        (w, a, b)
        for w in ["b2", "a1"]
        for a in ["RED", "GREEN", "BLUE"]
        for b in ["DARK", "PALE"]
    ]
    table = pl.read_parquet(result.output)
    assert table.columns[:4] == ["id", "code", "colour", "shade"]
    assert table.select("id", "code", "colour", "shade").rows() == sorted(
        (w, f"{a}|{b}", a, b) for w, a, b in order
    )


# --------------------------------------------------------------------------
# threshold, against [OA]
# --------------------------------------------------------------------------


def threshold_source(rows=None) -> pl.DataFrame:
    rows = THRESHOLD["source"] if rows is None else rows
    return pl.DataFrame(
        rows,
        schema={
            "id": pl.String,
            "code": pl.String,
            "score": pl.Float64,
            "parse_failure": pl.Boolean,
        },
        orient="row",
    )


def threshold_project(
    tmp_path,
    *,
    at_least="0.25",
    rule_extra: str = "",
    pass_models='["m1"]',
    source_models='["m1"]',
):
    write_works(tmp_path, "protocol_impact")
    probe_question(tmp_path / "probe", "work x list", {"a": "adt"})
    body = MODELS + (
        f'[[passes]]\nid = "scores"\nquestion = "protocol_v1/adt_pass1"\nmodels = {source_models}\n'
        'units = { rule = "all" }\n\n'
        f'[[passes]]\nid = "pick"\nquestion_dir = "probe"\nmodels = {pass_models}\n'
        f'units = {{ rule = "threshold", from = "scores", model = "same", at_least = {at_least}{rule_extra} }}\n'
    )
    return write_workflow(tmp_path, body)


@pytest.mark.parametrize(
    "case", THRESHOLD["cases"], ids=lambda c: f"at_least={c['at_least']}"
)
def test_threshold_units_and_order_are_the_earlier_ones(tmp_path, key_env, case):
    path = threshold_project(tmp_path, at_least=repr(case["at_least"]))
    place(tmp_path, "scores", "m1", threshold_source())
    endpoint = Endpoint(yes)
    [result] = tagger.run(
        tagger.load_workflow(path), passes=["pick"], transport=endpoint.transport
    )
    assert asked(endpoint) == [(w, c) for w, c, _ in case["units"]]
    table = pl.read_parquet(result.output)
    assert table.columns[:4] == ["id", "code", "source_score", "repeat"]
    assert table.schema["source_score"] == pl.Float64
    assert table.select("id", "code", "source_score").rows() == sorted(
        tuple(u) for u in case["units"]
    )


def test_threshold_reads_another_models_source(tmp_path, key_env):
    path = threshold_project(
        tmp_path, pass_models='["m1"]', source_models='["m1", "m2"]'
    )
    text = path.read_text(encoding="utf-8").replace('model = "same"', 'model = "m2"')
    path.write_text(text, encoding="utf-8")
    place(tmp_path, "scores", "m2", threshold_source())
    place(
        tmp_path,
        "scores",
        "m1",
        threshold_source().with_columns(pl.lit(0.0).alias("score")),
    )
    endpoint = Endpoint(yes)
    tagger.run(
        tagger.load_workflow(path), passes=["pick"], transport=endpoint.transport
    )
    assert asked(endpoint) == [(w, c) for w, c, _ in THRESHOLD["cases"][0]["units"]]


def test_threshold_model_same_must_be_a_source_model(tmp_path):
    path = threshold_project(tmp_path, pass_models='["m2"]', source_models='["m1"]')
    with pytest.raises(tagger.WorkflowError):
        tagger.load_workflow(path)


@pytest.mark.parametrize("value", ["1.5", "-0.1", "true", '"0.3"', "nan", "inf"])
def test_threshold_at_least_must_be_a_number_in_0_1(tmp_path, value):
    path = threshold_project(tmp_path, at_least=value)
    with pytest.raises(tagger.WorkflowError):
        tagger.load_workflow(path)


def bad_sources():
    base = THRESHOLD["source"]
    w3 = [r for r in base if r[0] == "w-003"]
    return {
        "missing score column": threshold_source().drop("score"),
        "score not Float64": threshold_source().with_columns(
            pl.col("score").cast(pl.Float32)
        ),
        "code not String": threshold_source().with_columns(
            pl.col("code").cast(pl.Categorical)
        ),
        "parse_failure not Boolean": threshold_source().with_columns(
            pl.col("parse_failure").cast(pl.Int64)
        ),
        "null id": threshold_source([[None, *base[0][1:]], *base[1:]]),
        "code not in the list": threshold_source(
            [[base[0][0], "BIG_DATA", 0.5, False], *base[1:]]
        ),
        "null score": threshold_source([[*base[0][:2], None, False], *base[1:]]),
        "NaN score": threshold_source([[*base[0][:2], float("nan"), False], *base[1:]]),
        "score above 1": threshold_source([[*base[0][:2], 1.01, False], *base[1:]]),
        "repeated pair": threshold_source([*base, base[0]]),
        "work without every label": threshold_source(base[1:]),
        "work not in the texts": threshold_source(
            [*base, *[["w-999", r[1], r[2], r[3]] for r in w3]]
        ),
        "work of the texts unscored": threshold_source(
            [r for r in base if r[0] != "w-002"]
        ),
    }


@pytest.mark.parametrize("case", sorted(bad_sources()))
def test_threshold_refuses_a_bad_source(tmp_path, key_env, case):
    path = threshold_project(tmp_path)
    place(tmp_path, "scores", "m1", bad_sources()[case])
    with pytest.raises(tagger.UnitsError):
        tagger.run(
            tagger.load_workflow(path),
            passes=["pick"],
            transport=Endpoint(yes).transport,
        )
    assert not (tmp_path / "runs" / "wf" / "pick").exists()


def test_threshold_allow_unscored(tmp_path, key_env):
    path = threshold_project(tmp_path, rule_extra=", allow_unscored = true")
    place(
        tmp_path,
        "scores",
        "m1",
        threshold_source([r for r in THRESHOLD["source"] if r[0] != "w-002"]),
    )
    endpoint = Endpoint(yes)
    tagger.run(
        tagger.load_workflow(path), passes=["pick"], transport=endpoint.transport
    )
    assert asked(endpoint) == [
        (w, c) for w, c, _ in THRESHOLD["cases"][0]["units"] if w != "w-002"
    ]


def test_threshold_empty_unit_set_is_refused(tmp_path, key_env):
    path = threshold_project(tmp_path, at_least="0.95")
    place(
        tmp_path,
        "scores",
        "m1",
        threshold_source().with_columns(pl.col("score").clip(0.0, 0.9)),
    )
    with pytest.raises(tagger.UnitsError):
        tagger.run(
            tagger.load_workflow(path),
            passes=["pick"],
            transport=Endpoint(yes).transport,
        )


def test_threshold_from_a_pass_of_another_list_is_refused(tmp_path):
    path = threshold_project(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        "protocol_v1/adt_pass1", "protocol_v1/sdg_pass1"
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(tagger.WorkflowError):
        tagger.load_workflow(path)


def test_threshold_from_a_later_pass_is_refused(tmp_path):
    write_works(tmp_path, "protocol_impact")
    probe_question(tmp_path / "probe", "work x list", {"a": "adt"})
    body = MODELS + (
        '[[passes]]\nid = "pick"\nquestion_dir = "probe"\nmodels = ["m1"]\n'
        'units = { rule = "threshold", from = "scores", model = "same", at_least = 0.25 }\n\n'
        '[[passes]]\nid = "scores"\nquestion = "protocol_v1/adt_pass1"\nmodels = ["m1"]\nunits = { rule = "all" }\n'
    )
    with pytest.raises(tagger.WorkflowError):
        tagger.load_workflow(write_workflow(tmp_path, body))


def test_threshold_from_a_letter_pass_is_refused(tmp_path):
    write_works(tmp_path, "protocol_impact")
    probe_question(tmp_path / "probe", "work x list", {"a": "adt"})
    body = MODELS + (
        '[[passes]]\nid = "scores"\nquestion = "protocol_v1/adt_pass1"\nmodels = ["m1"]\nunits = { rule = "all" }\n\n'
        '[[passes]]\nid = "letters"\nquestion = "protocol_v1/adt_pass2"\nmodels = ["m1"]\n'
        'units = { rule = "threshold", from = "scores", model = "same", at_least = 0.25 }\n\n'
        '[[passes]]\nid = "pick"\nquestion_dir = "probe"\nmodels = ["m1"]\n'
        'units = { rule = "threshold", from = "letters", model = "same", at_least = 0.25 }\n'
    )
    with pytest.raises(tagger.WorkflowError):
        tagger.load_workflow(write_workflow(tmp_path, body))


# --------------------------------------------------------------------------
# cross, against [WS]
# --------------------------------------------------------------------------


def label_source(rows) -> pl.DataFrame:
    return pl.DataFrame(
        [[w, c, 1, label] for w, c, label in rows],
        schema={
            "id": pl.String,
            "code": pl.String,
            "repeat": pl.Int64,
            "label": pl.String,
        },
        orient="row",
    )


SOURCE_PASSES = (
    '[[passes]]\nid = "adt1"\nquestion = "protocol_v1/adt_pass1"\nmodels = ["m1", "m2"]\nunits = { rule = "all" }\n\n'
    '[[passes]]\nid = "adt2"\nquestion = "protocol_v1/adt_pass2"\nmodels = ["m1", "m2"]\n'
    'units = { rule = "threshold", from = "adt1", model = "same", at_least = 0.25 }\n__ADT2__\n\n'
    '[[passes]]\nid = "sdg1"\nquestion = "protocol_v1/sdg_pass1"\nmodels = ["m1"]\nunits = { rule = "all" }\n\n'
    '[[passes]]\nid = "sdg2"\nquestion = "protocol_v1/sdg_pass2"\nmodels = ["m1"]\n'
    'units = { rule = "threshold", from = "sdg1", model = "same", at_least = 0.25 }\n\n'
)


def side(source: str, models: str, positive: list[str], combine: str | None) -> str:
    text = f'from = "{source}", models = {models}, positive = {positive!r}'.replace(
        "'", '"'
    )
    if combine:
        text += f', combine = "{combine}"'
    return "{ " + text + " }"


def cross_project(
    tmp_path,
    *,
    adt_positive=("E", "A", "T", "M"),
    sdg_positive=("Y",),
    combine="union",
    agreed_first=True,
    adt_models='["m1", "m2"]',
    adt2_extra="",
):
    write_works(tmp_path, "protocol_impact")
    probe_question(tmp_path / "probe", "work x list x list", {"a": "adt", "b": "sdg"})
    rule = (
        f'{{ rule = "cross", agreed_first = {str(agreed_first).lower()}, '
        f"a = {side('adt2', adt_models, list(adt_positive), combine)}, "
        f"b = {side('sdg2', '["m1"]', list(sdg_positive), None)} }}"
    )
    body = (
        MODELS
        + SOURCE_PASSES.replace("__ADT2__", adt2_extra)
        + (
            f'[[passes]]\nid = "pair"\nquestion_dir = "probe"\nmodels = ["m1"]\nunits = {rule}\n'
        )
    )
    path = write_workflow(tmp_path, body)
    for model, rows in CROSS["adt"].items():
        place(tmp_path, "adt2", model, label_source(rows))
    for model, rows in CROSS["sdg"].items():
        place(tmp_path, "sdg2", model, label_source(rows))
    return path


@pytest.mark.parametrize("case", CROSS["cases"], ids=lambda c: c["name"])
def test_cross_units_flags_and_agreed_first_order(tmp_path, key_env, case):
    path = cross_project(
        tmp_path, adt_positive=case["adt_positive"], sdg_positive=case["sdg_positive"]
    )
    endpoint = Endpoint(yes)
    [result] = tagger.run(
        tagger.load_workflow(path), passes=["pair"], transport=endpoint.transport
    )
    expected = case["agreed_first"]
    assert asked(endpoint) == [(u[0], u[2], u[3]) for u in expected]
    table = pl.read_parquet(result.output)
    flags = case["flags"]
    assert flags == ["adt_m1", "adt_m2", "sdg_m1"]
    assert table.columns[:8] == ["id", "code", "adt", "sdg", *flags, "repeat"]
    assert all(table.schema[f] == pl.Boolean for f in flags)
    assert table.select("id", "code", "adt", "sdg", *flags).rows() == sorted(
        tuple(u) for u in expected
    )


def test_cross_without_agreed_first_is_sorted(tmp_path, key_env):
    path = cross_project(tmp_path, agreed_first=False)
    endpoint = Endpoint(yes)
    tagger.run(
        tagger.load_workflow(path), passes=["pair"], transport=endpoint.transport
    )
    expected = sorted(tuple(u) for u in CROSS["cases"][0]["agreed_first"])
    assert asked(endpoint) == [(u[0], u[2], u[3]) for u in expected]


def test_cross_agreed_first_defaults_to_false(tmp_path, key_env):
    path = cross_project(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8").replace("agreed_first = true, ", ""),
        encoding="utf-8",
    )
    endpoint = Endpoint(yes)
    tagger.run(
        tagger.load_workflow(path), passes=["pair"], transport=endpoint.transport
    )
    expected = sorted(tuple(u) for u in CROSS["cases"][0]["agreed_first"])
    assert asked(endpoint) == [(u[0], u[2], u[3]) for u in expected]


def test_cross_intersection(tmp_path, key_env):
    path = cross_project(tmp_path, combine="intersection")
    endpoint = Endpoint(yes)
    [result] = tagger.run(
        tagger.load_workflow(path), passes=["pair"], transport=endpoint.transport
    )
    table = pl.read_parquet(result.output)
    # Under intersection a unit stands only where every source agrees: the union's all-true units.
    expected = sorted(
        (u[0], u[1], *u[4:]) for u in CROSS["cases"][0]["agreed_first"] if all(u[4:])
    )
    assert expected
    assert table.select("id", "code", "adt_m1", "adt_m2", "sdg_m1").rows() == expected


def test_cross_models_all(tmp_path, key_env):
    path = cross_project(tmp_path, adt_models='"all"')
    endpoint = Endpoint(yes)
    [result] = tagger.run(
        tagger.load_workflow(path), passes=["pair"], transport=endpoint.transport
    )
    expected = CROSS["cases"][0]["agreed_first"]
    assert pl.read_parquet(result.output).select("id", "code").rows() == sorted(
        (u[0], u[1]) for u in expected
    )


def test_cross_needs_combine_with_several_models(tmp_path):
    path = cross_project(tmp_path, combine=None)
    with pytest.raises(tagger.WorkflowError):
        tagger.load_workflow(path)


def test_cross_positive_must_be_letters_of_the_source(tmp_path):
    path = cross_project(tmp_path, adt_positive=("E", "Q"))
    with pytest.raises(tagger.WorkflowError):
        tagger.load_workflow(path)


def test_cross_side_from_a_pass_of_another_list(tmp_path):
    path = cross_project(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'a = { from = "adt2"', 'a = { from = "sdg2"'
        ),
        encoding="utf-8",
    )
    with pytest.raises(tagger.WorkflowError):
        tagger.load_workflow(path)


def test_cross_source_without_label(tmp_path, key_env):
    path = cross_project(tmp_path)
    place(tmp_path, "adt2", "m2", label_source(CROSS["adt"]["m2"]).drop("label"))
    with pytest.raises(tagger.UnitsError):
        tagger.run(
            tagger.load_workflow(path),
            passes=["pair"],
            transport=Endpoint(yes).transport,
        )


def test_cross_unit_of_a_work_not_in_the_texts(tmp_path, key_env):
    path = cross_project(tmp_path)
    place(
        tmp_path,
        "adt2",
        "m1",
        label_source([*CROSS["adt"]["m1"], ["w-999", "AI", "T"]]),
    )
    place(
        tmp_path,
        "sdg2",
        "m1",
        label_source([*CROSS["sdg"]["m1"], ["w-999", "SDG-01", "Y"]]),
    )
    with pytest.raises(tagger.UnitsError):
        tagger.run(
            tagger.load_workflow(path),
            passes=["pair"],
            transport=Endpoint(yes).transport,
        )


def test_cross_source_with_repeats_is_refused(tmp_path, key_env):
    path = cross_project(tmp_path, adt2_extra="repeats = 2")
    with pytest.raises((tagger.WorkflowError, tagger.UnitsError)):
        tagger.run(
            tagger.load_workflow(path),
            passes=["pair"],
            transport=Endpoint(yes).transport,
        )


def test_cross_empty_unit_set_is_refused(tmp_path, key_env):
    path = cross_project(tmp_path, sdg_positive=("N",))
    place(
        tmp_path,
        "sdg2",
        "m1",
        label_source([[w, c, "Y"] for w, c, _ in CROSS["sdg"]["m1"]]),
    )
    with pytest.raises(tagger.UnitsError):
        tagger.run(
            tagger.load_workflow(path),
            passes=["pair"],
            transport=Endpoint(yes).transport,
        )


# --------------------------------------------------------------------------
# file, against [WS]
# --------------------------------------------------------------------------


def file_project(
    tmp_path,
    *,
    flags: bool,
    csv_text: str | None = None,
    level: str = "work x list x list",
    lists=None,
    path_name: str = "units.csv",
):
    write_works(tmp_path, "protocol_impact")
    lists = {"a": "adt", "b": "sdg"} if lists is None else lists
    probe_question(tmp_path / "probe", level, lists)
    if csv_text is None:
        rows = CROSS["file"]["rows"]
        csv_text = "id,adt,sdg,note\n" + "".join(f"{w},{a},{s},x\n" for w, a, s in rows)
    (tmp_path / path_name).write_text(csv_text, encoding="utf-8")
    flag_text = ""
    if flags:
        flag_text = (
            f", flags = {{ a = {side('adt2', '["m1", "m2"]', ['E', 'A', 'T', 'M'], 'union')}, "
            f"b = {side('sdg2', '["m1"]', ['Y'], None)} }}"
        )
    body = (
        MODELS
        + SOURCE_PASSES.replace("__ADT2__", "")
        + (
            f'[[passes]]\nid = "pair"\nquestion_dir = "probe"\nmodels = ["m1"]\n'
            f'units = {{ rule = "file", path = "{path_name}"{flag_text} }}\n'
        )
    )
    path = write_workflow(tmp_path, body)
    for model, rows in CROSS["adt"].items():
        place(tmp_path, "adt2", model, label_source(rows))
    for model, rows in CROSS["sdg"].items():
        place(tmp_path, "sdg2", model, label_source(rows))
    return path


def test_file_units_with_flags_are_the_earlier_ones(tmp_path, key_env):
    path = file_project(tmp_path, flags=True)
    endpoint = Endpoint(yes)
    [result] = tagger.run(
        tagger.load_workflow(path), passes=["pair"], transport=endpoint.transport
    )
    expected = CROSS["file"]["units"]
    assert asked(endpoint) == [(u[0], u[2], u[3]) for u in expected]
    table = pl.read_parquet(result.output)
    assert table.columns[:8] == [
        "id",
        "code",
        "adt",
        "sdg",
        "adt_m1",
        "adt_m2",
        "sdg_m1",
        "repeat",
    ]
    assert table.select(
        "id", "code", "adt", "sdg", "adt_m1", "adt_m2", "sdg_m1"
    ).rows() == [tuple(u) for u in expected]


def test_file_units_without_flags(tmp_path, key_env):
    path = file_project(tmp_path, flags=False)
    [result] = tagger.run(
        tagger.load_workflow(path), passes=["pair"], transport=Endpoint(yes).transport
    )
    table = pl.read_parquet(result.output)
    assert table.columns[:5] == ["id", "code", "adt", "sdg", "repeat"]
    assert table.select("id", "code").rows() == [
        (u[0], u[1]) for u in CROSS["file"]["units"]
    ]


def test_file_units_from_parquet(tmp_path, key_env):
    path = file_project(tmp_path, flags=False, csv_text="", path_name="units.parquet")
    rows = CROSS["file"]["rows"]
    pl.DataFrame(rows, schema=["id", "adt", "sdg"], orient="row").write_parquet(
        tmp_path / "units.parquet"
    )
    [result] = tagger.run(
        tagger.load_workflow(path), passes=["pair"], transport=Endpoint(yes).transport
    )
    assert pl.read_parquet(result.output).select("id", "code").rows() == [
        (u[0], u[1]) for u in CROSS["file"]["units"]
    ]


def test_file_units_at_work_x_list(tmp_path, key_env):
    path = file_project(
        tmp_path,
        flags=False,
        level="work x list",
        lists={"a": "adt"},
        csv_text="code,id\nROBOTICS,w-001\nAI,w-001\nAI,w-003\n",
    )
    endpoint = Endpoint(yes)
    [result] = tagger.run(
        tagger.load_workflow(path), passes=["pair"], transport=endpoint.transport
    )
    assert asked(endpoint) == [("w-001", "AI"), ("w-001", "ROBOTICS"), ("w-003", "AI")]
    assert pl.read_parquet(result.output).select("id", "code").rows() == [
        ("w-001", "AI"),
        ("w-001", "ROBOTICS"),
        ("w-003", "AI"),
    ]


def test_file_units_at_work(tmp_path, key_env):
    path = file_project(
        tmp_path, flags=False, level="work", lists={}, csv_text="id\nw-010\nw-001\n"
    )
    endpoint = Endpoint(yes)
    [result] = tagger.run(
        tagger.load_workflow(path), passes=["pair"], transport=endpoint.transport
    )
    assert asked(endpoint) == [("w-001",), ("w-010",)]
    assert pl.read_parquet(result.output)["id"].to_list() == ["w-001", "w-010"]


@pytest.mark.parametrize(
    ("case", "csv_text"),
    [
        ("missing column", "id,adt\nw-003,AI\n"),
        ("repeated unit", "id,adt,sdg\nw-003,AI,SDG-07\nw-003,AI,SDG-07\n"),
        ("code not in its list", "id,adt,sdg\nw-003,BIG_DATA,SDG-07\n"),
        ("work not in the texts", "id,adt,sdg\nw-999,AI,SDG-07\n"),
        ("no unit", "id,adt,sdg\n"),
    ],
)
def test_file_refusals(tmp_path, key_env, case, csv_text):
    path = file_project(tmp_path, flags=False, csv_text=csv_text)
    with pytest.raises(tagger.UnitsError):
        tagger.run(
            tagger.load_workflow(path),
            passes=["pair"],
            transport=Endpoint(yes).transport,
        )
