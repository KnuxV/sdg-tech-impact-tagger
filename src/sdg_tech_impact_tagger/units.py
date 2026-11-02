"""Unit rules (contract section 5): which units a pass asks about, in plan order.

A unit is a work, a (work, label) or a (work, label, label), by the level of
the question. `all` takes every one; `threshold`, `cross` and the flags of
`file` read the output tables of earlier passes (the sources); `file` reads
a table of units. Every source and file is checked whole before a unit is
taken, and an empty unit set is refused.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from sdg_tech_impact_tagger.blocks import file_sha256
from sdg_tech_impact_tagger.errors import UnitsError
from sdg_tech_impact_tagger.workflow import Pass, Workflow


@dataclass(frozen=True)
class Unit:
    """One unit: its work, its codes (none, `(a,)` or `(a, b)`) and its key values.

    `values` holds the key columns a rule adds, in column order: the flags
    of `cross` (or `file` with flags), or the `source_score` of `threshold`.
    """

    id: str
    codes: tuple[str, ...] = ()
    values: tuple[tuple[str, Any], ...] = ()

    @property
    def code(self) -> str:
        """The unit's code column value: the code, or `<a>|<b>`; `""` for a work."""
        return "|".join(self.codes)


@dataclass
class Plan:
    """The units of a (pass, model) in plan order, the key columns they add, and
    the sources read (path and sha256, for the manifest)."""

    units: list[Unit]
    value_columns: dict[str, pl.DataType] = field(default_factory=dict)
    sources: list[dict[str, str]] = field(default_factory=list)


def plan_units(workflow: Workflow, p: Pass, model: str, works: Sequence[str]) -> Plan:
    """The units of one model of a pass over the works of the texts table, in plan order.

    Consumes the workflow (for the source tables under its output
    directory), the pass, the model entry name and the work ids in table
    order. Produces the `Plan`. Raises `UnitsError` on a missing source
    table, a source or file that fails its checks, a work not in the texts,
    or an empty unit set.
    """
    rule = p.units["rule"]
    question = p.question
    position = {work: n for n, work in enumerate(works)}
    if rule == "all":
        plan = Plan(_all(question.level, question.label_lists, works))
    elif rule == "threshold":
        plan = _threshold(workflow, p, model, position)
    elif rule == "cross":
        plan = _cross(workflow, p, position)
    else:
        plan = _file(workflow, p, position)
    if not plan.units:
        raise UnitsError(
            f"pass {p.id}, model {model}: the unit rule {rule} gives no unit"
        )
    return plan


def _all(
    level: str, label_lists: Mapping[str, Any], works: Sequence[str]
) -> list[Unit]:
    if level == "work":
        return [Unit(work) for work in works]
    a_codes = label_lists["a"].codes
    if level == "work x list":
        return [Unit(work, (a,)) for work in works for a in a_codes]
    b_codes = label_lists["b"].codes
    return [Unit(work, (a, b)) for work in works for a in a_codes for b in b_codes]


def _source(
    workflow: Workflow, pass_id: str, model: str
) -> tuple[pl.DataFrame, dict[str, str]]:
    path = workflow.output_of(pass_id, model)
    if not path.is_file():
        raise UnitsError(
            f"the source table {Path(pass_id) / f'{model}.parquet'} is missing "
            f"(looked for {path}): run pass {pass_id} for model {model} first"
        )
    return pl.read_parquet(path), {"path": str(path), "sha256": file_sha256(path)}


