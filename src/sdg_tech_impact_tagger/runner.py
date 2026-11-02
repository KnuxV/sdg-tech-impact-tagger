"""The pass runner (contract 6.6 to 6.9, 8, 9 and 10.1): chunks, claims, combine, records.

`run` takes a checked workflow and asks each (pass, model) its units, in
chunks a worker claims, answered in sub-chunks with attempts, then combines
the chunks into the output table once every planned chunk is on disk. Each
(pass, model) keeps `run.json` (what the run is), `manifest.json` (what was
done) and one call log per worker.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import threading
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import pydantic

from sdg_tech_impact_tagger.blocks import file_sha256, sha12
from sdg_tech_impact_tagger.client import Answer, Client, Outcome, Request
from sdg_tech_impact_tagger.errors import (
    CombineError,
    IncompleteRun,
    LLMCallError,
    ManifestMismatch,
    TextsError,
    WorkflowError,
)
from sdg_tech_impact_tagger.questions import OTHER, Question
from sdg_tech_impact_tagger.readouts import (
    DTYPES,
    ItemSpec,
    declared_item,
    item_response_format,
    model_item,
    quotes_ok,
    read_items,
    read_letter,
    read_logprob,
    read_pairs,
    read_scores,
    read_table,
    score_response_format,
)
from sdg_tech_impact_tagger.units import Plan, Unit, plan_units
from sdg_tech_impact_tagger.workflow import ModelEntry, Pass, PassModel, Workflow

WORKER_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_CHUNKS = 99_999
CALL_COLUMNS = ("model", "model_served", "system_fingerprint", "prompt_id", "run_id")


def package_version() -> str:
    """The installed version of the package, or `unknown`."""
    try:
        return importlib.metadata.version("sdg-tech-impact-tagger")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


@dataclass
class RunResult:
    """What a (pass, model) did in one invocation ([OA] `llm_passes.py:1050-1068`).

    `units` and `chunks` are counts; `written`, `skipped_on_disk`,
    `skipped_claimed` and `missing` list chunk indices; `output` is the path
    of the output table, written or not.
    """

    pass_id: str
    model: str
    units: int
    chunks: int
    written: list[int]
    skipped_on_disk: list[int]
    skipped_claimed: list[int]
    missing: list[int]
    output_written: bool
    output: Path


def frame_digest(rows: Sequence[Sequence[Any]]) -> str:
    """Contract 6.7: the hex sha256 of the rows as JSON lists joined by newlines."""
    text = "\n".join(json.dumps(list(row), ensure_ascii=False) for row in rows)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


# --------------------------------------------------------------------------
# the texts table (2.1)
# --------------------------------------------------------------------------


def load_texts(
    workflow: Workflow,
    texts: pl.DataFrame | str | Path | None,
    fields: Sequence[str],
) -> pl.DataFrame:
    """The texts table, checked, its id column renamed `id` (contract 2.1).

    `texts` overrides `[run].texts`; a path given here is read against the
    current directory. Raises `TextsError` when there are none, or on a
    missing or non-string id column, null or empty ids, repeated ids, or a
    field in `fields` missing or not `String` or `Null`.
    """
    if texts is None:
        if workflow.texts is None:
            raise TextsError(
                "no texts: give the texts argument (--texts) or [run].texts in the workflow"
            )
        texts = workflow.texts
    if isinstance(texts, pl.DataFrame):
        frame = texts
    else:
        path = Path(texts)
        if not path.is_file():
            raise TextsError(f"the texts file {path} does not exist")
        try:
            frame = pl.read_parquet(path)
        except (pl.exceptions.PolarsError, OSError) as exc:
            raise TextsError(
                f"the texts file {path} cannot be read as parquet: {exc}"
            ) from exc
    id_column = workflow.id_column
    if id_column not in frame.columns:
        raise TextsError(f"the texts have no id column {id_column!r}")
    if frame.schema[id_column] != pl.String:
        raise TextsError(
            f"the id column {id_column!r} is {frame.schema[id_column]}, not String"
        )
    ids = frame[id_column]
    empty = ids.null_count() + int((ids == "").sum())
    if empty:
        raise TextsError(f"{empty} works have a null or empty id")
    counts = Counter(ids.to_list())
    repeated = [work for work in ids.to_list() if counts[work] > 1]
    if repeated:
        distinct = len({*repeated})
        raise TextsError(f"{distinct} ids are repeated, the first {repeated[0]!r}")
    for name in fields:
        if name not in frame.columns:
            raise TextsError(f"the texts have no field {name!r}")
        if frame.schema[name] not in (pl.String, pl.Null):
            raise TextsError(f"the field {name!r} is {frame.schema[name]}, not String")
    if id_column != "id":
        frame = frame.drop("id", strict=False).rename({id_column: "id"})
    return frame


# --------------------------------------------------------------------------
# what a pass writes: the columns of its table
# --------------------------------------------------------------------------


def has_code(question: Question) -> bool:
    """Whether the rows carry a `code` column."""
    return question.level != "work" or question.rows_per_label


def output_schema(
    question: Question, value_columns: Mapping[str, pl.DataType], item: ItemSpec | None
) -> dict[str, pl.DataType]:
    """The columns of a pass's table, in order, with their dtypes (8.2)."""
    schema: dict[str, pl.DataType] = {"id": pl.String()}
    if has_code(question):
        schema["code"] = pl.String()
    if question.level == "work x list x list":
        schema[question.lists["a"]] = pl.String()
        schema[question.lists["b"]] = pl.String()
    schema.update(value_columns)
    schema["repeat"] = pl.Int64()
    for name in CALL_COLUMNS:
        schema[name] = pl.String()
    schema.update(readout_columns(question, item))
    return schema


