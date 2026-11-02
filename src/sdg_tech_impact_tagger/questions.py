"""Questions (contract section 3): loading, checking, prompt ids and rendering.

A question is a directory holding prompt files, of which only the fenced
blocks count, and a `question.toml` naming the blocks, how their
placeholders are filled, the lists and text fields used, the readout and
the budgets. Loading a question checks everything that can be checked
without a work, and computes its prompt ids, which must equal the ones the
file states.
"""

from __future__ import annotations

import json
import os
import re
import string
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sdg_tech_impact_tagger.blocks import OPEN_MARKER, file_sha256, read_blocks, sha12
from sdg_tech_impact_tagger.errors import (
    QuestionError,
    TextsError,
    UnitsError,
)
from sdg_tech_impact_tagger.lists import LabelList, label_values, shipped_lists

QUESTIONS_DIR = Path(__file__).resolve().parent / "questions"

LEVELS = ("work", "work x list", "work x list x list")
READOUTS = ("score_json", "letter_logprob", "letter_text", "json_object")
LETTER_RE = re.compile(r"[A-Za-z0-9]+")
SIDE_RE = r"^[a-z]+$"
OTHER = "OTHER"


def pydantic_message(exc: ValidationError) -> str:
    """One line per error of a pydantic validation, `location: message`."""
    lines = []
    for error in exc.errors():
        where = ".".join(str(part) for part in error["loc"]) or "(top)"
        lines.append(f"{where}: {error['msg']}")
    return "; ".join(lines)


# --------------------------------------------------------------------------
# question.toml, read into strict models that refuse unknown keys
# --------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class _Head(_Strict):
    name: str
    level: Literal["work", "work x list", "work x list x list"]
    per_call: Literal["unit", "work"] = "unit"
    readout: Literal["score_json", "letter_logprob", "letter_text", "json_object"]
    fill: Literal["format", "replace"] = "format"
    prompt_id: str | None = None
    prompt_ids: dict[str, str] | None = None
    recorded_ids: list[str] = []
    status: Literal["current", "record", "experimental"]


class _Lists(_Strict):
    a: str | None = None
    b: str | None = None


class _Text(_Strict):
    fields: list[str] = Field(min_length=1)


class _Fill(_Strict):
    system: dict[str, str]
    user: dict[str, str]
    side: dict[str, str] | None = None


class _Blocks(_Strict):
    files: list[str] = Field(min_length=1)
    system: str
    user: str
    fill: _Fill


class _Side(_Strict):
    name: str = Field(pattern=SIDE_RE)
    block: str


class _Material(_Strict):
    list: Literal["a", "b"]
    file: str | None = None
    block: str | None = None
    part: Literal["whole", "name", "body"] | None = None
    json_path: str | None = None
    key: str | None = None
    list_field: str | None = None


class _Listing(_Strict):
    list: Literal["a", "b"]
    item: str
    sep: str


class _Assembly(_Strict):
    kind: Literal["impact_work_v1"]
    preamble: str
    cut: str


class _Field(_Strict):
    name: str
    type: Literal["letter", "string", "quote", "boolean", "integer", "number"]
    letters: list[str] | None = None


class _Readout(_Strict):
    schema_name: str | None = None
    letters: list[str] | None = None
    layout: Literal["single", "table"] | None = None
    table: str | None = None
    form: Literal["label_object", "impact_pairs_v1"] | None = None
    schema_: bool | None = Field(default=None, alias="schema")
    fields: list[_Field] | None = None


class _Budget(_Strict):
    max_tokens: int | None = Field(default=None, ge=1)
    retry_max_tokens: int | None = None
    top_logprobs: int | None = None


class _IdJson(_Strict):
    file: str
    path: str


class _IdPart(_Strict):
    per: Literal["list", "label"]
    prefix: str
    material: list[str] = Field(min_length=1)


class _Id(_Strict):
    prefix: str
    blocks: list[str]
    json_: _IdJson | None = Field(default=None, alias="json")
    inner: str | None = None
    parts: list[_IdPart] = []


class _QuestionFile(_Strict):
    question: _Head
    lists: _Lists = _Lists()
    text: _Text
    blocks: _Blocks
    sides: list[_Side] | None = None
    material: dict[str, _Material] = {}
    listing: dict[str, _Listing] = {}
    assembly: _Assembly | None = None
    readout: _Readout
    budget: _Budget
    id: _Id


# --------------------------------------------------------------------------
# the loaded question
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AnswerField:
    """One field of a `label_object` item: its name, type and, for a letter, its letters."""

    name: str
    type: str
    letters: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadoutSpec:
    """The readout settings of a question, checked against its readout (section 4)."""

    kind: str
    letters: tuple[str, ...] = ()
    layout: str | None = None
    table: str | None = None
    form: str | None = None
    schema: bool = False
    schema_name: str | None = None
    fields: tuple[AnswerField, ...] = ()


@dataclass(frozen=True)
class Budget:
    """The question's budgets: first budget, retry budget, top logprobs."""

    max_tokens: int
    retry_max_tokens: int | None
    top_logprobs: int | None


