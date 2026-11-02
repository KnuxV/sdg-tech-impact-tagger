"""The workflow file (contract section 7): strict TOML, checked whole before any call.

A workflow names the texts, the model entries (6.1), the lists it adds to
the shipped ones, and the passes to run in order, each a question asked of
one or more models over the units of a unit rule (section 5). Loading it
refuses any unknown key at any level (D015) and every combination section 7
refuses, so that `run` starts only on a workflow that fits.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sdg_tech_impact_tagger.errors import KeyMissing, ListError, WorkflowError
from sdg_tech_impact_tagger.lists import (
    SHIPPED_LISTS,
    LabelList,
    read_list,
    shipped_lists,
)
from sdg_tech_impact_tagger.questions import (
    OTHER,
    Question,
    load_question,
    pydantic_message,
)

PRESETS_DIR = Path(__file__).resolve().parent / "presets"
PRESETS = ("protocol-v1", "protocol-v1-impact", "paper-v1")
MODEL_NAME_RE = re.compile(r"[a-z][a-z0-9_]*")

# Keys the package sends itself; a model's extra_body may not set them (6.3).
RESERVED_EXTRA = (
    "model",
    "messages",
    "temperature",
    "max_tokens",
    "seed",
    "logprobs",
    "top_logprobs",
    "response_format",
    "reasoning_effort",
    "n",
    "stream",
)


# --------------------------------------------------------------------------
# the file, as strict models
# --------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class _Run(_Strict):
    name: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    texts: str | None = None
    id_column: str = "id"
    cache_dir: str = "cache"
    output_dir: str | None = None
    env_file: str = ".env"


class _Model(_Strict):
    endpoint: str
    api_key_env: str
    model: str
    seed: int
    temperature: float = 0.0
    reasoning: Literal["off", "on"]
    reasoning_style: Literal["omit", "enable_thinking", "reasoning_effort"]
    reasoning_effort: str | None = None
    extra_body: dict[str, Any] = {}
    extraction: Literal["first_token", "final_channel"] = "first_token"
    expect_model: str | list[str] | None = None
    timeout_s: float = Field(default=60.0, gt=0)
    concurrency: int = Field(default=4, ge=1)
    max_retries: int = Field(default=3, ge=0)


class _Side(_Strict):
    from_: str = Field(alias="from")
    models: list[str] | Literal["all"]
    positive: list[str]
    combine: Literal["union", "intersection"] | None = None


class _All(_Strict):
    rule: Literal["all"]


class _Threshold(_Strict):
    rule: Literal["threshold"]
    from_: str = Field(alias="from")
    model: str
    at_least: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    allow_unscored: bool = False


class _Cross(_Strict):
    rule: Literal["cross"]
    a: _Side
    b: _Side
    agreed_first: bool = False


class _Flags(_Strict):
    a: _Side
    b: _Side


class _File(_Strict):
    rule: Literal["file"]
    path: str
    flags: _Flags | None = None


_Units = Annotated[_All | _Threshold | _Cross | _File, Field(discriminator="rule")]


class _Budgets(_Strict):
    max_tokens: int | None = Field(default=None, ge=1)
    retry_max_tokens: int | None = None
    top_logprobs: int | None = None
    timeout_s: float | None = Field(default=None, gt=0)


class _Pass(_Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    question: str | None = None
    question_dir: str | None = None
    models: list[str] = Field(min_length=1)
    units: _Units
    chunk_size: int = Field(default=1000, ge=1)
    sub_chunk: int = Field(default=100, ge=1)
    attempts: int = Field(default=3, ge=1)
    repeats: int = Field(default=1, ge=1)
    spelling: Literal["sum", "exact"] | None = None
    budget_rule: Literal["spent", "tokens", "length"] = "spent"
    null_text: str = ""
    prompt_prefix: str | None = Field(default=None, pattern=r"^[a-z0-9.]+$")
    budgets: dict[str, _Budgets] = {}
    cache_dirs: dict[str, str] = {}


class _WorkflowFile(_Strict):
    run: _Run
    lists: dict[str, str] = {}
    models: dict[str, _Model] = Field(min_length=1)
    passes: list[_Pass] = Field(min_length=1)


# --------------------------------------------------------------------------
# the loaded workflow
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelEntry:
    """A model entry of section 6.1, every default filled."""

    name: str
    endpoint: str
    api_key_env: str
    model: str
    seed: int
    temperature: float
    reasoning: str
    reasoning_style: str
    reasoning_effort: str | None
    extra_body: dict[str, Any]
    extraction: str
    expect_model: tuple[str, ...] | None
    timeout_s: float
    concurrency: int
    max_retries: int

    def record(self) -> dict[str, Any]:
        """Every key of 6.1 with its resolved value; the key's variable, never its value."""
        return {
            "endpoint": self.endpoint,
            "api_key_env": self.api_key_env,
            "model": self.model,
            "seed": self.seed,
            "temperature": self.temperature,
            "reasoning": self.reasoning,
            "reasoning_style": self.reasoning_style,
            "reasoning_effort": self.reasoning_effort,
            "extra_body": self.extra_body,
            "extraction": self.extraction,
            "expect_model": None
            if self.expect_model is None
            else list(self.expect_model),
            "timeout_s": self.timeout_s,
            "concurrency": self.concurrency,
            "max_retries": self.max_retries,
        }

    def reasoning_fields(self) -> dict[str, Any]:
        """The fields the reasoning setting adds to the body (6.2)."""
        on = self.reasoning == "on"
        if self.reasoning_style == "enable_thinking":
            return {"chat_template_kwargs": {"enable_thinking": on}}
        if self.reasoning_style == "reasoning_effort":
            return {"reasoning_effort": self.reasoning_effort if on else "none"}
        return {}


