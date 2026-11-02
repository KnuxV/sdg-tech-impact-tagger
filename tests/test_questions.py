"""Questions: prompt ids, rendering, and the refusals of contract section 3.

Rendered texts of the shipped questions are frozen from the earlier code
(tests/fixtures/render/, made by tests/fixtures/make/); prompt ids come from
questions/IDS.tsv, itself computed by the earlier code, plus the id D017
gives impact/p2_reasoning.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from conftest import (
    FIXTURES,
    QUESTIONS,
    SCORE_BLOCKS,
    block_file,
    read_json,
    score_question,
    sha12,
    write_question,
)

import sdg_tech_impact_tagger as tagger

ADT = {"a": "adt"}

SHIPPED = [
    "protocol_v1/sdg_pass1",
    "protocol_v1/sdg_pass2",
    "protocol_v1/adt_pass1",
    "protocol_v1/adt_pass2",
    "impact/p3_2",
    "impact/p2",
    "impact/p2_reasoning",
    "paper/adt_v1",
    "paper/sdg_v1",
    "paper/impact_v1",
]


def ids_from_tsv() -> dict[str, dict[str, str]]:
    """Expected `prompt_ids` per question: `{"": id}` when whole, `{code: id}` per label."""
    expected: dict[str, dict[str, str]] = {}
    with (QUESTIONS / "IDS.tsv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["part"].startswith("whole ("):
                continue  # a recorded id, not the question's own (contract 3.5)
            code = "" if row["part"] == "whole" else row["part"]
            expected.setdefault(row["question"], {})[code] = row["prompt_id"]
    # D017: the reasoning layer of divergence-validation, the P2 blocks under the prefix p3.
    expected["impact/p2_reasoning"] = {"": "p3-ed1dd92de43c"}
    return expected


def test_ids_tsv_covers_every_shipped_question():
    assert sorted(ids_from_tsv()) == sorted(SHIPPED)


@pytest.mark.parametrize("name", SHIPPED)
def test_shipped_prompt_ids(name):
    question = tagger.load_question(name)
    assert question.name == name
    assert dict(question.prompt_ids) == ids_from_tsv()[name]


@pytest.mark.parametrize("name", SHIPPED)
def test_shipped_question_loads_by_path(name):
    question = tagger.load_question(QUESTIONS / name)
    assert dict(question.prompt_ids) == ids_from_tsv()[name]


@pytest.mark.parametrize(
    ("name", "level", "readout"),
    [
        ("protocol_v1/sdg_pass1", "work", "score_json"),
        ("protocol_v1/sdg_pass2", "work x list", "letter_logprob"),
        ("protocol_v1/adt_pass1", "work", "score_json"),
        ("protocol_v1/adt_pass2", "work x list", "letter_logprob"),
        ("impact/p3_2", "work x list x list", "letter_text"),
        ("impact/p2", "work x list x list", "letter_logprob"),
        ("impact/p2_reasoning", "work x list x list", "letter_text"),
        ("paper/adt_v1", "work", "letter_text"),
        ("paper/sdg_v1", "work", "letter_text"),
        ("paper/impact_v1", "work x list x list", "json_object"),
    ],
)
def test_shipped_question_attributes(name, level, readout):
    question = tagger.load_question(name)
    assert question.level == level
    assert question.readout == readout
    assert list(question.text_fields) == ["title", "abstract"]


def test_shipped_question_files_are_listed_in_sha256sums():
    """Contract 3.1: one line per file under questions/<family>/<name>/, none for the root files."""
    import hashlib

    lines = (QUESTIONS / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    listed = {}
    for line in lines:
        digest, path = line.split("  ", 1)
        assert path not in listed, path
        listed[path] = digest
    on_disk = {
        p.relative_to(QUESTIONS).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in QUESTIONS.rglob("*")
        if p.is_file()
        and len(p.relative_to(QUESTIONS).parts) >= 3
        and "__pycache__" not in p.parts
    }
    assert listed == on_disk
    assert "SHA256SUMS" not in listed and "IDS.tsv" not in listed
    for name in SHIPPED:
        assert f"{name}/question.toml" in listed


# --------------------------------------------------------------------------
# rendering, against the earlier code
# --------------------------------------------------------------------------


def render_cases():
    for path in sorted((FIXTURES / "render").glob("*.json")):
        data = read_json(path)
        for n, case in enumerate(data["cases"]):
            yield pytest.param(data["question"], case, id=f"{path.stem}-{n}")


@pytest.mark.parametrize(("name", "case"), list(render_cases()))
def test_render_matches_earlier_code(name, case):
    question = tagger.load_question(name)
    units = [tuple(unit) for unit in case["units"]]
    calls = question.render(case["texts"], units, null_text=case["null_text"])
    assert [tuple(call) for call in calls] == [tuple(call) for call in case["calls"]]


def test_render_null_text_default_is_empty():
    question = tagger.load_question("protocol_v1/sdg_pass1")
    with_none = question.render({"title": "T", "abstract": None})
    with_empty = question.render({"title": "T", "abstract": ""})
    assert with_none == with_empty


# --------------------------------------------------------------------------
# render (10.1)
# --------------------------------------------------------------------------


def test_render_at_a_list_level_without_units_is_empty():
    question = tagger.load_question("protocol_v1/sdg_pass2")
    assert question.render({"title": "T", "abstract": "A"}) == []
    assert question.render({"title": "T", "abstract": "A"}, []) == []


def test_render_with_sides_gives_one_call_per_side_per_unit():
    question = tagger.load_question("impact/p3_2")
    units = [("AI", "SDG-07"), ("ROBOTICS", "SDG-13")]
    calls = question.render({"title": "T", "abstract": "A"}, units)
    assert len(calls) == 4
    one = [question.render({"title": "T", "abstract": "A"}, [u]) for u in units]
    assert calls == one[0] + one[1]


@pytest.mark.parametrize(
    ("name", "units"),
    [
        ("protocol_v1/sdg_pass1", [("SDG-01",)]),
        ("protocol_v1/sdg_pass2", [("SDG-01", "AI")]),
        ("protocol_v1/sdg_pass2", [()]),
        ("protocol_v1/sdg_pass2", [("SDG-18",)]),
        ("protocol_v1/sdg_pass2", [("AI",)]),
        ("impact/p3_2", [("AI",)]),
        ("impact/p3_2", [("SDG-07", "AI")]),
    ],
)
def test_render_refuses_a_bad_unit(name, units):
    question = tagger.load_question(name)
    with pytest.raises(tagger.UnitsError):
        question.render({"title": "T", "abstract": "A"}, units)


def test_render_refuses_a_missing_field():
    question = tagger.load_question("protocol_v1/sdg_pass1")
    with pytest.raises(tagger.TextsError):
        question.render({"title": "T"})


# --------------------------------------------------------------------------
# the [[OPEN marker (3.4)
# --------------------------------------------------------------------------


def open_question(directory, *, blocks, fill_user, id_blocks=None, extra=""):
    write_question(
        directory,
        blocks=blocks,
        fill_user=fill_user,
        fields=["title"],
        readout_table='schema_name = "s"',
        lists=ADT,
        id_blocks=id_blocks,
        extra=extra,
    )


@pytest.mark.parametrize(
    "case",
    ["system", "user", "block fill", "id block only"],
)
def test_open_marker_in_a_block_is_refused(tmp_path, case):
    marked = "Draft [[OPEN: wording]]"
    blocks = {"SYS": "Score.", "USR": "Text: {title}", "NOTE": "Plain."}
    fill = {"title": "text:title"}
    id_blocks = None
    if case == "system":
        blocks["SYS"] = marked
    elif case == "user":
        blocks["USR"] = "Text: {title} " + marked
    elif case == "block fill":
        blocks["USR"] = "Text: {title}\n{note}"
        blocks["NOTE"] = marked
        fill["note"] = "block:NOTE"
    else:
        blocks["NOTE"] = marked
        id_blocks = ["SYS", "USR", "NOTE"]
    open_question(tmp_path / "q", blocks=blocks, fill_user=fill, id_blocks=id_blocks)
    with pytest.raises(tagger.QuestionError):
        tagger.load_question(tmp_path / "q")


def test_open_marker_in_an_unread_block_is_not_refused(tmp_path):
    blocks = {"SYS": "Score.", "USR": "Text: {title}", "NOTE": "Draft [[OPEN]]"}
    open_question(tmp_path / "q", blocks=blocks, fill_user={"title": "text:title"})
    tagger.load_question(tmp_path / "q")


def test_open_marker_in_the_material_of_any_label_is_refused(tmp_path):
    # The marker sits in a label no unit asks about: refused all the same.
    material_question(
        tmp_path / "q",
        block_file({**GOOD_MATERIAL, "BLOCKCHAIN": "Ledgers\n\nThey record [[OPEN]]."}),
    )
    refused(tmp_path / "q")


def test_open_marker_in_a_work_is_rendered(tmp_path):
    score_question(tmp_path / "q", lists=ADT)
    question = tagger.load_question(tmp_path / "q")
    [(_, user)] = question.render({"title": "[[OPEN", "abstract": "x"})
    assert user == "Text: [[OPEN\nx"


# --------------------------------------------------------------------------
# block files and ids on a question of our own
# --------------------------------------------------------------------------


def test_block_body_is_verbatim_and_id_hashes_it(tmp_path):
    blocks = {"SYS": "\nYou score colours.\n", "USR": "Text: {title}\n{abstract}  "}
    expected = write_question(
        tmp_path / "q",
        blocks=blocks,
        fill_user={"title": "text:title", "abstract": "text:abstract"},
        readout_table='schema_name = "s"',
        lists=ADT,
    )
    question = tagger.load_question(tmp_path / "q")
    assert dict(question.prompt_ids) == {"": expected}
    assert expected == "tq-" + sha12(
        "\nYou score colours.\n\nText: {title}\n{abstract}  "
    )
    [(system, user)] = question.render({"title": "A", "abstract": "B"})
    assert system == "\nYou score colours.\n"
    assert user == "Text: A\nB  "


def test_block_reader_accepts_blank_lines_and_trailing_blanks(tmp_path):
    directory = tmp_path / "q"
    score_question(directory, lists=ADT)
    # Rewrite the file: blank lines between heading and fence, blanks after
    # the heading and the closing fence, a heading that is not a block name.
    text = (
        "## 1. Prose heading\n\nnot a block\n\n"
        "## SYS  \n\n\n```text\nYou score colours.\n```\t \n\n"
        "## USR\n```text\nText: {title}\n{abstract}\n```\n"
    )
    (directory / "q.md").write_text(text, encoding="utf-8")
    question = tagger.load_question(directory)
    assert dict(question.prompt_ids) == {
        "": "tq-" + sha12("You score colours.\nText: {title}\n{abstract}")
    }


def test_format_fill_does_not_rescan_values(tmp_path):
    score_question(tmp_path / "q", lists=ADT)
    question = tagger.load_question(tmp_path / "q")
    [(_, user)] = question.render({"title": "{abstract} {0} {", "abstract": "x}"})
    assert user == "Text: {abstract} {0} {\nx}"


def test_replace_fill_replaces_in_fill_order(tmp_path):
    write_question(
        tmp_path / "q",
        blocks=SCORE_BLOCKS,
        fill_user={"title": "text:title", "abstract": "text:abstract"},
        readout_table='schema_name = "s"',
        lists=ADT,
        question_extra='fill = "replace"',
    )
    question = tagger.load_question(tmp_path / "q")
    [(_, user)] = question.render({"title": "On {abstract}", "abstract": "ABS"})
    # Contract 3.4: each replacement runs on the result of the one before.
    assert user == "Text: On ABS\nABS"


def test_question_by_path_with_prompt_id_of_any_prefix(tmp_path):
    expected = write_question(
        tmp_path / "q",
        blocks=SCORE_BLOCKS,
        fill_user={"title": "text:title", "abstract": "text:abstract"},
        readout_table='schema_name = "s"',
        lists=ADT,
        prefix="abc.9",
    )
    assert expected.startswith("abc.9-")
    assert dict(tagger.load_question(tmp_path / "q").prompt_ids) == {"": expected}


# --------------------------------------------------------------------------
# refusals (QuestionError)
# --------------------------------------------------------------------------


def refused(directory: Path) -> None:
    with pytest.raises(tagger.QuestionError):
        tagger.load_question(directory)


def test_refuses_unknown_key_in_question(tmp_path):
    score_question(tmp_path / "q", lists=ADT, question_extra='colour = "red"')
    refused(tmp_path / "q")


def test_refuses_unknown_key_in_readout(tmp_path):
    write_question(
        tmp_path / "q",
        blocks=SCORE_BLOCKS,
        fill_user={"title": "text:title", "abstract": "text:abstract"},
        readout_table='schema_name = "s"\nletters_ = ["Y"]',
        lists=ADT,
    )
    refused(tmp_path / "q")


def test_refuses_unknown_key_in_budget(tmp_path):
    score_question(tmp_path / "q", lists=ADT, budget="max_tokens = 50\nmax_token = 3")
    refused(tmp_path / "q")


def test_refuses_missing_block_file(tmp_path):
    score_question(tmp_path / "q", lists=ADT)
    (tmp_path / "q" / "q.md").unlink()
    refused(tmp_path / "q")


def test_refuses_missing_block(tmp_path):
    score_question(tmp_path / "q", lists=ADT)
    (tmp_path / "q" / "q.md").write_text(
        block_file({"SYS": "You score colours."}), encoding="utf-8"
    )
    refused(tmp_path / "q")


def test_refuses_repeated_block_in_a_file(tmp_path):
    score_question(tmp_path / "q", lists=ADT)
    text = block_file(SCORE_BLOCKS) + "\n" + block_file({"SYS": "Another system."})
    (tmp_path / "q" / "q.md").write_text(text, encoding="utf-8")
    refused(tmp_path / "q")


def test_refuses_placeholder_without_fill(tmp_path):
    write_question(
        tmp_path / "q",
        blocks=SCORE_BLOCKS,
        fill_user={"title": "text:title"},
        readout_table='schema_name = "s"',
        lists=ADT,
    )
    refused(tmp_path / "q")


def test_refuses_fill_without_placeholder(tmp_path):
    write_question(
        tmp_path / "q",
        blocks=SCORE_BLOCKS,
        fill_user={
            "title": "text:title",
            "abstract": "text:abstract",
            "colour": "a:name",
        },
        readout_table='schema_name = "s"',
        lists=ADT,
    )
    refused(tmp_path / "q")


@pytest.mark.parametrize(
    "field", ["{title!r}", "{title:>10}", "{title[0]}", "{title.upper}"]
)
def test_refuses_placeholder_with_conversion_spec_index_or_attribute(tmp_path, field):
    blocks = {"SYS": "You score colours.", "USR": "Text: " + field + "\n{abstract}"}
    write_question(
        tmp_path / "q",
        blocks=blocks,
        fill_user={"title": "text:title", "abstract": "text:abstract"},
        readout_table='schema_name = "s"',
        lists=ADT,
    )
    refused(tmp_path / "q")


def test_refuses_replace_placeholder_absent_from_template(tmp_path):
    write_question(
        tmp_path / "q",
        blocks={"SYS": "You score colours.", "USR": "Text: {title}"},
        fill_user={"title": "text:title", "abstract": "text:abstract"},
        readout_table='schema_name = "s"',
        lists=ADT,
        question_extra='fill = "replace"',
    )
    refused(tmp_path / "q")


def test_refuses_computed_id_not_the_expected_one(tmp_path):
    score_question(tmp_path / "q", lists=ADT, prompt_id="tq-000000000000")
    with pytest.raises(tagger.QuestionError) as info:
        tagger.load_question(tmp_path / "q")
    computed = "tq-" + sha12("\n".join(SCORE_BLOCKS.values()))
    # Contract 3.5: the error names both ids.
    assert computed in str(info.value) and "tq-000000000000" in str(info.value)


def test_refuses_shipped_name_with_moved_block(tmp_path):
    """A copy of a shipped question with one byte changed is refused on its id."""
    import shutil

    target = tmp_path / "impact" / "p2"
    shutil.copytree(QUESTIONS / "impact" / "p2", target)
    text = (
        (target / "p2.md").read_text(encoding="utf-8").replace("Y or N:", "Y or N :", 1)
    )
    (target / "p2.md").write_text(text, encoding="utf-8")
    refused(target)


def material_question(directory: Path, material_file: str) -> None:
    """A work x list question whose user block takes a per-label block of `m.md`."""
    write_question(
        directory,
        level="work x list",
        readout="letter_logprob",
        blocks={"SYS": "Answer.", "USR": "{title}\n{definition}"},
        fill_user={"title": "text:title", "definition": "material:definition"},
        fields=["title"],
        readout_table='letters = ["Y", "N"]',
        budget="max_tokens = 1",
        lists=ADT,
        extra='[material.definition]\nlist = "a"\nfile = "m.md"\nblock = "{id}"\npart = "body"\n',
    )
    (directory / "m.md").write_text(material_file, encoding="utf-8")


GOOD_MATERIAL = {
    "AI": "Machines\n\nThey learn.",
    "IOT": "Things\n\nThey connect.",
    "COMPUTING_INFRASTRUCTURE": "Computers\n\nThey compute.",
    "BLOCKCHAIN": "Ledgers\n\nThey record.",
    "ROBOTICS": "Robots\n\nThey move.",
    "ADDITIVE_MANUFACTURING": "Printers\n\nThey print.",
}


def test_material_body_part_is_read(tmp_path):
    material_question(tmp_path / "q", block_file(GOOD_MATERIAL))
    question = tagger.load_question(tmp_path / "q")
    calls = question.render({"title": "T"}, [("ROBOTICS",), ("AI",)])
    assert [c[1] for c in calls] == ["T\nThey move.", "T\nThey learn."]


def test_refuses_material_block_not_in_the_list(tmp_path):
    material_question(
        tmp_path / "q", block_file({**GOOD_MATERIAL, "BIG_DATA": "Data\n\nA lot."})
    )
    refused(tmp_path / "q")


def test_refuses_material_block_missing(tmp_path):
    material_question(
        tmp_path / "q",
        block_file({k: v for k, v in GOOD_MATERIAL.items() if k != "IOT"}),
    )
    refused(tmp_path / "q")


def test_refuses_material_body_without_blank_line(tmp_path):
    material_question(
        tmp_path / "q", block_file({**GOOD_MATERIAL, "IOT": "Things\nThey connect."})
    )
    refused(tmp_path / "q")


def test_refuses_material_empty_name_line(tmp_path):
    material_question(
        tmp_path / "q", block_file({**GOOD_MATERIAL, "IOT": " \n\nThey connect."})
    )
    refused(tmp_path / "q")


def test_refuses_material_empty_body(tmp_path):
    material_question(
        tmp_path / "q", block_file({**GOOD_MATERIAL, "IOT": "Things\n\n  "})
    )
    refused(tmp_path / "q")