@dataclass
class Question:
    """A checked question.

    Public attributes: `name`, `level`, `readout`, `text_fields`, `lists`
    (side `a` or `b` to list id) and `prompt_ids` (`{"": id}` when the id
    does not depend on the label, else label code of list `a` to id). Use
    `render` to see the calls of a work.
    """

    name: str
    level: str
    readout: str
    text_fields: tuple[str, ...]
    lists: dict[str, str]
    prompt_ids: dict[str, str]
    status: str
    per_call: str
    directory: Path
    spec: ReadoutSpec
    budget: Budget
    recorded_ids: tuple[str, ...]
    prefix: str
    label_lists: dict[str, LabelList] = field(repr=False)
    blocks: dict[str, str] = field(repr=False)
    fill_mode: str = "format"
    system_block: str = ""
    user_block: str = ""
    fill_system: dict[str, str] = field(default_factory=dict, repr=False)
    fill_user: dict[str, str] = field(default_factory=dict, repr=False)
    fill_side: dict[str, str] = field(default_factory=dict, repr=False)
    sides: tuple[tuple[str, str], ...] = ()
    materials: dict[str, dict[str, str]] = field(default_factory=dict, repr=False)
    material_list: dict[str, str] = field(default_factory=dict, repr=False)
    listings: dict[str, str] = field(default_factory=dict, repr=False)
    assembly: dict[str, str] | None = None
    files_read: dict[str, str] = field(default_factory=dict, repr=False)
    head_text_hash: str = ""
    label_parts: dict[str, list[str]] = field(default_factory=dict, repr=False)
    list_parts: list[str] = field(default_factory=list, repr=False)

    # -- ids ---------------------------------------------------------------

    @property
    def per_label(self) -> bool:
        """Whether the prompt id depends on the label of list `a`."""
        return bool(self.label_parts)

    def ids_with_prefix(self, prefix: str | None = None) -> dict[str, str]:
        """The prompt ids with the head prefix replaced by `prefix` (the question's when None)."""
        head = (prefix or self.prefix) + "-" + self.head_text_hash
        if not self.per_label:
            return {"": "+".join([head, *self.list_parts])}
        return {
            code: "+".join([head, *parts]) for code, parts in self.label_parts.items()
        }

    # -- rendering ---------------------------------------------------------

    @property
    def side_names(self) -> tuple[str, ...]:
        """The names of the sides, in order; empty without sides."""
        return tuple(name for name, _ in self.sides)

    @property
    def rows_per_label(self) -> bool:
        """Whether a work-level call is read into one row per label of list `a`."""
        return self.level == "work" and (
            self.readout == "score_json"
            or (self.readout == "letter_text" and self.spec.layout == "table")
            or (self.readout == "json_object" and self.spec.form == "label_object")
        )

    def render(
        self,
        texts: Mapping[str, str | None],
        units: Sequence[tuple[str, ...]] = (),
        *,
        null_text: str = "",
    ) -> list[tuple[str, str]]:
        """The (system, user) texts of the calls of one work's units, in call order.

        Consumes the work's text fields (a null as `null_text`) and, at the
        list levels, units as tuples of codes, `(a,)` or `(a, b)`. At level
        `work`, `units` must be empty and the work's call (one per side) is
        returned. At a list level, each unit gives one call per side in side
        order, or one call; with `per_call = "work"`, one call holds every
        given unit; no units give `[]`. Raises `TextsError` on a missing
        field and `UnitsError` on a unit of the wrong length or code.
        """
        work = {}
        for name in self.text_fields:
            if name not in texts:
                raise TextsError(f"the texts given to render have no field {name}")
            work[name] = texts[name]
        units = [tuple(unit) for unit in units]
        if self.level == "work":
            if units:
                raise UnitsError(
                    f"{self.name} is a work question: render takes no units"
                )
            return self._calls_of_unit(work, (), null_text)
        labels = [self.unit_labels(unit) for unit in units]
        if not units:
            return []
        if self.per_call == "work":
            return [self.assemble(work, units, null_text)]
        calls: list[tuple[str, str]] = []
        for unit, _ in zip(units, labels, strict=True):
            calls.extend(self._calls_of_unit(work, unit, null_text))
        return calls

    def unit_labels(self, unit: tuple[str, ...]) -> tuple[dict[str, str], ...]:
        """The labels of a unit's codes; `UnitsError` on a wrong length or an unknown code."""
        sides = ["a"] if self.level == "work x list" else ["a", "b"]
        if self.level == "work":
            sides = []
        if len(unit) != len(sides):
            raise UnitsError(
                f"a unit of {self.name} holds {len(sides)} codes, not {len(unit)}: {unit!r}"
            )
        labels = []
        for side, code in zip(sides, unit, strict=True):
            listed = self.label_lists[side]
            try:
                labels.append(listed.label(code))
            except KeyError:
                raise UnitsError(
                    f"{code!r} is not a label of the list {listed.id}"
                ) from None
        return tuple(labels)

    def _value(
        self,
        source: str,
        work: Mapping[str, str | None],
        null_text: str,
        labels: Mapping[str, dict[str, str]],
        side_text: str | None,
    ) -> str:
        kind, _, arg = source.partition(":")
        if source == "side":
            if side_text is None:
                raise QuestionError(f"{self.name}: no side text to fill")
            return side_text
        if kind == "text":
            value = work[arg]
            return null_text if value is None else value
        if kind in ("a", "b"):
            if kind not in labels:
                raise UnitsError(
                    f"{self.name}: no label of list {kind} to fill {source}"
                )
            return label_values(labels[kind])[arg]
        if kind == "material":
            side = self.material_list[arg]
            if side not in labels:
                raise UnitsError(
                    f"{self.name}: no label of list {side} to fill {source}"
                )
            return self.materials[arg][labels[side]["id"]]
        if kind == "block":
            return self.blocks[arg]
        if kind == "listing":
            return self.listings[arg]
        raise QuestionError(f"{self.name}: unknown source {source!r}")

    def _fill(
        self,
        template: str,
        table: Mapping[str, str],
        work: Mapping[str, str | None],
        null_text: str,
        labels: Mapping[str, dict[str, str]],
        side_text: str | None = None,
        mode: str | None = None,
    ) -> str:
        values = {
            name: self._value(source, work, null_text, labels, side_text)
            for name, source in table.items()
        }
        if (mode or self.fill_mode) == "format":
            return template.format(**values)
        for name, value in values.items():
            template = template.replace("{" + name + "}", value)
        return template

    def _labels_of(self, unit: tuple[str, ...]) -> dict[str, dict[str, str]]:
        found = self.unit_labels(unit)
        return dict(zip(("a", "b"), found, strict=False))

    def _calls_of_unit(
        self, work: Mapping[str, str | None], unit: tuple[str, ...], null_text: str
    ) -> list[tuple[str, str]]:
        labels = self._labels_of(unit)
        system = self._fill(
            self.system_block, self.fill_system, work, null_text, labels
        )
        if not self.sides:
            user = self._fill(self.user_block, self.fill_user, work, null_text, labels)
            return [(system, user)]
        calls = []
        for _, block in self.sides:
            side_text = self._fill(
                self.blocks[block], self.fill_side, work, null_text, labels
            )
            user = self._fill(
                self.user_block, self.fill_user, work, null_text, labels, side_text
            )
            calls.append((system, user))
        return calls

    def assemble(
        self,
        work: Mapping[str, str | None],
        units: Sequence[tuple[str, ...]],
        null_text: str,
    ) -> tuple[str, str]:
        """The one call of a work over all its units, by `[assembly]` (contract 3.4).

        Units are ordered by (a, b); the `b` labels go in order of first
        appearance, each with its `a` labels; units are numbered P1, P2, ...
        in that order (`assembly_order` gives it).
        """
        assert self.assembly is not None
        ordered = self.assembly_order(units)
        system_block = self._fill(
            self.system_block, self.fill_system, work, null_text, {}
        )
        system = (
            self.blocks[self.assembly["preamble"]]
            + "\n\n"
            + system_block.rstrip()
            + "\n"
        )
        head = self.user_block.split("{question}", 1)[0]
        table = {k: v for k, v in self.fill_user.items() if v != "side"}
        cut = self.assembly["cut"]
        blocks = {name: self.blocks[block] for name, block in self.sides}
        parts: list[str] = []
        goals: list[str] = []
        for unit in ordered:
            if unit[1] not in goals:
                goals.append(unit[1])
        number = 0
        for goal in goals:
            goal_labels = {"b": self.label_lists["b"].label(goal)}
            section = self._fill(
                head, table, work, null_text, goal_labels, mode="format"
            )
            if parts:
                at = section.find(cut)
                if at < 0:
                    raise QuestionError(
                        f"{self.name}: the cut {cut!r} is not in the user text"
                    )
                section = section[at:]
            parts.append(section)
            for unit in ordered:
                if unit[1] != goal:
                    continue
                number += 1
                labels = self._labels_of(unit)
                pos = self._fill(blocks["pos"], self.fill_side, work, null_text, labels)
                neg = self._fill(blocks["neg"], self.fill_side, work, null_text, labels)
                parts.append(f"P{number}, beneficial: " + pos)
                parts.append(f"P{number}, detrimental: " + neg)
                parts.append("")
        parts.append("Return the JSON object.")
        return system, "\n".join(parts)

    def assembly_order(self, units: Sequence[tuple[str, ...]]) -> list[tuple[str, ...]]:
        """A work's units in the order of its assembled call: P1, P2, ..."""
        for unit in units:
            self.unit_labels(tuple(unit))
        ordered = sorted(tuple(unit) for unit in units)
        goals: list[str] = []
        for unit in ordered:
            if unit[1] not in goals:
                goals.append(unit[1])
        return [unit for goal in goals for unit in ordered if unit[1] == goal]

    def joined_text(self, work: Mapping[str, str | None], null_text: str) -> str:
        """The question's text fields in order, nulls as `null_text`, joined by newlines."""
        return "\n".join(
            null_text if work[name] is None else str(work[name])
            for name in self.text_fields
        )


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def _template_fields(template: str, where: str) -> list[str]:
    """The field names of a `str.format` template; refuse conversions, specs, indexes."""
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as exc:
        raise QuestionError(f"{where}: not a format template: {exc}") from exc
    names = []
    for _, name, spec, conversion in parsed:
        if name is None:
            continue
        if conversion is not None or spec or not name.isidentifier():
            raise QuestionError(
                f"{where}: the placeholder {{{name}"
                + (f"!{conversion}" if conversion else "")
                + (f":{spec}" if spec else "")
                + "} is refused: only plain names are filled"
            )
        names.append(name)
    return names