def _threshold(
    workflow: Workflow, p: Pass, model: str, position: dict[str, int]
) -> Plan:
    rule = p.units
    source_model = model if rule["model"] == "same" else rule["model"]
    frame, record = _source(workflow, rule["from"], source_model)
    where = f"the source {rule['from']}/{source_model}.parquet"
    expected = {
        "id": pl.String,
        "code": pl.String,
        "score": pl.Float64,
        "parse_failure": pl.Boolean,
    }
    for name, dtype in expected.items():
        if name not in frame.columns:
            raise UnitsError(f"{where} has no column {name}")
        if frame.schema[name] != dtype:
            raise UnitsError(f"{where}: {name} is {frame.schema[name]}, not {dtype}")
    if frame["id"].null_count() or frame["code"].null_count():
        raise UnitsError(f"{where} has a null id or code")
    codes = p.question.label_lists["a"].codes
    stray = sorted(set(frame["code"].to_list()) - set(codes))
    if stray:
        raise UnitsError(f"{where} holds codes not in the list: {', '.join(stray[:5])}")
    scores = frame["score"].to_list()
    if any(s is None or math.isnan(s) or not 0.0 <= s <= 1.0 for s in scores):
        raise UnitsError(f"{where} holds a score null, NaN or outside [0, 1]")
    pairs = list(zip(frame["id"].to_list(), frame["code"].to_list(), strict=True))
    if len(set(pairs)) != len(pairs):
        raise UnitsError(f"{where} repeats an (id, code)")
    per_work: dict[str, int] = {}
    for work, _ in pairs:
        per_work[work] = per_work.get(work, 0) + 1
    partial = [w for w, n in per_work.items() if n != len(codes)]
    if partial:
        raise UnitsError(
            f"{where}: {len(partial)} works lack a row per label, the first {partial[0]}"
        )
    outside = [w for w in per_work if w not in position]
    if outside:
        raise UnitsError(
            f"{where}: {len(outside)} scored works are not in the texts, the first {outside[0]}"
        )
    unscored = [w for w in position if w not in per_work]
    if unscored and not rule["allow_unscored"]:
        raise UnitsError(
            f"{where}: {len(unscored)} works of the texts have no score, the first "
            f"{unscored[0]} (allow_unscored = true takes the others)"
        )
    at_least = rule["at_least"]
    chosen = [
        (work, code, score)
        for (work, code), score in zip(pairs, scores, strict=True)
        if score >= at_least
    ]
    chosen.sort(key=lambda row: (position[row[0]], row[1]))
    units = [
        Unit(work, (code,), (("source_score", score),)) for work, code, score in chosen
    ]
    return Plan(units, {"source_score": pl.Float64()}, [record])


def _present(
    workflow: Workflow, side: Mapping[str, Any], records: list[dict[str, str]]
) -> list[tuple[str, set[tuple[str, str]]]]:
    """Per source model of a side: its flag name part and the (id, code) present."""
    found = []
    positive = set(side["positive"])
    for model in side["models"]:
        frame, record = _source(workflow, side["from"], model)
        records.append(record)
        missing = [c for c in ("id", "code", "label") if c not in frame.columns]
        if missing:
            raise UnitsError(
                f"the source {side['from']}/{model}.parquet has no column {', '.join(missing)}"
            )
        rows = frame.select("id", "code", "label").iter_rows()
        found.append((model, {(w, c) for w, c, label in rows if label in positive}))
    return found


def _combined(
    side: Mapping[str, Any], found: list[tuple[str, set]]
) -> set[tuple[str, str]]:
    sets = [present for _, present in found]
    if side["combine"] == "intersection":
        return set.intersection(*sets)
    return set.union(*sets)


def _flags(
    p: Pass, sides: Mapping[str, Any], workflow: Workflow, records: list[dict[str, str]]
) -> tuple[list[tuple[str, int, set]], dict[str, set], dict[str, pl.DataType]]:
    """The flag sources of both sides, the combined presence per side, the flag columns."""
    flags: list[tuple[str, int, set]] = []
    combined: dict[str, set] = {}
    columns: dict[str, pl.DataType] = {}
    for n, name in enumerate(("a", "b")):
        side = sides[name]
        found = _present(workflow, side, records)
        list_id = p.question.lists[name]
        for model, present in found:
            flags.append((f"{list_id}_{model}", n, present))
            columns[f"{list_id}_{model}"] = pl.Boolean()
        combined[name] = _combined(side, found)
    return flags, combined, columns