def readout_columns(
    question: Question, item: ItemSpec | None
) -> dict[str, pl.DataType]:
    """The readout columns of a question (8.2)."""
    f64, i64, boolean, string = pl.Float64(), pl.Int64(), pl.Boolean(), pl.String()
    tokens = {"tokens_in": i64, "tokens_out": i64}
    readout = question.readout
    if readout == "score_json":
        return {"score": f64, **tokens, "parse_failure": boolean}
    if readout == "json_object":
        if question.spec.form == "impact_pairs_v1":
            return {
                "pos_label": string,
                "neg_label": string,
                "beneficial_kind": string,
                "quotes_ok": boolean,
                "n_pairs": i64,
                "retried": boolean,
                **tokens,
                "parse_failure": boolean,
            }
        assert item is not None
        columns: dict[str, pl.DataType] = {f.name: DTYPES[f.type] for f in item.fields}
        if item.quote_fields:
            columns["quotes_ok"] = boolean
        return {**columns, "retried": boolean, **tokens, "parse_failure": boolean}
    probs = [f"p_{letter.lower()}" for letter in question.spec.letters]
    sides = question.side_names
    if not sides:
        if readout == "letter_logprob":
            middle: dict[str, pl.DataType] = {p: f64 for p in probs}
        else:
            middle = {"retried": boolean}
        return {"label": string, **middle, **tokens, "parse_failure": boolean}
    columns = {f"{s}_label": string for s in sides}
    for s in sides:
        if readout == "letter_logprob":
            columns.update({f"{s}_{p}": f64 for p in probs})
        else:
            columns[f"{s}_retried"] = boolean
    for s in sides:
        columns[f"{s}_tokens_in"] = i64
        columns[f"{s}_tokens_out"] = i64
    return {**columns, **tokens, "parse_failure": boolean}


# --------------------------------------------------------------------------
# asking: the requests of a (pass, model) and the reading of their answers
# --------------------------------------------------------------------------


@dataclass
class Job:
    """The calls of one group of units for one repeat: one call, or one per side."""

    units: list[Unit]
    repeat: int
    requests: list[Request]
    work: dict[str, str | None]