def _check_placeholders(
    template: str, table: Mapping[str, str], mode: str, where: str
) -> None:
    """The fill table fits the template: exactly its fields, or each `{name}` present."""
    if mode == "format":
        found = set(_template_fields(template, where))
        if found != set(table):
            raise QuestionError(
                f"{where}: placeholders {sorted(found)} do not match the fill table {sorted(table)}"
            )
        return
    absent = [name for name in table if "{" + name + "}" not in template]
    if absent:
        raise QuestionError(
            f"{where}: no placeholder {', '.join(absent)} in the template"
        )


def _resolve(directory: Path, relative: str, shipped: bool, where: str) -> Path:
    """A file of the question; a shipped question never reads outside `questions/`."""
    path = directory / relative
    if shipped:
        real = Path(os.path.normpath(path.resolve()))
        if not real.is_relative_to(QUESTIONS_DIR):
            raise QuestionError(f"{where}: {relative} is outside questions/")
    return path


def _question_directory(name_or_path: str | Path) -> tuple[Path, bool]:
    """The directory of a question named as shipped (`family/name`) or given by path."""
    if isinstance(name_or_path, str):
        shipped = QUESTIONS_DIR / name_or_path
        if (shipped / "question.toml").is_file() and not Path(
            name_or_path
        ).is_absolute():
            return shipped, True
    path = Path(name_or_path)
    if not (path / "question.toml").is_file():
        raise QuestionError(f"no question at {name_or_path}: no question.toml there")
    shipped = path.resolve().is_relative_to(QUESTIONS_DIR)
    return path, shipped