@dataclass(frozen=True)
class PassModel:
    """The settings of one (pass, model): budgets resolved, and its own cache if any."""

    max_tokens: int
    retry_max_tokens: int | None
    top_logprobs: int | None
    timeout_s: float
    cache_dir: Path | None


@dataclass
class Pass:
    """A pass of the workflow: a question asked of its models over a unit rule."""

    id: str
    question: Question
    models: tuple[str, ...]
    units: dict[str, Any]
    chunk_size: int
    sub_chunk: int
    attempts: int
    repeats: int
    spelling: str | None
    budget_rule: str
    null_text: str
    prompt_prefix: str | None
    prompt_ids: dict[str, str]
    settings: dict[str, PassModel]

    @property
    def rule(self) -> str:
        """The name of the unit rule."""
        return self.units["rule"]

    def sources(self) -> list[tuple[str, str]]:
        """The (pass, model) tables the unit rule reads, for any model of this pass."""
        rule = self.units
        if rule["rule"] == "threshold":
            if rule["model"] == "same":
                return [(rule["from"], m) for m in self.models]
            return [(rule["from"], rule["model"])]
        sides = None
        if rule["rule"] == "cross":
            sides = rule
        elif rule["rule"] == "file" and rule.get("flags"):
            sides = rule["flags"]
        if sides is None:
            return []
        return [(sides[s]["from"], m) for s in ("a", "b") for m in sides[s]["models"]]

    def sources_of(self, model: str) -> list[tuple[str, str]]:
        """The (pass, model) tables the unit rule reads for one model of this pass."""
        rule = self.units
        if rule["rule"] == "threshold":
            return [(rule["from"], model if rule["model"] == "same" else rule["model"])]
        return self.sources()