class Asker:
    """Builds the requests of one (pass, model) and reads their answers into rows.

    Consumes the pass, the model entry, its resolved settings and the item
    of a `label_object` question; produces `Request`s (4.1, 6.3, 6.5), the
    run id record (3.6) and the rows of the table (8.2).
    """

    def __init__(
        self, p: Pass, entry: ModelEntry, settings: PassModel, item: ItemSpec | None
    ) -> None:
        self.p = p
        self.q = p.question
        self.entry = entry
        self.settings = settings
        self.item = item
        q = self.q
        self.json_keys = (
            [label["json_key"] for label in q.label_lists["a"].labels]
            if ("a" in q.label_lists)
            else []
        )
        self.codes = q.label_lists["a"].codes if "a" in q.label_lists else []
        readout = q.readout
        single = readout == "letter_text" and q.spec.layout == "single"
        self.kind = "single_token" if readout == "letter_logprob" or single else "chat"
        self.response_format: dict[str, Any] | None = None
        if readout == "score_json":
            self.response_format = score_response_format(
                q.spec.schema_name, self.json_keys
            )
        elif (
            readout == "json_object" and q.spec.form == "label_object" and q.spec.schema
        ):
            assert item is not None
            self.response_format = item_response_format(
                q.spec.schema_name, self.json_keys, item.schema
            )
        if readout == "letter_logprob":
            self.top_logprobs: int | None = settings.top_logprobs
        elif single:
            self.top_logprobs = 0
        else:
            self.top_logprobs = None
        # The keyed extra body: reasoning fields, the readout's added field,
        # then the model's extra_body, chat_template_kwargs merged key by key.
        keyed: dict[str, Any] = dict(entry.reasoning_fields())
        if readout in ("letter_text", "json_object"):
            keyed["logprobs"] = False
        for name, value in entry.extra_body.items():
            if name == "chat_template_kwargs" and isinstance(keyed.get(name), dict):
                keyed[name] = {**keyed[name], **value}
            else:
                keyed[name] = value
        self.keyed_extra = keyed
        self.retry = (
            settings.retry_max_tokens
            if readout in ("letter_text", "json_object")
            else None
        )

    # -- the run id (3.6) --------------------------------------------------

    def run_record(self) -> dict[str, Any]:
        """The 19-key record the run id hashes."""
        q, readout = self.q, self.q.readout
        letters = (
            list(q.spec.letters)
            if readout in ("letter_logprob", "letter_text")
            else None
        )
        label_object = readout == "json_object" and q.spec.form == "label_object"
        return {
            "prompt_ids": dict(self.p.prompt_ids),
            "readout": readout,
            "layout": q.spec.layout if readout == "letter_text" else None,
            "form": q.spec.form if readout == "json_object" else None,
            "letters": letters,
            "answer_schema": self.item.schema if label_object and self.item else None,
            "model": self.entry.model,
            "seed": self.entry.seed,
            "temperature": self.entry.temperature,
            "max_tokens": self.settings.max_tokens,
            "retry_max_tokens": self.retry,
            "top_logprobs": self.top_logprobs,
            "response_format": self.response_format,
            "extra_body": self.keyed_extra,
            "reasoning": self.entry.reasoning,
            "spelling": self.p.spelling if readout == "letter_logprob" else None,
            "extraction": self.entry.extraction
            if readout == "letter_logprob"
            else None,
            "budget_rule": self.p.budget_rule if self.retry is not None else None,
            "null_text": self.p.null_text,
        }

    def run_id(self) -> str:
        """`run-` and the sha12 of the run id record."""
        blob = json.dumps(self.run_record(), sort_keys=True, separators=(",", ":"))
        return "run-" + sha12(blob)

    # -- requests ----------------------------------------------------------

    def request(
        self, system: str, user: str, repeat: int, unreadable: Callable[[Answer], bool]
    ) -> Request:
        """One call: key fields (6.5) and wire body (4.1, 6.3)."""
        e, s = self.entry, self.settings
        if self.kind == "chat":
            fields: dict[str, Any] = {
                "model": e.model,
                "system": system,
                "user": user,
                "seed": e.seed,
                "temperature": e.temperature,
                "max_tokens": s.max_tokens,
                "response_format": self.response_format,
                "extra_body": self.keyed_extra,
                "kind": "chat",
            }
        else:
            fields = {
                "model": e.model,
                "system": system,
                "user": user,
                "seed": e.seed,
                "temperature": e.temperature,
                "max_tokens": s.max_tokens,
                "top_logprobs": self.top_logprobs,
                "extra_body": self.keyed_extra,
            }
        if repeat >= 2:
            fields["repeat"] = repeat
        payload: dict[str, Any] = {
            "model": e.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": e.temperature,
            "max_tokens": s.max_tokens,
            "seed": e.seed,
        }
        if self.kind == "single_token":
            payload["logprobs"] = True
            payload["top_logprobs"] = self.top_logprobs
        elif self.response_format is not None:
            payload["response_format"] = self.response_format
        payload.update(self.keyed_extra)
        return Request(
            kind=self.kind,
            fields=fields,
            payload=payload,
            repeat=repeat,
            unreadable=unreadable,
        )

    def jobs(
        self, groups: Sequence[list[Unit]], works: Mapping[str, dict]
    ) -> list[Job]:
        """The jobs of groups of units, repeats of a group adjacent (contract 5)."""
        q, null_text = self.q, self.p.null_text
        jobs = []
        for group in groups:
            work = works[group[0].id]
            if q.per_call == "work":
                units = [u.codes for u in group]
                calls = q.render(work, units, null_text=null_text)
                order = q.assembly_order(units)
                by_codes = {u.codes: u for u in group}
                group = [by_codes[codes] for codes in order]
            elif q.level == "work":
                calls = q.render(work, [], null_text=null_text)
            else:
                calls = q.render(work, [group[0].codes], null_text=null_text)
            unreadable = self.unreadable(len(group), q.joined_text(work, null_text))
            for repeat in range(1, self.p.repeats + 1):
                requests = [self.request(s, u, repeat, unreadable) for s, u in calls]
                jobs.append(Job(list(group), repeat, requests, work))
        return jobs

    # -- reading -----------------------------------------------------------

    def unreadable(self, n_units: int, joined: str) -> Callable[[Answer], bool]:
        """Whether an answer cannot be read by the readout (the call log, 4.4)."""
        q = self.q
        readout = q.readout
        if readout == "score_json":
            return lambda a: read_scores(a.text, self.json_keys) is None
        if readout == "letter_logprob":
            extraction = self.entry.extraction
            return lambda a: read_letter(a, q.spec.letters, extraction) == OTHER
        if readout == "letter_text" and q.spec.layout == "table":
            n = len(self.codes)
            return lambda a: read_table(a.text, q.spec.table, q.spec.letters, n) is None
        if readout == "letter_text":
            return lambda a: read_letter(a, q.spec.letters) == OTHER
        if q.spec.form == "impact_pairs_v1":
            return lambda a: read_pairs(a.text, n_units, joined) is None
        item = self.item
        assert item is not None
        return lambda a: read_items(a.text, self.json_keys, item) is None

    def spent(self, answer: Answer) -> bool:
        """Whether an answer used its budget, by the pass's budget rule (4.4)."""
        rule, budget = self.p.budget_rule, self.settings.max_tokens
        by_length = answer.finish_reason == "length"
        by_tokens = answer.tokens_out >= budget
        if rule == "tokens":
            return by_tokens
        if rule == "length":
            return by_length
        return by_length or by_tokens

    def rows(
        self,
        job: Job,
        answers: list[Answer],
        retried: list[bool],
        run_id: str,
    ) -> list[dict[str, Any]]:
        """The rows of a job's answers (8.2)."""
        q = self.q
        readout = q.readout
        served = _joined([a.model_served for a in answers])
        fingerprint = _joined([a.system_fingerprint for a in answers])

        def head(unit: Unit, code: str | None) -> dict[str, Any]:
            row: dict[str, Any] = {"id": unit.id}
            if has_code(q):
                row["code"] = code
            if q.level == "work x list x list":
                row[q.lists["a"]] = unit.codes[0]
                row[q.lists["b"]] = unit.codes[1]
            row.update(dict(unit.values))
            row["repeat"] = job.repeat
            first = (code or "").split("|")[0]
            prompt_id = self.p.prompt_ids.get(first, self.p.prompt_ids.get(""))
            row.update(
                model=self.entry.model,
                model_served=served,
                system_fingerprint=fingerprint,
                prompt_id=prompt_id,
                run_id=run_id,
            )
            return row

        if q.rows_per_label:
            return self._label_rows(job, answers[0], retried[0], head)
        if readout == "json_object":
            return self._pair_rows(job, answers[0], retried[0], head)
        unit = job.units[0]
        row = head(unit, unit.code if has_code(q) else None)
        sides = q.side_names
        if not sides:
            row.update(self._letter(answers[0], retried[0], ""))
            row.update(tokens_in=answers[0].tokens_in, tokens_out=answers[0].tokens_out)
            row["parse_failure"] = row["label"] == OTHER
            return [row]
        parts = [
            self._letter(a, r, f"{s}_")
            for s, a, r in zip(sides, answers, retried, strict=True)
        ]
        for s, part in zip(sides, parts, strict=True):
            row[f"{s}_label"] = part[f"{s}_label"]
        for part in parts:
            row.update({k: v for k, v in part.items() if not k.endswith("_label")})
        for s, a in zip(sides, answers, strict=True):
            row[f"{s}_tokens_in"] = a.tokens_in
            row[f"{s}_tokens_out"] = a.tokens_out
        row["tokens_in"] = sum(a.tokens_in for a in answers)
        row["tokens_out"] = sum(a.tokens_out for a in answers)
        row["parse_failure"] = any(row[f"{s}_label"] == OTHER for s in sides)
        return [row]

    def _letter(self, answer: Answer, retried: bool, prefix: str) -> dict[str, Any]:
        q = self.q
        letters = q.spec.letters
        if q.readout == "letter_logprob":
            label, probs = read_logprob(
                answer, letters, self.p.spelling or "sum", self.entry.extraction
            )
            out: dict[str, Any] = {f"{prefix}label": label}
            for letter, prob in zip(letters, probs, strict=True):
                out[f"{prefix}p_{letter.lower()}"] = prob
            return out
        return {
            f"{prefix}label": read_letter(answer, letters),
            f"{prefix}retried": retried,
        }

    def _label_rows(
        self, job: Job, answer: Answer, retried: bool, head: Callable
    ) -> list[dict[str, Any]]:
        q = self.q
        unit = job.units[0]
        tokens = {"tokens_in": answer.tokens_in, "tokens_out": answer.tokens_out}
        rows = []
        if q.readout == "score_json":
            scores = read_scores(answer.text, self.json_keys)
            for code, key in zip(self.codes, self.json_keys, strict=True):
                row = head(unit, code)
                row["score"] = 0.0 if scores is None else scores[key]
                row.update(tokens)
                row["parse_failure"] = scores is None
                rows.append(row)
            return rows
        if q.readout == "letter_text":
            found = read_table(
                answer.text, q.spec.table, q.spec.letters, len(self.codes)
            )
            for n, code in enumerate(self.codes):
                row = head(unit, code)
                row["label"] = OTHER if found is None else found[n]
                row["retried"] = retried
                row.update(tokens)
                row["parse_failure"] = found is None
                rows.append(row)
            return rows
        item = self.item
        assert item is not None
        items = read_items(answer.text, self.json_keys, item)
        joined = q.joined_text(job.work, self.p.null_text)
        for code, key in zip(self.codes, self.json_keys, strict=True):
            row = head(unit, code)
            values = None if items is None else items[key]
            for f in item.fields:
                value = None if values is None else values[f.name]
                if value is not None and f.type == "number":
                    value = float(value)
                row[f.name] = value
            if item.quote_fields:
                row["quotes_ok"] = (
                    None
                    if values is None
                    else quotes_ok(values, item.quote_fields, joined)
                )
            row["retried"] = retried
            row.update(tokens)
            row["parse_failure"] = items is None
            rows.append(row)
        return rows

    def _pair_rows(
        self, job: Job, answer: Answer, retried: bool, head: Callable
    ) -> list[dict[str, Any]]:
        joined = self.q.joined_text(job.work, self.p.null_text)
        n = len(job.units)
        pairs = read_pairs(answer.text, n, joined)
        rows = []
        for index, unit in enumerate(job.units):
            row = head(unit, unit.code)
            if pairs is None:
                row.update(
                    pos_label=OTHER,
                    neg_label=OTHER,
                    beneficial_kind=None,
                    quotes_ok=False,
                )
            else:
                row.update(pairs[index])
            row.update(
                n_pairs=n,
                retried=retried,
                tokens_in=answer.tokens_in,
                tokens_out=answer.tokens_out,
                parse_failure=pairs is None,
            )
            rows.append(row)
        return rows

    def expected_keys(self, units: Sequence[Unit]) -> list[tuple[str, str | None, int]]:
        """The (id, code, repeat) of the rows the units give."""
        keys = []
        for unit in units:
            for repeat in range(1, self.p.repeats + 1):
                if self.q.rows_per_label:
                    keys.extend((unit.id, code, repeat) for code in self.codes)
                else:
                    keys.append(
                        (unit.id, unit.code if has_code(self.q) else None, repeat)
                    )
        return keys