def load_question(
    name_or_path: str | Path,
    lists: Mapping[str, LabelList] | None = None,
) -> Question:
    """Load and check a question, by shipped name (`impact/p3_2`) or directory path.

    `lists` maps list id to list; the shipped `sdg` and `adt` lists by
    default. Produces a `Question` whose prompt ids are computed by the rule
    of contract 3.5 and equal the ones `question.toml` states. Raises
    `QuestionError` on anything of section 3 that does not fit.
    """
    registry = dict(lists) if lists is not None else shipped_lists()
    return _load(name_or_path, registry, ())


def _load(
    name_or_path: str | Path, registry: Mapping[str, LabelList], seen: tuple
) -> Question:
    directory, shipped = _question_directory(name_or_path)
    toml_path = directory / "question.toml"
    where = str(toml_path)
    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise QuestionError(f"{where}: not TOML: {exc}") from exc
    try:
        spec = _QuestionFile.model_validate(data)
    except ValidationError as exc:
        raise QuestionError(f"{where}: {pydantic_message(exc)}") from exc
    head = spec.question
    files_read: dict[str, str] = {"question.toml": file_sha256(toml_path)}

    # Lists by level and readout.
    label_lists: dict[str, LabelList] = {}
    for side in ("a", "b"):
        list_id = getattr(spec.lists, side)
        if list_id is None:
            continue
        if list_id not in registry:
            raise QuestionError(f"{where}: unknown list {list_id!r} for side {side}")
        label_lists[side] = registry[list_id]
    needs = {"work": [], "work x list": ["a"], "work x list x list": ["a", "b"]}[
        head.level
    ]
    if head.readout == "score_json" or (
        head.readout in ("letter_text", "json_object")
        and (spec.readout.layout == "table" or spec.readout.form == "label_object")
    ):
        needs = sorted(set(needs) | {"a"})
    missing = [side for side in needs if side not in label_lists]
    if missing:
        raise QuestionError(f"{where}: [lists] needs {', '.join(missing)}")
    if "b" in label_lists and head.level != "work x list x list":
        raise QuestionError(f"{where}: list b is for level work x list x list only")
    if len(label_lists) == 2 and label_lists["a"].id == label_lists["b"].id:
        raise QuestionError(f"{where}: lists a and b are the same list")

    readout_spec = _readout_spec(spec, where)
    budget = _budget(spec, where)
    _check_shape(spec, readout_spec, where)

    # Blocks.
    blocks: dict[str, str] = {}
    for relative in spec.blocks.files:
        path = _resolve(directory, relative, shipped, where)
        for name, body in read_blocks(path).items():
            if name in blocks:
                raise QuestionError(f"{where}: the block {name} is in two files")
            blocks[name] = body
        files_read[relative] = file_sha256(path)

    def block(name: str, role: str) -> str:
        if name not in blocks:
            raise QuestionError(f"{where}: no block {name} ({role})")
        return blocks[name]

    named: dict[str, str] = {}
    named[spec.blocks.system] = block(spec.blocks.system, "system")
    named[spec.blocks.user] = block(spec.blocks.user, "user")
    sides = tuple((s.name, s.block) for s in spec.sides or [])
    if spec.sides is not None:
        if len(sides) < 2:
            raise QuestionError(f"{where}: [[sides]] needs two sides or more")
        if len({name for name, _ in sides}) != len(sides):
            raise QuestionError(f"{where}: repeated side name")
        if spec.blocks.fill.side is None:
            raise QuestionError(f"{where}: sides need [blocks.fill.side]")
        for name, side_block in sides:
            named[side_block] = block(side_block, f"side {name}")
    elif spec.blocks.fill.side is not None:
        raise QuestionError(f"{where}: [blocks.fill.side] without [[sides]]")
    for name in spec.id.blocks:
        named[name] = block(name, "id")
    if spec.assembly is not None:
        named[spec.assembly.preamble] = block(spec.assembly.preamble, "preamble")

    # Material, per label, for every label of its list.
    materials: dict[str, dict[str, str]] = {}
    material_list: dict[str, str] = {}
    for mname, material in spec.material.items():
        if material.list not in label_lists:
            raise QuestionError(
                f"{where}: material {mname} reads list {material.list}, absent"
            )
        materials[mname] = _read_material(
            directory,
            shipped,
            mname,
            material,
            label_lists[material.list],
            files_read,
            where,
        )
        material_list[mname] = material.list

    # Fill tables: every source must name something that exists.
    fill_sys, fill_user = spec.blocks.fill.system, spec.blocks.fill.user
    fill_side = spec.blocks.fill.side or {}
    for table_name, table in (
        ("system", fill_sys),
        ("user", fill_user),
        ("side", fill_side),
    ):
        for placeholder, source in table.items():
            _check_source(
                source, table_name, spec, label_lists, materials, blocks, sides, where
            )
            if source.startswith("block:"):
                named[source[6:]] = blocks[source[6:]]
            del placeholder
    mode = head.fill
    _check_placeholders(named[spec.blocks.system], fill_sys, mode, f"{where} system")
    _check_placeholders(named[spec.blocks.user], fill_user, mode, f"{where} user")
    for name, side_block in sides:
        _check_placeholders(blocks[side_block], fill_side, mode, f"{where} side {name}")
    if spec.assembly is not None:
        tail = blocks[spec.blocks.user].split("{question}", 1)
        if len(tail) != 2 or tail[1].strip():
            raise QuestionError(f"{where}: the user block must end with {{question}}")
        if {"pos", "neg"} - {name for name, _ in sides}:
            raise QuestionError(f"{where}: impact_work_v1 needs the sides pos and neg")

    # The [[OPEN marker, in every block read by name and every label's material.
    marked = [f"block {name}" for name, body in named.items() if OPEN_MARKER in body]
    for mname, texts in materials.items():
        marked += [
            f"material {mname} of {code}"
            for code, t in texts.items()
            if OPEN_MARKER in t
        ]
    if marked:
        raise QuestionError(f"{where}: [[OPEN marker in {', '.join(marked)}")

    # Listings over a whole list.
    listings: dict[str, str] = {}
    for lname, listing in spec.listing.items():
        if listing.list not in label_lists:
            raise QuestionError(
                f"{where}: listing {lname} reads list {listing.list}, absent"
            )
        items = []
        for label in label_lists[listing.list].labels:
            values = label_values(label)
            for mname, texts in materials.items():
                if material_list[mname] == listing.list:
                    values[mname] = texts[label["id"]]
            try:
                items.append(listing.item.format(**values))
            except (KeyError, IndexError, ValueError) as exc:
                raise QuestionError(f"{where}: listing {lname}: {exc!r}") from exc
        listings[lname] = listing.sep.join(items)

    # The prompt id (3.5).
    head_hash, list_parts, label_parts = _prompt_id_parts(
        spec,
        directory,
        shipped,
        blocks,
        materials,
        material_list,
        label_lists,
        registry,
        files_read,
        where,
        seen,
    )
    question = Question(
        name=head.name,
        level=head.level,
        readout=head.readout,
        text_fields=tuple(spec.text.fields),
        lists={side: listed.id for side, listed in label_lists.items()},
        prompt_ids={},
        status=head.status,
        per_call=head.per_call,
        directory=directory,
        spec=readout_spec,
        budget=budget,
        recorded_ids=tuple(head.recorded_ids),
        prefix=spec.id.prefix,
        label_lists=label_lists,
        blocks=blocks,
        fill_mode=mode,
        system_block=blocks[spec.blocks.system],
        user_block=blocks[spec.blocks.user],
        fill_system=dict(fill_sys),
        fill_user=dict(fill_user),
        fill_side=dict(fill_side),
        sides=sides,
        materials=materials,
        material_list=material_list,
        listings=listings,
        assembly=(
            None
            if spec.assembly is None
            else {"preamble": spec.assembly.preamble, "cut": spec.assembly.cut}
        ),
        files_read=files_read,
        head_text_hash=head_hash,
        label_parts=label_parts,
        list_parts=list_parts,
    )
    computed = question.ids_with_prefix()
    question.prompt_ids = computed
    if label_parts:
        expected = head.prompt_ids
        if expected is None or head.prompt_id is not None:
            raise QuestionError(
                f"{where}: the id depends on the label: give prompt_ids"
            )
        if set(expected) != set(computed):
            raise QuestionError(
                f"{where}: prompt_ids name {sorted(expected)}, the list holds {sorted(computed)}"
            )
        for code, value in computed.items():
            if expected[code] != value:
                raise QuestionError(
                    f"{where}: the id of {code} is {value}, not {expected[code]}: refused"
                )
    else:
        if head.prompt_id is None or head.prompt_ids is not None:
            raise QuestionError(
                f"{where}: give prompt_id (the id does not depend on the label)"
            )
        if head.prompt_id != computed[""]:
            raise QuestionError(
                f"{where}: the computed id is {computed['']}, not {head.prompt_id}: refused"
            )
    return question