@dataclass
class Workflow:
    """A checked workflow (section 7): paths absolute, every default filled."""

    name: str
    path: Path | None
    preset: str | None
    base: Path
    sha256: str
    texts: Path | None
    id_column: str
    cache_dir: Path
    output_dir: Path
    env_file: Path
    lists: dict[str, LabelList]
    list_files: dict[str, Path]
    models: dict[str, ModelEntry]
    passes: list[Pass]
    _env: dict[str, str] | None = field(default=None, repr=False)

    def pass_by_id(self, pass_id: str) -> Pass:
        """The pass of that id; `KeyError` when there is none."""
        for p in self.passes:
            if p.id == pass_id:
                return p
        raise KeyError(pass_id)

    def cache_dir_of(self, p: Pass, model: str) -> Path:
        """The cache directory of a (pass, model): its own, else the run's."""
        return p.settings[model].cache_dir or self.cache_dir

    def output_of(self, pass_id: str, model: str) -> Path:
        """The output table of a (pass, model) (8.1)."""
        return self.output_dir / pass_id / f"{model}.parquet"

    def work_dir(self, pass_id: str, model: str) -> Path:
        """The directory of the run of a (pass, model) (8.1)."""
        return self.output_dir / pass_id / model

    def api_key(self, entry: ModelEntry) -> str:
        """The key of a model entry, from the environment or else the env file (6.1).

        Raises `KeyMissing`, naming the variable and never a value, when it
        is unset or empty.
        """
        if self._env is None:
            self._env = read_env_file(self.env_file)
        var = entry.api_key_env
        value = os.environ[var] if var in os.environ else self._env.get(var, "")
        if not value:
            raise KeyMissing(
                f"the key of model {entry.name} is missing: set the environment variable "
                f"{var} (or give it in {self.env_file})"
            )
        return value

    def resolved(self) -> dict[str, Any]:
        """The workflow with every default filled, for `workflow.json` (section 9)."""
        return {
            "run": {
                "name": self.name,
                "path": None if self.path is None else str(self.path),
                "preset": self.preset,
                "workflow_sha256": self.sha256,
                "texts": None if self.texts is None else str(self.texts),
                "id_column": self.id_column,
                "cache_dir": str(self.cache_dir),
                "output_dir": str(self.output_dir),
                "env_file": str(self.env_file),
            },
            "lists": {k: str(v) for k, v in self.list_files.items()},
            "models": {name: entry.record() for name, entry in self.models.items()},
            "passes": [
                {
                    "id": p.id,
                    "question": p.question.name,
                    "question_dir": str(p.question.directory),
                    "models": list(p.models),
                    "units": p.units,
                    "chunk_size": p.chunk_size,
                    "sub_chunk": p.sub_chunk,
                    "attempts": p.attempts,
                    "repeats": p.repeats,
                    "spelling": p.spelling,
                    "budget_rule": p.budget_rule,
                    "null_text": p.null_text,
                    "prompt_prefix": p.prompt_prefix,
                    "prompt_ids": p.prompt_ids,
                    "budgets": {
                        m: {
                            "max_tokens": s.max_tokens,
                            "retry_max_tokens": s.retry_max_tokens,
                            "top_logprobs": s.top_logprobs,
                            "timeout_s": s.timeout_s,
                        }
                        for m, s in p.settings.items()
                    },
                    "cache_dirs": {m: str(self.cache_dir_of(p, m)) for m in p.models},
                }
                for p in self.passes
            ],
        }


def read_env_file(path: Path) -> dict[str, str]:
    """The `KEY=VALUE` lines of an env file, as [OA] `llm_passes.py:958-973` reads them.

    Empty lines, `#` comments and lines without `=` are skipped; the key
    loses a leading `export `, the value its surrounding quotes. A missing
    file gives no value.
    """
    values: dict[str, str] = {}
    if not Path(path).is_file():
        return values
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def load_workflow(
    path: str | Path | None = None, *, preset: str | None = None
) -> Workflow:
    """Load and check a workflow file, or a shipped preset by name (section 7).

    Exactly one of `path` and `preset`. Relative paths are read against the
    workflow file's directory, a preset's against the current directory.
    Produces a `Workflow` whose questions, lists, models, budgets and unit
    rules are all checked. Raises `WorkflowError` (the file, an unknown or
    missing key, a combination section 7 refuses), `QuestionError` (a
    question) or `ListError` (a list).
    """
    if (path is None) == (preset is None):
        raise WorkflowError("give exactly one of a workflow path and a preset")
    if preset is not None:
        if preset not in PRESETS:
            raise WorkflowError(f"no preset {preset!r}; shipped: {', '.join(PRESETS)}")
        file = PRESETS_DIR / f"{preset}.toml"
        base = Path.cwd()
        shown: Path | None = None
    else:
        file = Path(path).absolute()  # type: ignore[arg-type]
        if not file.is_file():
            raise WorkflowError(f"the workflow file {file} does not exist")
        base = file.parent
        shown = file
    raw = file.read_bytes()
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise WorkflowError(f"{file}: not TOML: {exc}") from exc
    try:
        spec = _WorkflowFile.model_validate(data)
    except ValidationError as exc:
        raise WorkflowError(f"{file}: {pydantic_message(exc)}") from exc
    return _build(
        spec, file=shown, preset=preset, base=base, sha=hashlib.sha256(raw).hexdigest()
    )


