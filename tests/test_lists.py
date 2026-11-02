"""Lists (contract 2.2): the shipped sdg and adt lists, and the refusals of a list file.

The names the earlier runs gave the labels are frozen in tests/fixtures/lists.json
from [OA] (`sdg_pass1.SDG_TITLES`, `sdg_pass2.goal_name`, the name lines of
`adt_descriptions_v3.md`) and [WS] `params.yaml` (`name_impact`).
"""

from __future__ import annotations

import pytest
from conftest import (
    FIXTURES,
    PACKAGE,
    model_entry,
    read_json,
    write_texts,
    write_workflow,
)

import sdg_tech_impact_tagger as tagger

EXPECTED = read_json(FIXTURES / "lists.json")


@pytest.mark.parametrize("list_id", ["sdg", "adt"])
def test_shipped_list_labels_in_order(list_id):
    loaded = tagger.load_list(list_id)
    assert loaded.id == list_id
    labels = [dict(label) for label in loaded.labels]
    assert [label["id"] for label in labels] == [e["id"] for e in EXPECTED[list_id]]
    for label, expected in zip(labels, EXPECTED[list_id], strict=True):
        for key, value in expected.items():
            assert label[key] == value, (label["id"], key)


@pytest.mark.parametrize("list_id", ["sdg", "adt"])
def test_shipped_list_values_are_strings_with_one_key_set(list_id):
    labels = [dict(label) for label in tagger.load_list(list_id).labels]
    keys = {frozenset(label) for label in labels}
    assert len(keys) == 1
    assert all(isinstance(v, str) for label in labels for v in label.values())
    # The slug is derived, never stored (contract 2.2).
    assert "slug" not in next(iter(keys))


def test_shipped_lists_are_checked_by_sha256sums():
    sums = (PACKAGE / "lists" / "SHA256SUMS").read_text(encoding="utf-8")
    assert "sdg.toml" in sums and "adt.toml" in sums


def test_load_list_by_path(tmp_path):
    path = tmp_path / "l.toml"
    path.write_text(
        '[list]\nid = "harm"\nname = "Harms"\nsource = "invented"\n\n'
        '[[labels]]\nid = "H1"\nname = "Bias"\ndefinition = "Unfair treatment."\n\n'
        '[[labels]]\nid = "H-2"\njson_key = "H2"\nname = "Surveillance"\ndefinition = "Watching people."\n',
        encoding="utf-8",
    )
    loaded = tagger.load_list(path)
    assert loaded.id == "harm"
    assert loaded.name == "Harms"
    labels = [dict(label) for label in loaded.labels]
    assert [(l["id"], l["json_key"], l["name"], l["definition"]) for l in labels] == [
        ("H1", "H1", "Bias", "Unfair treatment."),
        ("H-2", "H2", "Surveillance", "Watching people."),
    ]


BAD_LISTS = {
    "unknown list key": '[list]\nid = "x"\nname = "X"\nowner = "me"\n\n[[labels]]\nid = "A"\nname = "a"\n',
    "missing id": '[list]\nid = "x"\nname = "X"\n\n[[labels]]\nname = "a"\n',
    "repeated id": '[list]\nid = "x"\nname = "X"\n\n[[labels]]\nid = "A"\nname = "a"\n\n[[labels]]\nid = "A"\nname = "b"\n',
    "repeated json_key": (
        '[list]\nid = "x"\nname = "X"\n\n[[labels]]\nid = "A"\njson_key = "K"\nname = "a"\n\n'
        '[[labels]]\nid = "B"\njson_key = "K"\nname = "b"\n'
    ),
    "non-string value": '[list]\nid = "x"\nname = "X"\n\n[[labels]]\nid = "A"\nname = "a"\nrank = 3\n',
    "different key sets": (
        '[list]\nid = "x"\nname = "X"\n\n[[labels]]\nid = "A"\nname = "a"\ndefinition = "d"\n\n'
        '[[labels]]\nid = "B"\nname = "b"\n'
    ),
    "missing name": '[list]\nid = "x"\nname = "X"\n\n[[labels]]\nid = "A"\n',
}


@pytest.mark.parametrize("case", sorted(BAD_LISTS))
def test_refuses_bad_list(tmp_path, case):
    path = tmp_path / "l.toml"
    path.write_text(BAD_LISTS[case], encoding="utf-8")
    with pytest.raises(tagger.ListError):
        tagger.load_list(path)


def test_refuses_list_id_clashing_with_shipped(tmp_path):
    write_texts(tmp_path)
    (tmp_path / "lists").mkdir()
    (tmp_path / "lists" / "mine.toml").write_text(
        '[list]\nid = "sdg"\nname = "Mine"\n\n[[labels]]\nid = "A"\nname = "a"\n',
        encoding="utf-8",
    )
    body = (
        model_entry()
        + '[[passes]]\nid = "p"\nquestion = "protocol_v1/sdg_pass1"\nmodels = ["m1"]\nunits = { rule = "all" }\n'
    )
    path = write_workflow(tmp_path, body, lists={"sdg": "lists/mine.toml"})
    with pytest.raises(tagger.ListError):
        tagger.load_workflow(path)