def _readout_spec(spec: _QuestionFile, where: str) -> ReadoutSpec:
    """Check the [readout] table against the readout and return its settings."""
    readout, r = spec.question.readout, spec.readout
    given = {k for k, v in r.model_dump(by_alias=True).items() if v is not None}
    allowed = {
        "score_json": {"schema_name"},
        "letter_logprob": {"letters"},
        "letter_text": {"letters", "layout", "table"},
        "json_object": {"form", "schema", "schema_name", "fields"},
    }[readout]
    extra = sorted(given - allowed)
    if extra:
        raise QuestionError(
            f"{where}: [readout] of {readout} takes no {', '.join(extra)}"
        )

    def letters_of(values: list[str] | None, what: str) -> tuple[str, ...]:
        if not values:
            raise QuestionError(f"{where}: {what} needs letters")
        for letter in values:
            if LETTER_RE.fullmatch(letter) is None or letter == OTHER:
                raise QuestionError(f"{where}: bad letter {letter!r} in {what}")
        if len({letter.lower() for letter in values}) != len(values):
            raise QuestionError(f"{where}: letters of {what} repeat (case ignored)")
        return tuple(values)

    if readout == "score_json":
        if r.schema_name is None:
            raise QuestionError(f"{where}: score_json needs [readout].schema_name")
        return ReadoutSpec(kind=readout, schema_name=r.schema_name)
    if readout == "letter_logprob":
        return ReadoutSpec(kind=readout, letters=letters_of(r.letters, "[readout]"))
    if readout == "letter_text":
        layout = r.layout or "single"
        if layout == "table" and not r.table:
            raise QuestionError(f"{where}: layout table needs [readout].table")
        if layout == "single" and r.table is not None:
            raise QuestionError(f"{where}: layout single takes no table")
        return ReadoutSpec(
            kind=readout,
            letters=letters_of(r.letters, "[readout]"),
            layout=layout,
            table=r.table,
        )
    if r.form is None:
        raise QuestionError(f"{where}: json_object needs [readout].form")
    if r.form == "impact_pairs_v1":
        extra = sorted(given - {"form"})
        if extra:
            raise QuestionError(f"{where}: impact_pairs_v1 takes no {', '.join(extra)}")
        return ReadoutSpec(kind=readout, form=r.form)
    schema = bool(r.schema_)
    if schema and not r.schema_name:
        raise QuestionError(f"{where}: schema = true needs schema_name")
    fields: list[AnswerField] = []
    for f in r.fields or []:
        if f.type == "letter":
            fields.append(
                AnswerField(f.name, f.type, letters_of(f.letters, f"field {f.name}"))
            )
        else:
            if f.letters is not None:
                raise QuestionError(
                    f"{where}: field {f.name} of type {f.type} takes no letters"
                )
            fields.append(AnswerField(f.name, f.type))
    names = [f.name for f in fields]
    if len(set(names)) != len(names):
        raise QuestionError(f"{where}: repeated field name")
    return ReadoutSpec(
        kind=readout,
        form=r.form,
        schema=schema,
        schema_name=r.schema_name,
        fields=tuple(fields),
    )