def _build(
    spec: _WorkflowFile, *, file: Path | None, preset: str | None, base: Path, sha: str
) -> Workflow:
    where = str(file) if file is not None else f"preset {preset}"
    lists, list_files = _lists(spec, base, where)
    models = _models(spec, where)
    passes: list[Pass] = []
    for item in spec.passes:
        if any(p.id == item.id for p in passes):
            raise WorkflowError(f"{where}: the pass id {item.id} is repeated")
        passes.append(_pass(item, passes, models, lists, base, where))
    run = spec.run
    return Workflow(
        name=run.name,
        path=file,
        preset=preset,
        base=base,
        sha256=sha,
        texts=None if run.texts is None else base / run.texts,
        id_column=run.id_column,
        cache_dir=base / run.cache_dir,
        output_dir=base / (run.output_dir or f"runs/{run.name}"),
        env_file=base / run.env_file,
        lists=lists,
        list_files=list_files,
        models=models,
        passes=passes,
    )


def _lists(
    spec: _WorkflowFile, base: Path, where: str
) -> tuple[dict[str, LabelList], dict[str, Path]]:
    registry = shipped_lists()
    files = {
        list_id: loaded.path for list_id, loaded in registry.items() if loaded.path
    }
    for list_id, relative in spec.lists.items():
        if list_id in SHIPPED_LISTS:
            raise ListError(
                f"{where}: [lists].{list_id} clashes with the shipped list {list_id}"
            )
        loaded = read_list(base / relative)
        if loaded.id != list_id:
            raise ListError(
                f"{where}: [lists].{list_id} names the file {relative}, whose list id is "
                f"{loaded.id}"
            )
        registry[list_id] = loaded
        files[list_id] = base / relative
    return registry, files


def _models(spec: _WorkflowFile, where: str) -> dict[str, ModelEntry]:
    models: dict[str, ModelEntry] = {}
    for name, m in spec.models.items():
        at = f"{where}: [models.{name}]"
        if MODEL_NAME_RE.fullmatch(name) is None:
            raise WorkflowError(f"{at}: a model entry name must match [a-z][a-z0-9_]*")
        needs_effort = m.reasoning_style == "reasoning_effort" and m.reasoning == "on"
        if needs_effort and m.reasoning_effort is None:
            raise WorkflowError(
                f"{at}: reasoning_effort is required with this style and on"
            )
        if not needs_effort and m.reasoning_effort is not None:
            raise WorkflowError(
                f"{at}: reasoning_effort is taken only with style reasoning_effort and on"
            )
        reserved = sorted(k for k in m.extra_body if k in RESERVED_EXTRA)
        kwargs = m.extra_body.get("chat_template_kwargs")
        if kwargs is not None and not isinstance(kwargs, dict):
            raise WorkflowError(
                f"{at}: extra_body.chat_template_kwargs must be a table"
            )
        if isinstance(kwargs, dict) and "enable_thinking" in kwargs:
            reserved.append("chat_template_kwargs.enable_thinking")
        if reserved:
            raise WorkflowError(f"{at}: extra_body may not set {', '.join(reserved)}")
        expect = m.expect_model
        if isinstance(expect, list) and not expect:
            raise WorkflowError(f"{at}: expect_model is an empty list")
        models[name] = ModelEntry(
            name=name,
            endpoint=m.endpoint,
            api_key_env=m.api_key_env,
            model=m.model,
            seed=m.seed,
            temperature=float(m.temperature),
            reasoning=m.reasoning,
            reasoning_style=m.reasoning_style,
            reasoning_effort=m.reasoning_effort,
            extra_body=dict(m.extra_body),
            extraction=m.extraction,
            expect_model=None
            if expect is None
            else ((expect,) if isinstance(expect, str) else tuple(expect)),
            timeout_s=float(m.timeout_s),
            concurrency=m.concurrency,
            max_retries=m.max_retries,
        )
    return models


def _question(
    item: _Pass, base: Path, lists: dict[str, LabelList], at: str
) -> Question:
    if (item.question is None) == (item.question_dir is None):
        raise WorkflowError(f"{at}: give exactly one of question and question_dir")
    if item.question is not None:
        if not (Path(__file__).resolve().parent / "questions" / item.question).is_dir():
            raise WorkflowError(f"{at}: no shipped question {item.question!r}")
        return load_question(item.question, lists)
    return load_question(base / item.question_dir, lists)  # type: ignore[operator]


