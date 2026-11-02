"""Readouts (contract section 4): the request each readout sends and how its answer is read.

Four readouts: `score_json`, `letter_logprob`, `letter_text` (layout
`single` or `table`) and `json_object` (form `label_object` or
`impact_pairs_v1`). The kind of call, and so the cache key, is fixed by the
readout (4.1). Reading never raises: an answer that cannot be read is a
parse failure, written as such.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any

import polars as pl
import pydantic

from sdg_tech_impact_tagger.client import Answer
from sdg_tech_impact_tagger.errors import QuestionError
from sdg_tech_impact_tagger.questions import OTHER, AnswerField


class _QuoteMarker:
    """Marks a field of an answer model as a quote, checked against the text."""

    def __repr__(self) -> str:
        return "Quote"


QUOTE = _QuoteMarker()

Quote = Annotated[str, QUOTE]
"""A string field of an answer model that quotes the text (contract 4.5)."""

TABLE_RE = re.compile(r"^=== ([A-Za-z0-9_]+) ===$")

TYPE_SCHEMAS: dict[str, dict[str, Any]] = {
    "string": {"type": "string"},
    "quote": {"type": "string"},
    "boolean": {"type": "boolean"},
    "integer": {"type": "integer"},
    "number": {"type": "number"},
}
DTYPES: dict[str, pl.DataType] = {
    "letter": pl.String(),
    "string": pl.String(),
    "quote": pl.String(),
    "boolean": pl.Boolean(),
    "integer": pl.Int64(),
    "number": pl.Float64(),
}


# --------------------------------------------------------------------------
# label_object items: declared fields or an answer model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemSpec:
    """The fields of a `label_object` item, from `question.toml` or a Pydantic model.

    `fields` is a tuple of (name, type), type one of the declared types;
    `schema` is the `<item>` JSON schema of 4.5; `model` the answer model
    when one is given, used to validate each item.
    """

    fields: tuple[AnswerField, ...]
    schema: dict[str, Any]
    model: type[pydantic.BaseModel] | None = None

    @property
    def quote_fields(self) -> list[str]:
        """The names of the quote fields."""
        return [f.name for f in self.fields if f.type == "quote"]


def declared_item(fields: Sequence[AnswerField]) -> ItemSpec:
    """The item of the declared fields of a question, with its schema (4.5)."""
    properties: dict[str, Any] = {}
    for f in fields:
        if f.type == "letter":
            properties[f.name] = {"type": "string", "enum": list(f.letters)}
        else:
            properties[f.name] = dict(TYPE_SCHEMAS[f.type])
    schema = {
        "type": "object",
        "properties": properties,
        "required": [f.name for f in fields],
        "additionalProperties": False,
    }
    return ItemSpec(fields=tuple(fields), schema=schema)


def model_item(model: type[pydantic.BaseModel]) -> ItemSpec:
    """The item of an answer model; `QuestionError` for a field it cannot type (4.5).

    Each field must be required and have a plain `string`, `boolean`,
    `integer` or `number` schema; a field annotated `Quote` is a quote.
    """
    if not (isinstance(model, type) and issubclass(model, pydantic.BaseModel)):
        raise QuestionError(f"the answer model {model!r} is not a Pydantic model")
    schema = model.model_json_schema()
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields: list[AnswerField] = []
    for name, info in model.model_fields.items():
        key = info.alias or name
        prop = properties.get(key)
        where = f"the field {name} of the answer model {model.__name__}"
        if prop is None or key not in required:
            raise QuestionError(f"{where} is not required")
        if any(
            k in prop for k in ("anyOf", "allOf", "oneOf", "$ref", "default", "items")
        ):
            raise QuestionError(f"{where} has a schema the package cannot type: {prop}")
        kind = prop.get("type")
        if kind not in ("string", "boolean", "integer", "number"):
            raise QuestionError(
                f"{where} has the type {kind!r}, not a string, boolean or number"
            )
        quote = any(item is QUOTE for item in info.metadata)
        if kind == "string":
            fields.append(AnswerField(key, "quote" if quote else "string"))
        else:
            fields.append(AnswerField(key, kind))
    if not fields:
        raise QuestionError(f"the answer model {model.__name__} has no field")
    return ItemSpec(
        fields=tuple(fields),
        schema={**schema, "additionalProperties": False},
        model=model,
    )


def item_response_format(
    name: str, json_keys: Sequence[str], item: dict[str, Any]
) -> dict:
    """The `response_format` of a `label_object` question: one item per label (4.5)."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {key: item for key in json_keys},
                "required": list(json_keys),
                "additionalProperties": False,
            },
        },
    }


def score_response_format(name: str, json_keys: Sequence[str]) -> dict:
    """The `response_format` of a `score_json` question: an integer per label (4.2)."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {key: {"type": "integer"} for key in json_keys},
                "required": list(json_keys),
                "additionalProperties": False,
            },
        },
    }


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------


def read_scores(text: str, json_keys: Sequence[str]) -> dict[str, float] | None:
    """A `score_json` reply as json_key to score in [0, 1], or None when unreadable (4.2)."""
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    keys = set(json_keys)
    scores: dict[str, float] = {}
    for name, value in payload.items():
        if name not in keys:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        try:
            whole = int(value)
        except (ValueError, OverflowError):
            return None
        scores[name] = min(1.0, max(0.0, whole / 100.0))
    if any(key not in scores for key in json_keys):
        return None
    return scores


def answer_entry(
    answer: Answer, extraction: str
) -> tuple[str, tuple[tuple[str, float], ...]] | None:
    """The logprob entry of the answer token: the first, or the one after the last
    `<|message|>` (4.3 step 1); None when there is none."""
    entries = answer.entries
    if extraction == "first_token":
        return entries[0] if entries else None
    markers = [i for i, (token, _) in enumerate(entries) if token == "<|message|>"]
    if markers and markers[-1] + 1 < len(entries):
        return entries[markers[-1] + 1]
    return None


def read_letter(
    answer: Answer, letters: Sequence[str], extraction: str = "first_token"
) -> str:
    """The letter of an answer: the content stripped, or the entry's token; else OTHER."""
    entry = answer_entry(answer, extraction)
    raw = answer.content if answer.content is not None else (entry[0] if entry else "")
    stripped = raw.strip()
    return stripped if stripped in letters else OTHER