def _budget(spec: _QuestionFile, where: str) -> Budget:
    """Check the [budget] table against the readout (3.3) and fill its defaults."""
    readout, b = spec.question.readout, spec.budget
    if b.max_tokens is None:
        if readout != "letter_logprob":
            raise QuestionError(f"{where}: [budget].max_tokens is required")
        max_tokens = 1
    else:
        max_tokens = b.max_tokens
    if b.retry_max_tokens is not None:
        if readout not in ("letter_text", "json_object"):
            raise QuestionError(
                f"{where}: retry_max_tokens is for letter_text and json_object"
            )
        if b.retry_max_tokens <= max_tokens:
            raise QuestionError(f"{where}: retry_max_tokens must be above max_tokens")
    top = b.top_logprobs
    if top is not None:
        if readout != "letter_logprob":
            raise QuestionError(f"{where}: top_logprobs is for letter_logprob only")
        if not 0 <= top <= 20:
            raise QuestionError(f"{where}: top_logprobs must be 0 to 20, not {top}")
    if readout == "letter_logprob" and top is None:
        top = 20
    return Budget(
        max_tokens=max_tokens, retry_max_tokens=b.retry_max_tokens, top_logprobs=top
    )


def _check_shape(spec: _QuestionFile, r: ReadoutSpec, where: str) -> None:
    """Level, per_call, readout, sides and assembly fit together (sections 3.3, 4)."""
    head = spec.question
    if r.kind == "score_json" and head.level != "work":
        raise QuestionError(f"{where}: score_json is a work question")
    if r.layout == "table" and head.level != "work":
        raise QuestionError(f"{where}: a letter table is a work question")
    if r.form == "label_object" and head.level != "work":
        raise QuestionError(f"{where}: label_object is a work question")
    if r.form == "impact_pairs_v1" and (
        head.level != "work x list x list"
        or head.per_call != "work"
        or spec.assembly is None
    ):
        raise QuestionError(
            f"{where}: impact_pairs_v1 is per_call work at work x list x list, with an assembly"
        )
    if head.per_call == "work" and (
        spec.assembly is None or r.form != "impact_pairs_v1"
    ):
        raise QuestionError(
            f"{where}: per_call work needs [assembly] and impact_pairs_v1"
        )
    if spec.assembly is not None and head.per_call != "work":
        raise QuestionError(f"{where}: [assembly] is for per_call work only")
    if spec.sides is not None and (
        r.kind in ("score_json",) or r.layout == "table" or r.form == "label_object"
    ):
        raise QuestionError(f"{where}: this readout takes no sides")