def _pass(
    item: _Pass,
    earlier: list[Pass],
    models: dict[str, ModelEntry],
    lists: dict[str, LabelList],
    base: Path,
    where: str,
) -> Pass:
    at = f"{where}: pass {item.id}"
    if len(set(item.models)) != len(item.models):
        raise WorkflowError(f"{at}: models repeat")
    unknown = [m for m in item.models if m not in models]
    if unknown:
        raise WorkflowError(f"{at}: unknown model {', '.join(unknown)}")
    question = _question(item, base, lists, at)
    readout = question.readout

    # Prompt ids, under a recorded prefix if one is given (3.5).
    prompt_ids = question.ids_with_prefix(item.prompt_prefix)
    if item.prompt_prefix is not None and prompt_ids != question.ids_with_prefix():
        outside = sorted(
            v for v in prompt_ids.values() if v not in question.recorded_ids
        )
        if outside:
            raise WorkflowError(
                f"{at}: prompt_prefix {item.prompt_prefix} gives {', '.join(outside)}, "
                f"not among the recorded ids of {question.name}"
            )

    # Readout settings (D006, D007).
    if item.spelling is not None and readout != "letter_logprob":
        raise WorkflowError(f"{at}: spelling is for letter_logprob only")
    spelling = (item.spelling or "sum") if readout == "letter_logprob" else None
    if readout == "letter_logprob":
        on = [m for m in item.models if models[m].reasoning == "on"]
        if on:
            raise WorkflowError(
                f"{at}: letter_logprob is refused with reasoning on (D006): {', '.join(on)}"
            )

    # Budgets per model (7.3, 7.5).
    stray = sorted(set(item.budgets) - set(item.models))
    if stray:
        raise WorkflowError(
            f"{at}: budgets of a model not in the pass: {', '.join(stray)}"
        )
    stray = sorted(set(item.cache_dirs) - set(item.models))
    if stray:
        raise WorkflowError(
            f"{at}: cache_dirs of a model not in the pass: {', '.join(stray)}"
        )
    settings: dict[str, PassModel] = {}
    for m in item.models:
        given = item.budgets.get(m, _Budgets())
        b_at = f"{at}: [passes.budgets.{m}]"
        if given.top_logprobs is not None:
            if readout != "letter_logprob":
                raise WorkflowError(f"{b_at}: top_logprobs is for letter_logprob only")
            if not 0 <= given.top_logprobs <= 20:
                raise WorkflowError(f"{b_at}: top_logprobs must be 0 to 20")
        if given.retry_max_tokens is not None and readout not in (
            "letter_text",
            "json_object",
        ):
            raise WorkflowError(
                f"{b_at}: retry_max_tokens is for letter_text and json_object"
            )
        max_tokens = given.max_tokens or question.budget.max_tokens
        retry = given.retry_max_tokens or question.budget.retry_max_tokens
        if retry is not None and retry <= max_tokens:
            raise WorkflowError(
                f"{b_at}: retry_max_tokens {retry} is not above {max_tokens}"
            )
        top = (
            given.top_logprobs
            if given.top_logprobs is not None
            else question.budget.top_logprobs
        )
        settings[m] = PassModel(
            max_tokens=max_tokens,
            retry_max_tokens=retry,
            top_logprobs=top,
            timeout_s=float(given.timeout_s or models[m].timeout_s),
            cache_dir=base / item.cache_dirs[m] if m in item.cache_dirs else None,
        )

    units = _units(item, question, earlier, at)
    return Pass(
        id=item.id,
        question=question,
        models=tuple(item.models),
        units=units,
        chunk_size=item.chunk_size,
        sub_chunk=item.sub_chunk,
        attempts=item.attempts,
        repeats=item.repeats,
        spelling=spelling,
        budget_rule=item.budget_rule,
        null_text=item.null_text,
        prompt_prefix=item.prompt_prefix,
        prompt_ids=prompt_ids,
        settings=settings,
    )


def _source_pass(name: str, earlier: list[Pass], at: str) -> Pass:
    for p in earlier:
        if p.id == name:
            if p.repeats > 1:
                raise WorkflowError(f"{at}: the source pass {name} has repeats > 1")
            return p
    raise WorkflowError(f"{at}: {name} is not a pass listed before this one")