def _joined(values: Sequence[str | None]) -> str | None:
    """The distinct non-null values, sorted, joined with `|`; null when none (8.2)."""
    found = sorted({v for v in values if v is not None})
    return "|".join(found) if found else None


# --------------------------------------------------------------------------
# chunks (6.6)
# --------------------------------------------------------------------------


def groups_of(question: Question, units: Sequence[Unit]) -> list[list[Unit]]:
    """The units in call groups: one unit each, or a work's units with `per_call = "work"`."""
    if question.per_call != "work":
        return [[unit] for unit in units]
    by_work: dict[str, list[Unit]] = {}
    for unit in units:
        by_work.setdefault(unit.id, []).append(unit)
    return list(by_work.values())


def cut(groups: Sequence[list[Unit]], size: int) -> list[list[list[Unit]]]:
    """Consecutive groups cut into parts closing once they hold `size` units or more."""
    parts: list[list[list[Unit]]] = []
    current: list[list[Unit]] = []
    count = 0
    for group in groups:
        current.append(group)
        count += len(group)
        if count >= size:
            parts.append(current)
            current, count = [], 0
    if current:
        parts.append(current)
    return parts


class CallLog:
    """The call log of a worker: one JSON line per call made or read (section 9)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def __call__(self, request: Request, outcome: Outcome, duration_ms: float) -> None:
        answer = outcome.answer
        line = {
            "cache_key": outcome.key,
            "kind": request.kind,
            "cached": outcome.cached,
            "repeat": request.repeat,
            "retry": request.retry,
            "model_served": answer.model_served,
            "system_fingerprint": answer.system_fingerprint,
            "finish_reason": answer.finish_reason,
            "tokens_in": answer.tokens_in,
            "tokens_out": answer.tokens_out,
            "duration_ms": round(duration_ms, 3),
            "parse_failure": bool(request.unreadable(answer)),
        }
        text = json.dumps(line, ensure_ascii=False) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(text)


# --------------------------------------------------------------------------
# one (pass, model)
# --------------------------------------------------------------------------


@dataclass
class PassRun:
    """Everything one (pass, model) needs: the plan, its asker, its paths and records."""

    workflow: Workflow
    p: Pass
    model: str
    texts: pl.DataFrame
    works: dict[str, dict[str, str | None]]
    plan: Plan
    asker: Asker
    run_id: str
    schema: dict[str, pl.DataType]
    chunks: list[list[list[Unit]]] = field(default_factory=list)

    @property
    def entry(self) -> ModelEntry:
        return self.workflow.models[self.model]

    @property
    def work_dir(self) -> Path:
        return self.workflow.work_dir(self.p.id, self.model)

    @property
    def chunk_dir(self) -> Path:
        return self.work_dir / "chunks"

    @property
    def output(self) -> Path:
        return self.workflow.output_of(self.p.id, self.model)

    def chunk_path(self, index: int, suffix: str = "parquet") -> Path:
        return self.chunk_dir / f"chunk_{index:05d}.{suffix}"

    def record(self) -> dict[str, Any]:
        """The `run.json` record (6.7)."""
        q = self.p.question
        fields = list(q.text_fields)
        null_text = self.p.null_text
        rows = [
            [work, *(null_text if row[f] is None else row[f] for f in fields)]
            for work, row in self.works.items()
        ]
        units = self.plan.units
        if q.level == "work":
            unit_rows = [[u.id] for u in units]
        else:
            unit_rows = [[u.id, u.code] for u in units]
        record: dict[str, Any] = {
            "pass": self.p.id,
            "question": q.name,
            "model_entry": self.model,
            "model": self.entry.model,
        }
        if q.per_label:
            record["prompt_ids"] = dict(self.p.prompt_ids)
        else:
            record["prompt_id"] = self.p.prompt_ids[""]
        record.update(
            run_id=self.run_id,
            texts_sha256=frame_digest(rows),
            units=len(units),
            units_sha256=frame_digest(unit_rows),
            unit_rule=self.p.units,
            chunk_size=self.p.chunk_size,
            repeats=self.p.repeats,
        )
        return json.loads(json.dumps(record))

    def check_record(self, create: bool) -> None:
        """Compare `run.json` with this run, or create it (6.7)."""
        path = self.work_dir / "run.json"
        new = self.record()
        if path.is_file():
            stored = json.loads(path.read_text(encoding="utf-8"))
            lines = sorted(
                f"{key}: {stored.get(key)!r} on disk, {new.get(key)!r} now"
                for key in sorted(set(stored) | set(new))
                if stored.get(key) != new.get(key)
            )
            if lines:
                raise ManifestMismatch(
                    f"{path} records another run of pass {self.p.id}, model {self.model}:\n"
                    + "\n".join(lines)
                )
            return
        if not create:
            raise ManifestMismatch(f"combine_only needs {path}, which does not exist")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        text = json.dumps(new, indent=2, sort_keys=True) + "\n"
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            self.check_record(create=False)
            return
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)

    # -- answering ---------------------------------------------------------

    def answer_sub_chunk(self, client: Client, groups: list[list[Unit]]) -> list[dict]:
        """Ask a sub-chunk's calls in one batch, then its budget retries in one more."""
        jobs = self.asker.jobs(groups, self.works)
        requests = [r for job in jobs for r in job.requests]
        outcomes = client.batch(requests)
        answers = [o.answer for o in outcomes]
        retried = [False] * len(requests)
        retry = self.asker.retry
        if retry is not None:
            again = [
                n
                for n, (request, answer) in enumerate(
                    zip(requests, answers, strict=True)
                )
                if request.unreadable(answer) and self.asker.spent(answer)
            ]
            if again:
                second = client.batch([requests[n].with_budget(retry) for n in again])
                for n, outcome in zip(again, second, strict=True):
                    answers[n] = outcome.answer
                    retried[n] = True
        rows: list[dict] = []
        at = 0
        for job in jobs:
            width = len(job.requests)
            rows.extend(
                self.asker.rows(
                    job, answers[at : at + width], retried[at : at + width], self.run_id
                )
            )
            at += width
        return rows

    def answer_chunk(self, client: Client, chunk: list[list[Unit]]) -> pl.DataFrame:
        """Answer a chunk in sub-chunks, asking again the failed ones (6.6)."""
        subs = cut(chunk, self.p.sub_chunk)
        done: dict[int, list[dict]] = {}
        pending = list(range(len(subs)))
        failures: list[tuple[int, BaseException]] = []
        for _ in range(self.p.attempts):
            failures = []
            for n in pending:
                try:
                    done[n] = self.answer_sub_chunk(client, subs[n])
                except LLMCallError as exc:
                    failures.append((n, exc))
            pending = [n for n, _ in failures]
            if not pending:
                break
        if pending:
            last = failures[-1][1]
            raise LLMCallError(
                f"pass {self.p.id}, model {self.model}: {len(pending)} sub-chunks still fail "
                f"after {self.p.attempts} attempts (last: {last})",
                failures=failures,
            ) from last
        rows = [row for n in range(len(subs)) for row in done[n]]
        names = list(self.schema)
        return pl.DataFrame(
            [tuple(row[name] for name in names) for row in rows],
            schema=self.schema,
            orient="row",
        )

    def visit(
        self, client: Client | None, worker: str, reverse: bool
    ) -> tuple[list[int], list[int], list[int]]:
        """Visit the chunks as a worker: skip the done and the claimed, answer the rest."""
        written: list[int] = []
        on_disk: list[int] = []
        claimed: list[int] = []
        indices = list(range(1, len(self.chunks) + 1))
        if reverse:
            indices.reverse()
        for index in indices:
            if self.chunk_path(index).exists():
                on_disk.append(index)
                continue
            if not self._claim(index, worker):
                claimed.append(index)
                continue
            assert client is not None
            frame = self.answer_chunk(client, self.chunks[index - 1])
            partial = self.chunk_path(index, f"{worker}.partial")
            frame.write_parquet(partial)
            os.replace(partial, self.chunk_path(index))
            self.chunk_path(index, "claim").unlink(missing_ok=True)
            written.append(index)
        return written, on_disk, claimed

    def _claim(self, index: int, worker: str) -> bool:
        path = self.chunk_path(index, "claim")
        self.chunk_dir.mkdir(parents=True, exist_ok=True)
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                holder = path.read_text(encoding="utf-8").strip()
            except OSError:
                return False
            return holder == worker
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
            out.write(worker)
        return True

    # -- combine (6.8) -----------------------------------------------------

    def combine(self) -> pl.DataFrame:
        """Check every chunk and write the sorted output table; return it."""
        planned = {self.chunk_path(n).name for n in range(1, len(self.chunks) + 1)}
        missing = [
            n
            for n in range(1, len(self.chunks) + 1)
            if not self.chunk_path(n).is_file()
        ]
        if missing:
            raise IncompleteRun(
                f"pass {self.p.id}, model {self.model}: {len(missing)} planned chunks are "
                f"missing, the lowest {missing[0]}"
            )
        stray = sorted(
            path.name
            for path in self.chunk_dir.glob("chunk_*.parquet")
            if path.name not in planned
        )
        if stray:
            raise CombineError(
                f"{self.chunk_dir}: chunks outside the plan: {', '.join(stray)}"
            )
        expected_schema = list(self.schema.items())
        frames = []
        code = "code" in self.schema
        for n, chunk in enumerate(self.chunks, start=1):
            path = self.chunk_path(n)
            frame = pl.read_parquet(path)
            if list(frame.schema.items()) != expected_schema:
                raise CombineError(f"{path} does not have the output schema")
            keys = list(
                zip(
                    frame["id"].to_list(),
                    frame["code"].to_list() if code else [None] * frame.height,
                    frame["repeat"].to_list(),
                    strict=True,
                )
            )
            expected = set(self.asker.expected_keys([u for g in chunk for u in g]))
            counts = Counter(keys)
            lacking = len(expected - set(counts))
            unexpected = len(set(counts) - expected)
            repeated = sum(1 for k, c in counts.items() if c > 1)
            if lacking or unexpected or repeated:
                raise CombineError(
                    f"{path}: {lacking} rows missing, {unexpected} unexpected, "
                    f"{repeated} repeated"
                )
            ids = self.p.prompt_ids
            wrong = 0
            for row_code, model, prompt_id, run_id in zip(
                frame["code"].to_list() if code else [None] * frame.height,
                frame["model"].to_list(),
                frame["prompt_id"].to_list(),
                frame["run_id"].to_list(),
                strict=True,
            ):
                first = (row_code or "").split("|")[0]
                want = ids.get(first, ids.get(""))
                if (
                    model != self.entry.model
                    or prompt_id != want
                    or run_id != self.run_id
                ):
                    wrong += 1
            if wrong:
                raise CombineError(
                    f"{path}: {wrong} rows of another model, prompt id or run id"
                )
            frames.append(frame)
        table = pl.concat(frames) if frames else pl.DataFrame(schema=self.schema)
        table = table.sort([c for c in ("id", "code", "repeat") if c in self.schema])
        partial = self.output.with_name(self.output.name + ".partial")
        self.output.parent.mkdir(parents=True, exist_ok=True)
        table.write_parquet(partial)
        os.replace(partial, self.output)
        return table

    # -- the manifest (9) --------------------------------------------------

    def write_manifest(self, table: pl.DataFrame, replay: bool) -> None:
        """Write `manifest.json` from the table and the call logs."""
        lines = []
        for path in sorted((self.work_dir / "calls").glob("*.jsonl")):
            for raw in path.read_text(encoding="utf-8").splitlines():
                if raw.strip():
                    lines.append(json.loads(raw))
        q = self.p.question
        retried_columns = [
            c for c in table.columns if c == "retried" or c.endswith("_retried")
        ]
        retried = (
            table.select(pl.any_horizontal(retried_columns)).to_series().sum()
            if retried_columns
            else 0
        )
        counts = {
            "units": len(self.plan.units),
            "rows": table.height,
            "parse_failures": int(table["parse_failure"].sum()),
            "retried": int(retried),
            "calls": len(lines),
            "cached_calls": sum(1 for line in lines if line["cached"]),
            "fresh_calls": sum(1 for line in lines if not line["cached"]),
            "distinct_keys": len({line["cache_key"] for line in lines}),
            "tokens_in": sum(line["tokens_in"] for line in lines),
            "tokens_out": sum(line["tokens_out"] for line in lines),
        }
        changes = []
        first = None
        seen = set()
        for line in lines:
            pair = (line["model_served"], line["system_fingerprint"])
            if first is None:
                first = pair
            elif pair != first and pair not in seen:
                seen.add(pair)
                changes.append(
                    {
                        "first_model_served": first[0],
                        "first_system_fingerprint": first[1],
                        "model_served": pair[0],
                        "system_fingerprint": pair[1],
                    }
                )
        started = (self.work_dir / "run.json").stat().st_mtime
        settings = self.p.settings[self.model]
        manifest: dict[str, Any] = {
            "package_version": package_version(),
            "python_version": platform.python_version(),
            "started_at": dt.datetime.fromtimestamp(started, dt.UTC).isoformat(),
            "combined_at": _now(),
            "workflow": self.workflow.name,
            "workflow_sha256": self.workflow.sha256,
            "pass": self.p.id,
            "question": q.name,
            "question_status": q.status,
            "question_files": dict(q.files_read),
            "lists": {
                listed.id: file_sha256(listed.path)
                for listed in q.label_lists.values()
                if listed.path is not None
            },
            "run_id": self.run_id,
            "model": self.entry.record(),
            "endpoint": self.entry.endpoint,
            "cache_dir": str(self.workflow.cache_dir_of(self.p, self.model)),
            "replay": replay,
            "settings": {
                "max_tokens": settings.max_tokens,
                "retry_max_tokens": settings.retry_max_tokens,
                "top_logprobs": settings.top_logprobs,
                "timeout_s": settings.timeout_s,
                "spelling": self.p.spelling,
                "budget_rule": self.p.budget_rule,
                "null_text": self.p.null_text,
                "repeats": self.p.repeats,
                "chunk_size": self.p.chunk_size,
                "sub_chunk": self.p.sub_chunk,
                "attempts": self.p.attempts,
            },
            "texts_sha256": self.record()["texts_sha256"],
            "unit_rule": self.p.units,
            "sources": self.plan.sources,
            "counts": counts,
            "models_served": dict(
                Counter(line["model_served"] or "" for line in lines)
            ),
            "system_fingerprints": dict(
                Counter(line["system_fingerprint"] or "" for line in lines)
            ),
            "model_changes": changes,
        }
        if q.per_label:
            manifest["prompt_ids"] = dict(self.p.prompt_ids)
        else:
            manifest["prompt_id"] = self.p.prompt_ids[""]
        text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        path = self.work_dir / "manifest.json"
        partial = path.with_name("manifest.json.partial")
        partial.write_text(text, encoding="utf-8", newline="\n")
        os.replace(partial, path)