def _check_source(
    source: str,
    table: str,
    spec: _QuestionFile,
    label_lists: Mapping[str, LabelList],
    materials: Mapping[str, dict[str, str]],
    blocks: Mapping[str, str],
    sides: tuple[tuple[str, str], ...],
    where: str,
) -> None:
    """A fill source names a text field, a list field, material, a block, a listing or the side."""
    if source == "side":
        if table != "user" or not sides:
            raise QuestionError(
                f"{where}: side fills the user block of a question with sides"
            )
        return
    kind, sep, arg = source.partition(":")
    if not sep or not arg:
        raise QuestionError(f"{where}: bad source {source!r}")
    if kind == "text":
        if arg not in spec.text.fields:
            raise QuestionError(f"{where}: {source} is not in [text].fields")
    elif kind in ("a", "b"):
        if kind not in label_lists:
            raise QuestionError(f"{where}: {source} reads a list the question has not")
        keys = set(label_lists[kind].labels[0]) | {"slug"}
        if arg not in keys:
            raise QuestionError(f"{where}: {source}: the list has no field {arg}")
    elif kind == "material":
        if arg not in materials:
            raise QuestionError(f"{where}: no [material.{arg}]")
    elif kind == "block":
        if arg not in blocks:
            raise QuestionError(f"{where}: no block {arg} for {source}")
    elif kind == "listing":
        if arg not in spec.listing:
            raise QuestionError(f"{where}: no [listing.{arg}]")
    else:
        raise QuestionError(f"{where}: unknown source {source!r}")


def _format_label(template: str, label: dict[str, str], where: str) -> str:
    try:
        return template.format(**label_values(label))
    except (KeyError, IndexError, ValueError) as exc:
        raise QuestionError(f"{where}: cannot format {template!r}: {exc!r}") from exc