def _labels_pass(source: Pass) -> bool:
    """A pass whose rows carry one `label` per (id, code) of its list `a` (section 5)."""
    q = source.question
    if q.readout == "letter_text" and q.spec.layout == "table":
        return True
    return (
        q.readout in ("letter_logprob", "letter_text")
        and not q.sides
        and q.level == ("work x list")
    )


def _side(
    name: str,
    side: _Side,
    question: Question,
    earlier: list[Pass],
    at: str,
) -> dict[str, Any]:
    s_at = f"{at}: side {name}"
    source = _source_pass(side.from_, earlier, s_at)
    if not _labels_pass(source):
        raise WorkflowError(
            f"{s_at}: {source.id} is not a pass of one label per (work, label)"
        )
    wanted = question.lists[name]
    if source.question.lists.get("a") != wanted:
        raise WorkflowError(f"{s_at}: {source.id} reads another list than {wanted}")
    if side.models == "all":
        chosen = list(source.models)
    else:
        chosen = list(side.models)
        if not chosen or len(set(chosen)) != len(chosen):
            raise WorkflowError(f"{s_at}: models must be non-empty and unique")
        stray = [m for m in chosen if m not in source.models]
        if stray:
            raise WorkflowError(
                f"{s_at}: {', '.join(stray)} not a model of {source.id}"
            )
    letters = set(source.question.spec.letters) | {OTHER}
    if not side.positive or len(set(side.positive)) != len(side.positive):
        raise WorkflowError(f"{s_at}: positive must be non-empty, without repeats")
    bad = [p for p in side.positive if p not in letters]
    if bad:
        raise WorkflowError(
            f"{s_at}: positive {bad} not letters of {source.id} nor OTHER"
        )
    if len(chosen) > 1 and side.combine is None:
        raise WorkflowError(
            f"{s_at}: several models need combine (union or intersection)"
        )
    return {
        "from": side.from_,
        "models": chosen,
        "positive": list(side.positive),
        "combine": side.combine,
    }


def _units(
    item: _Pass,
    question: Question,
    earlier: list[Pass],
    at: str,
) -> dict[str, Any]:
    """Check the unit rule against the question and the earlier passes; resolve it."""
    rule = item.units
    level = question.level
    if isinstance(rule, _All):
        return {"rule": "all"}
    if isinstance(rule, _Threshold):
        if level != "work x list":
            raise WorkflowError(
                f"{at}: threshold needs a work x list question, not {level}"
            )
        source = _source_pass(rule.from_, earlier, at)
        if source.question.readout != "score_json":
            raise WorkflowError(
                f"{at}: threshold reads a score_json pass, not {source.id}"
            )
        if source.question.lists.get("a") != question.lists.get("a"):
            raise WorkflowError(
                f"{at}: {source.id} scores another list than this question's"
            )
        if rule.model == "same":
            stray = [m for m in item.models if m not in source.models]
            if stray:
                raise WorkflowError(
                    f"{at}: model same, but {', '.join(stray)} is not a model of {source.id}"
                )
        elif rule.model not in source.models:
            raise WorkflowError(f"{at}: {rule.model} is not a model of {source.id}")
        if isinstance(rule.at_least, bool) or not math.isfinite(rule.at_least):
            raise WorkflowError(f"{at}: at_least must be a number in [0, 1]")
        return {
            "rule": "threshold",
            "from": rule.from_,
            "model": rule.model,
            "at_least": rule.at_least,
            "allow_unscored": rule.allow_unscored,
        }
    if isinstance(rule, _Cross):
        if level != "work x list x list":
            raise WorkflowError(
                f"{at}: cross needs a work x list x list question, not {level}"
            )
        a = _side("a", rule.a, question, earlier, at)
        b = _side("b", rule.b, question, earlier, at)
        if question.lists["a"] == question.lists["b"]:
            raise WorkflowError(f"{at}: the two sides read the same list")
        return {"rule": "cross", "a": a, "b": b, "agreed_first": rule.agreed_first}
    flags = None
    if rule.flags is not None:
        if level != "work x list x list":
            raise WorkflowError(f"{at}: file flags need a work x list x list question")
        flags = {
            "a": _side("a", rule.flags.a, question, earlier, at),
            "b": _side("b", rule.flags.b, question, earlier, at),
        }
    return {"rule": "file", "path": rule.path, "flags": flags}