def prepare(
    workflow: Workflow,
    p: Pass,
    model: str,
    texts: pl.DataFrame,
    item: ItemSpec | None,
) -> PassRun:
    """Plan one (pass, model): its units, chunks, asker, run id and schema; no write.

    Raises `UnitsError` when the unit rule cannot build its units.
    """
    question = p.question
    fields = list(question.text_fields)
    works = {
        row["id"]: {f: row[f] for f in fields}
        for row in texts.select("id", *fields).iter_rows(named=True)
    }
    plan = plan_units(workflow, p, model, list(works))
    if question.readout == "json_object" and question.spec.form == "label_object":
        item = item or declared_item(question.spec.fields)
    else:
        item = None
    asker = Asker(p, workflow.models[model], p.settings[model], item)
    run = PassRun(
        workflow=workflow,
        p=p,
        model=model,
        texts=texts,
        works=works,
        plan=plan,
        asker=asker,
        run_id=asker.run_id(),
        schema=output_schema(question, plan.value_columns, item),
    )
    run.chunks = cut(groups_of(question, plan.units), p.chunk_size)
    if len(run.chunks) > MAX_CHUNKS:
        raise WorkflowError(
            f"pass {p.id}: {len(run.chunks)} chunks, more than {MAX_CHUNKS}: raise chunk_size"
        )
    return run