def read_logprob(
    answer: Answer, letters: Sequence[str], spelling: str, extraction: str
) -> tuple[str, list[float | None]]:
    """A `letter_logprob` answer: its label and the probability of each letter (4.3)."""
    entry = answer_entry(answer, extraction)
    top: dict[str, float] = {}
    if entry is not None:
        for token, value in entry[1]:
            top[token] = value
    label = read_letter(answer, letters, extraction)
    if spelling == "sum":
        mass = {
            letter: sum(math.exp(v) for k, v in top.items() if k.strip() == letter)
            for letter in letters
        }
    else:
        mass = {
            letter: math.exp(top[letter]) if letter in top else 0.0
            for letter in letters
        }
    total = sum(mass[letter] for letter in letters)
    if total == 0.0:
        return label, [None for _ in letters]
    return label, [mass[letter] / total for letter in letters]


def read_table(
    text: str, table: str, letters: Sequence[str], n_labels: int
) -> list[str] | None:
    """The letters of the work line of a reply's table, in list order, or None (4.4)."""
    current = None
    seen = False
    rows: list[list[str]] = []
    for raw in text.splitlines():
        line = raw.strip().strip("`").strip()
        opened = TABLE_RE.match(line)
        if opened:
            current = opened.group(1)
            seen = seen or current == table
            continue
        if current != table:
            continue
        cells = [cell for cell in re.split(r"[\s|]+", line) if cell]
        if cells and cells[0] == "1":
            rows.append(cells[1:])
    if not seen or len(rows) != 1:
        return None
    found = rows[0]
    if len(found) != n_labels or not set(found) <= set(letters):
        return None
    return found


def _json_span(text: str) -> Any:
    """The JSON value from the first `{` to the last `}` of a text; raises ValueError."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no braces")
    return json.loads(text[start : end + 1])


def _typed(value: Any, f: AnswerField) -> bool:
    if f.type == "letter":
        return isinstance(value, str) and value in f.letters
    if f.type in ("string", "quote"):
        return isinstance(value, str)
    if f.type == "boolean":
        return isinstance(value, bool)
    if f.type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def read_items(
    text: str, json_keys: Sequence[str], item: ItemSpec
) -> dict[str, dict[str, Any]] | None:
    """A `label_object` reply as json_key to field values, or None when one item fails (4.5)."""
    try:
        payload = _json_span(text)
    except ValueError:
        return None
    if not isinstance(payload, dict) or set(payload) != set(json_keys):
        return None
    items: dict[str, dict[str, Any]] = {}
    for key in json_keys:
        raw = payload[key]
        if not isinstance(raw, dict):
            return None
        if item.model is not None:
            try:
                validated = item.model.model_validate(raw)
            except pydantic.ValidationError:
                return None
            dumped = validated.model_dump(by_alias=True)
            items[key] = {f.name: dumped[f.name] for f in item.fields}
            continue
        values = {}
        for f in item.fields:
            if f.name not in raw or not _typed(raw[f.name], f):
                return None
            values[f.name] = raw[f.name]
        items[key] = values
    return items


def quotes_ok(
    values: Mapping[str, Any], quote_fields: Sequence[str], text: str
) -> bool:
    """Every quote that is not blank is a substring of the text (4.5)."""
    return all(
        str(values[name]) in text for name in quote_fields if str(values[name]).strip()
    )


def read_pairs(text: str, n_pairs: int, source: str) -> list[dict[str, Any]] | None:
    """An `impact_pairs_v1` reply as one answer per unit in P order, or None (4.5).

    As [WS] `paper_pass.py:387-416`.
    """
    try:
        payload = _json_span(text)
    except ValueError:
        return None
    if not isinstance(payload, dict) or set(payload) != {"pairs"}:
        return None
    items = payload["pairs"]
    if not isinstance(items, list):
        return None
    names = [o.get("pair") if isinstance(o, dict) else None for o in items]
    if names != [f"P{i}" for i in range(1, n_pairs + 1)]:
        return None
    out = []
    for o in items:
        if any(k not in o for k in ("beneficial", "beneficial_kind", "detrimental")):
            return None
        pos, neg, kind = o["beneficial"], o["detrimental"], o["beneficial_kind"]
        if pos not in ("Y", "N") or neg not in ("Y", "N"):
            return None
        if (pos == "Y" and kind not in ("outcome", "utility")) or (
            pos == "N" and kind != "none"
        ):
            return None
        ok = all(
            isinstance(o.get(f"{q}_quote"), str)
            and o[f"{q}_quote"].strip() != ""
            and o[f"{q}_quote"] in source
            for q, a in (("beneficial", pos), ("detrimental", neg))
            if a == "Y"
        )
        out.append(
            {
                "pos_label": pos,
                "neg_label": neg,
                "beneficial_kind": kind,
                "quotes_ok": ok,
            }
        )
    return out