def _read_material(
    directory: Path,
    shipped: bool,
    name: str,
    material: _Material,
    listed: LabelList,
    files_read: dict[str, str],
    where: str,
) -> dict[str, str]:
    """The material of every label of the list, checked as [OA] adt_pass1.py:39-83 does."""
    where = f"{where} [material.{name}]"
    if material.list_field is not None:
        if any(
            v is not None
            for v in (
                material.file,
                material.block,
                material.json_path,
                material.key,
                material.part,
            )
        ):
            raise QuestionError(f"{where}: list_field stands alone")
        if material.list_field not in set(listed.labels[0]) | {"slug"}:
            raise QuestionError(f"{where}: the list has no field {material.list_field}")
        return {
            label["id"]: label_values(label)[material.list_field]
            for label in listed.labels
        }
    if material.file is None:
        raise QuestionError(
            f"{where}: give file and block, file and json_path, or list_field"
        )
    texts: dict[str, str] = {}
    if material.json_path is not None or material.key is not None:
        if (
            material.json_path is None
            or material.key is None
            or material.block is not None
        ):
            raise QuestionError(
                f"{where}: a JSON material takes file, json_path and key"
            )
        if material.part is not None:
            raise QuestionError(f"{where}: part is for block material")
        cache: dict[str, Any] = {}
        for label in listed.labels:
            relative = _format_label(material.file, label, where)
            if relative not in cache:
                path = _resolve(directory, relative, shipped, where)
                if not path.is_file():
                    raise QuestionError(f"{where}: no file {relative}")
                try:
                    cache[relative] = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise QuestionError(
                        f"{where}: {relative} is not JSON: {exc}"
                    ) from exc
                files_read[relative] = file_sha256(path)
            data = cache[relative]
            mapping = data.get(material.json_path) if isinstance(data, dict) else None
            if not isinstance(mapping, dict):
                raise QuestionError(
                    f"{where}: {relative} has no mapping {material.json_path}"
                )
            key = _format_label(material.key, label, where)
            if key not in mapping or not isinstance(mapping[key], str):
                raise QuestionError(f"{where}: {relative} has no string under {key!r}")
            texts[label["id"]] = mapping[key]
        return texts
    if material.block is None:
        raise QuestionError(f"{where}: a block material takes file and block")
    part = material.part or "whole"
    read: dict[str, dict[str, str]] = {}
    codes = set(listed.codes)
    for label in listed.labels:
        relative = _format_label(material.file, label, where)
        if relative not in read:
            path = _resolve(directory, relative, shipped, where)
            read[relative] = read_blocks(path)
            files_read[relative] = file_sha256(path)
            if material.block == "{id}":
                strays = sorted(set(read[relative]) - codes)
                if strays:
                    raise QuestionError(
                        f"{where}: {relative} holds blocks not in the list: {', '.join(strays)}"
                    )
        block_name = _format_label(material.block, label, where)
        if block_name not in read[relative]:
            raise QuestionError(f"{where}: {relative} has no block {block_name}")
        body = read[relative][block_name]
        code = label["id"]
        if part == "whole":
            if not body.strip():
                raise QuestionError(f"{where}: the block {block_name} is empty")
            texts[code] = body
            continue
        lines = body.split("\n")
        if not lines[0].strip():
            raise QuestionError(
                f"{where}: the block {block_name} has an empty name line"
            )
        if part == "name":
            texts[code] = lines[0]
            continue
        if len(lines) == 1:
            raise QuestionError(f"{where}: the block {block_name} has an empty body")
        if lines[1].strip():
            raise QuestionError(
                f"{where}: the block {block_name} has no blank line after its name"
            )
        definition = "\n".join(lines[2:]).strip("\n")
        if not definition.strip():
            raise QuestionError(f"{where}: the block {block_name} has an empty body")
        texts[code] = definition
    return texts


def _prompt_id_parts(
    spec: _QuestionFile,
    directory: Path,
    shipped: bool,
    blocks: Mapping[str, str],
    materials: Mapping[str, dict[str, str]],
    material_list: Mapping[str, str],
    label_lists: Mapping[str, LabelList],
    registry: Mapping[str, LabelList],
    files_read: dict[str, str],
    where: str,
    seen: tuple,
) -> tuple[str, list[str], dict[str, list[str]]]:
    """The hash of the head, the per-list part ids and the per-label part ids (3.5)."""
    rule = spec.id
    head_text = "\n".join(blocks[name] for name in rule.blocks)
    if rule.json_ is not None:
        path = _resolve(directory, rule.json_.file, shipped, where)
        if not path.is_file():
            raise QuestionError(f"{where}: no file {rule.json_.file}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise QuestionError(f"{where}: {rule.json_.file} is not JSON") from exc
        if not isinstance(data, dict) or rule.json_.path not in data:
            raise QuestionError(f"{where}: {rule.json_.file} has no {rule.json_.path}")
        head_text += "\n" + json.dumps(
            data[rule.json_.path], sort_keys=True, ensure_ascii=False
        )
        files_read[rule.json_.file] = file_sha256(path)
    if rule.inner is not None:
        if rule.inner in seen:
            raise QuestionError(f"{where}: the inner question {rule.inner} loops")
        inner = _load(rule.inner, registry, (*seen, spec.question.name))
        if inner.per_label:
            raise QuestionError(
                f"{where}: the inner question's id depends on the label"
            )
        head_text += "\n" + inner.prompt_ids[""]
        for relative, digest in inner.files_read.items():
            path = os.path.relpath(inner.directory / relative, directory).replace(
                os.sep, "/"
            )
            files_read.setdefault(path, digest)
    # Each part gives one id, or one id per label of list a; kept in part order.
    ordered: list[str | dict[str, str]] = []
    for part in rule.parts:
        for mname in part.material:
            if mname not in materials:
                raise QuestionError(f"{where}: [[id.parts]] names no material {mname}")
        sides = {material_list[m] for m in part.material}
        if len(sides) != 1:
            raise QuestionError(f"{where}: a part reads the material of one list")
        listed = label_lists[sides.pop()]
        texts = {
            label["id"]: "\n".join(materials[m][label["id"]] for m in part.material)
            for label in listed.labels
        }
        if part.per == "list":
            joined = "\n".join(texts[label["id"]] for label in listed.labels)
            ordered.append(part.prefix + "-" + sha12(joined))
        else:
            if listed is not label_lists.get("a"):
                raise QuestionError(f"{where}: a per-label part reads list a")
            ordered.append(
                {
                    label["id"]: _format_label(part.prefix, label, where)
                    + "-"
                    + sha12(texts[label["id"]])
                    for label in listed.labels
                }
            )
    if not any(isinstance(item, dict) for item in ordered):
        return sha12(head_text), [str(item) for item in ordered], {}
    codes = label_lists["a"].codes
    label_parts = {
        code: [item[code] if isinstance(item, dict) else item for item in ordered]
        for code in codes
    }
    return sha12(head_text), [], label_parts