# --------------------------------------------------------------------------
# run (10.1)
# --------------------------------------------------------------------------


def select(
    workflow: Workflow, passes: Sequence[str] | None, models: Sequence[str] | None
) -> list[tuple[Pass, str]]:
    """The (pass, model) pairs to run, in file order then pass order; `WorkflowError`
    when a restriction is empty, names nothing in the workflow, or leaves nothing."""
    if passes is not None:
        passes = list(passes)
        known = {p.id for p in workflow.passes}
        unknown = [name for name in passes if name not in known]
        if not passes or unknown:
            raise WorkflowError(
                f"passes {passes!r} name nothing to run in the workflow"
            )
    if models is not None:
        models = list(models)
        unknown = [name for name in models if name not in workflow.models]
        if not models or unknown:
            raise WorkflowError(
                f"models {models!r} name nothing to run in the workflow"
            )
    chosen = [
        (p, m)
        for p in workflow.passes
        if passes is None or p.id in passes
        for m in p.models
        if models is None or m in models
    ]
    if not chosen:
        raise WorkflowError("the passes and models asked leave nothing to run")
    return chosen


def answer_items(
    workflow: Workflow, answer_models: Mapping[str, type[pydantic.BaseModel]] | None
) -> dict[str, ItemSpec]:
    """The item of each answer model given from Python (4.5)."""
    items: dict[str, ItemSpec] = {}
    for pass_id, model in (answer_models or {}).items():
        try:
            p = workflow.pass_by_id(pass_id)
        except KeyError:
            raise WorkflowError(
                f"an answer model for {pass_id!r}, not a pass of the workflow"
            ) from None
        q = p.question
        if q.readout != "json_object" or q.spec.form != "label_object":
            raise WorkflowError(
                f"an answer model for {pass_id}, not a label_object pass"
            )
        items[pass_id] = model_item(model)
    return items


