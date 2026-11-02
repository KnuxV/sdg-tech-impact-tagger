"""Lists of labels (contract 2.2): TOML files of ids, keys, names and string fields."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sdg_tech_impact_tagger.errors import ListError

LISTS_DIR = Path(__file__).resolve().parent / "lists"
SHIPPED_LISTS = ("sdg", "adt")

LIST_ID_RE = re.compile(r"[a-z][a-z0-9_]*")
LABEL_ID_RE = re.compile(r"[A-Za-z0-9_-]+")
LIST_KEYS = {"id", "name", "source"}


@dataclass(frozen=True)
class LabelList:
    """A loaded list: its id, name, labels in order, and the file it came from.

    Each label is a dict of strings holding at least `id`, `json_key` and
    `name`; `json_key` defaults to the id. The slug is derived, never stored.
    """

    id: str
    name: str
    labels: tuple[dict[str, str], ...]
    source: str | None = None
    path: Path | None = field(default=None, compare=False)

    @property
    def codes(self) -> list[str]:
        """The label ids in list order."""
        return [label["id"] for label in self.labels]

    def label(self, code: str) -> dict[str, str]:
        """The label of id `code`; `KeyError` when the list has none."""
        for label in self.labels:
            if label["id"] == code:
                return label
        raise KeyError(code)


def slug(code: str) -> str:
    """The derived variable of [OA] adt_pass2.py: the id lower-cased, `_` as `-`."""
    return code.lower().replace("_", "-")


def label_values(label: dict[str, str]) -> dict[str, str]:
    """A label's fields with its slug, the names a format string may use."""
    return {**label, "slug": slug(label["id"])}


def parse_list(data: Any, where: str) -> LabelList:
    """Check a list read from TOML and return it; `ListError` naming `where` otherwise."""
    if not isinstance(data, dict):
        raise ListError(f"{where}: not a TOML table")
    unknown = sorted(set(data) - {"list", "labels"})
    if unknown:
        raise ListError(f"{where}: unknown table {', '.join(unknown)}")
    head = data.get("list")
    if not isinstance(head, dict):
        raise ListError(f"{where}: no [list] table")
    extra = sorted(set(head) - LIST_KEYS)
    if extra:
        raise ListError(f"{where}: unknown [list] key {', '.join(extra)}")
    list_id, name = head.get("id"), head.get("name")
    if not isinstance(list_id, str) or LIST_ID_RE.fullmatch(list_id) is None:
        raise ListError(
            f"{where}: [list].id must match [a-z][a-z0-9_]*, not {list_id!r}"
        )
    if not isinstance(name, str):
        raise ListError(f"{where}: [list].name must be a string")
    source = head.get("source")
    if source is not None and not isinstance(source, str):
        raise ListError(f"{where}: [list].source must be a string")
    raw = data.get("labels")
    if not isinstance(raw, list) or not raw:
        raise ListError(f"{where}: no [[labels]]")
    labels: list[dict[str, str]] = []
    keys: set[str] | None = None
    for number, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            raise ListError(f"{where}: label {number} is not a table")
        bad = sorted(k for k, v in entry.items() if not isinstance(v, str))
        if bad:
            raise ListError(
                f"{where}: label {number} has non-string values: {', '.join(bad)}"
            )
        for required in ("id", "name"):
            if required not in entry:
                raise ListError(f"{where}: label {number} has no {required}")
        if LABEL_ID_RE.fullmatch(entry["id"]) is None:
            raise ListError(f"{where}: label id {entry['id']!r} is not [A-Za-z0-9_-]+")
        label = {"id": entry["id"], "json_key": entry.get("json_key", entry["id"])}
        label.update({k: v for k, v in entry.items() if k not in label})
        found = set(entry) | {"json_key"}
        if keys is None:
            keys = found
        elif found != keys:
            raise ListError(
                f"{where}: label {entry['id']} has another key set than the first"
            )
        labels.append(label)
    for key in ("id", "json_key"):
        values = [label[key] for label in labels]
        repeated = sorted({v for v in values if values.count(v) > 1})
        if repeated:
            raise ListError(f"{where}: repeated {key}: {', '.join(repeated)}")
    return LabelList(id=list_id, name=name, labels=tuple(labels), source=source)


def read_list(path: Path) -> LabelList:
    """Load a list file by path; `ListError` when it is missing, not TOML or does not fit."""
    path = Path(path)
    if not path.is_file():
        raise ListError(f"the list file {path} does not exist")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ListError(f"{path}: not TOML: {exc}") from exc
    loaded = parse_list(data, str(path))
    return LabelList(
        id=loaded.id,
        name=loaded.name,
        labels=loaded.labels,
        source=loaded.source,
        path=path,
    )


def load_list(name_or_path: str | Path) -> LabelList:
    """Load a shipped list by id (`sdg`, `adt`) or any list file by path.

    Produces a `LabelList` whose `labels` keep the file's order. Raises
    `ListError` on an unknown name or a file that does not fit section 2.2.
    """
    if isinstance(name_or_path, str) and name_or_path in SHIPPED_LISTS:
        return read_list(LISTS_DIR / f"{name_or_path}.toml")
    path = Path(name_or_path)
    if not path.exists() and isinstance(name_or_path, str) and "/" not in name_or_path:
        raise ListError(
            f"no shipped list {name_or_path!r}; shipped: {', '.join(SHIPPED_LISTS)}"
        )
    return read_list(path)


def shipped_lists() -> dict[str, LabelList]:
    """The shipped lists, id to list."""
    return {list_id: load_list(list_id) for list_id in SHIPPED_LISTS}