def _flagged(
    work: str, codes: tuple[str, ...], flags: list[tuple[str, int, set]]
) -> Unit:
    values = tuple((name, (work, codes[n]) in present) for name, n, present in flags)
    return Unit(work, codes, values)


def _cross(workflow: Workflow, p: Pass, position: dict[str, int]) -> Plan:
    records: list[dict[str, str]] = []
    flags, combined, columns = _flags(p, p.units, workflow, records)
    a_by_work: dict[str, list[str]] = {}
    for work, code in combined["a"]:
        a_by_work.setdefault(work, []).append(code)
    b_by_work: dict[str, list[str]] = {}
    for work, code in combined["b"]:
        b_by_work.setdefault(work, []).append(code)
    units = [
        _flagged(work, (a, b), flags)
        for work in a_by_work
        if work in b_by_work
        for a in a_by_work[work]
        for b in b_by_work[work]
    ]
    outside = sorted({u.id for u in units if u.id not in position})
    if outside:
        raise UnitsError(
            f"pass {p.id}: {len(outside)} works of the units are not in the texts, "
            f"the first {outside[0]}"
        )
    units.sort(key=lambda u: (u.id, u.code))
    if p.units["agreed_first"]:
        agreed = [u for u in units if all(v for _, v in u.values)]
        units = agreed + [u for u in units if not all(v for _, v in u.values)]
    return Plan(units, columns, records)


def _read_units_file(path: Path) -> pl.DataFrame:
    if not path.is_file():
        raise UnitsError(f"the units file {path} does not exist")
    try:
        if path.suffix.lower() == ".csv":
            return pl.read_csv(path, infer_schema=False)
        frame = pl.read_parquet(path)
    except (pl.exceptions.PolarsError, OSError) as exc:
        raise UnitsError(f"the units file {path} cannot be read: {exc}") from exc
    return frame.with_columns(pl.all().cast(pl.String))


def _file(workflow: Workflow, p: Pass, position: dict[str, int]) -> Plan:
    rule = p.units
    path = workflow.base / rule["path"]
    frame = _read_units_file(path)
    question = p.question
    level = question.level
    if level == "work":
        columns = ["id"]
    elif level == "work x list":
        columns = ["id", "code"]
    else:
        columns = ["id", question.lists["a"], question.lists["b"]]
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise UnitsError(f"the units file {path} has no column {', '.join(missing)}")
    rows = frame.select(columns).rows()
    if any(value is None for row in rows for value in row):
        raise UnitsError(
            f"the units file {path} has an empty cell in {', '.join(columns)}"
        )
    if len(set(rows)) != len(rows):
        raise UnitsError(f"the units file {path} repeats a unit")
    for n, side in enumerate(("a", "b")[: len(columns) - 1]):
        codes = set(question.label_lists[side].codes)
        stray = sorted({row[n + 1] for row in rows} - codes)
        if stray:
            raise UnitsError(
                f"the units file {path}: {', '.join(stray[:5])} not in the list "
                f"{question.lists[side]}"
            )
    outside = [row[0] for row in rows if row[0] not in position]
    if outside:
        raise UnitsError(
            f"the units file {path}: {len(outside)} units of works not in the texts, "
            f"the first {outside[0]}"
        )
    records = [{"path": str(path), "sha256": file_sha256(path)}]
    value_columns: dict[str, pl.DataType] = {}
    flags: list[tuple[str, int, set]] = []
    if rule.get("flags"):
        flags, _, value_columns = _flags(p, rule["flags"], workflow, records)
    units = [_flagged(row[0], tuple(row[1:]), flags) for row in rows]
    units.sort(key=lambda u: (u.id, u.code))
    return Plan(units, value_columns, records)