def write_workflow_record(
    workflow: Workflow, chosen: Sequence[tuple[Pass, str]]
) -> None:
    """Write `<output_dir>/workflow.json` (section 9)."""
    record = {
        "package_version": package_version(),
        "workflow": workflow.resolved(),
        "tables": {
            f"{p.id}/{m}": {
                "table": str(workflow.output_of(p.id, m)),
                "manifest": str(workflow.work_dir(p.id, m) / "manifest.json"),
            }
            for p in workflow.passes
            for m in p.models
        },
        "asked": [f"{p.id}/{m}" for p, m in chosen],
    }
    workflow.output_dir.mkdir(parents=True, exist_ok=True)
    path = workflow.output_dir / "workflow.json"
    partial = path.with_name(f"workflow.json.{os.getpid()}.partial")
    partial.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(partial, path)


def run(
    workflow: Workflow,
    *,
    texts: pl.DataFrame | str | Path | None = None,
    replay: bool = False,
    passes: Sequence[str] | None = None,
    models: Sequence[str] | None = None,
    limit: int | None = None,
    worker: str = "main",
    reverse: bool = False,
    combine_only: bool = False,
    answer_models: Mapping[str, type[pydantic.BaseModel]] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> list[RunResult]:
    """Run the passes of a workflow (contract 10.1); one `RunResult` per (pass, model) asked.

    Before any call and any write it refuses a bad worker name, restrictions
    naming nothing (`WorkflowError`), an unfit answer model (`QuestionError`
    or `WorkflowError`), missing or bad texts (`TextsError`) and, in a live
    run, a missing key (`KeyMissing`). Passes run in file order, models in
    pass order. A pass whose sources were not written in this invocation is
    returned with `output_written = False` and `units = 0`.
    """
    if not isinstance(worker, str) or WORKER_RE.fullmatch(worker) is None:
        raise WorkflowError(
            f"the worker name {worker!r} does not match [A-Za-z0-9_-]{{1,64}}"
        )
    chosen = select(workflow, passes, models)
    items = answer_items(workflow, answer_models)
    fields = sorted({f for p, _ in chosen for f in p.question.text_fields})
    frame = load_texts(workflow, texts, fields)
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise WorkflowError(
                f"limit must be a whole number of works >= 1, not {limit!r}"
            )
        frame = frame.head(limit)
    keys: dict[str, str | None] = {}
    for _, m in chosen:
        if m not in keys:
            live = not replay and not combine_only
            keys[m] = workflow.api_key(workflow.models[m]) if live else None

    results: list[RunResult] = []
    written: dict[tuple[str, str], bool] = {}
    recorded = False
    for p, m in chosen:
        output = workflow.output_of(p.id, m)
        blocked = [s for s in p.sources_of(m) if written.get(s) is False]
        if blocked:
            results.append(RunResult(p.id, m, 0, 0, [], [], [], [], False, output))
            written[(p.id, m)] = False
            continue
        pass_run = prepare(workflow, p, m, frame, items.get(p.id))
        if not recorded:
            write_workflow_record(workflow, chosen)
            recorded = True
        result = _run_one(
            pass_run, keys[m], replay, worker, reverse, combine_only, transport
        )
        written[(p.id, m)] = result.output_written
        results.append(result)
    return results


def _run_one(
    pass_run: PassRun,
    api_key: str | None,
    replay: bool,
    worker: str,
    reverse: bool,
    combine_only: bool,
    transport: httpx.BaseTransport | None,
) -> RunResult:
    pass_run.check_record(create=not combine_only)
    indices = list(range(1, len(pass_run.chunks) + 1))
    written: list[int] = []
    on_disk: list[int] = []
    claimed: list[int] = []
    if not combine_only:
        entry = pass_run.entry
        workflow = pass_run.workflow
        log = CallLog(pass_run.work_dir / "calls" / f"{worker}.jsonl")
        client = Client(
            endpoint=entry.endpoint,
            api_key=api_key,
            cache_dir=workflow.cache_dir_of(pass_run.p, pass_run.model),
            concurrency=entry.concurrency,
            max_retries=entry.max_retries,
            timeout_s=pass_run.p.settings[pass_run.model].timeout_s,
            replay=replay,
            expect_model=entry.expect_model,
            transport=transport,
            names=(pass_run.p.id, pass_run.model),
            log=log,
        )
        with client:
            written, on_disk, claimed = pass_run.visit(client, worker, reverse)
    missing = [n for n in indices if not pass_run.chunk_path(n).is_file()]
    output_written = False
    if not missing or combine_only:
        table = pass_run.combine()
        pass_run.write_manifest(table, replay)
        output_written = True
    return RunResult(
        pass_id=pass_run.p.id,
        model=pass_run.model,
        units=len(pass_run.plan.units),
        chunks=len(pass_run.chunks),
        written=written,
        skipped_on_disk=on_disk,
        skipped_claimed=claimed,
        missing=missing,
        output_written=output_written,
        output=pass_run.output,
    )


def check_lines(
    workflow: Workflow, texts: pl.DataFrame | str | Path | None = None
) -> list[str]:
    """What `check` prints: per (pass, model), the prompt ids, run id and unit count.

    Loads the texts and plans every pass whose sources exist on disk; makes
    no call and writes nothing.
    """
    chosen = select(workflow, None, None)
    fields = sorted({f for p, _ in chosen for f in p.question.text_fields})
    frame = load_texts(workflow, texts, fields)
    lines = []
    for p, m in chosen:
        ids = ", ".join(sorted(set(p.prompt_ids.values())))
        waiting = [
            f"{s}/{sm}"
            for s, sm in p.sources_of(m)
            if not workflow.output_of(s, sm).is_file()
        ]
        if waiting:
            run_id = Asker(p, workflow.models[m], p.settings[m], _item_of(p)).run_id()
            lines.append(
                f"{p.id} {m}: prompt {ids}, {run_id}, units waiting on {', '.join(waiting)}"
            )
            continue
        pass_run = prepare(workflow, p, m, frame, None)
        lines.append(
            f"{p.id} {m}: prompt {ids}, {pass_run.run_id}, {len(pass_run.plan.units)} units, "
            f"{len(pass_run.chunks)} chunks"
        )
    return lines


def _item_of(p: Pass) -> ItemSpec | None:
    q = p.question
    if q.readout == "json_object" and q.spec.form == "label_object":
        return declared_item(q.spec.fields)
    return None
