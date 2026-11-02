"""The client: one call, the cache, retries and batches (contract 4.1, 6.3 to 6.5).

Every call of a run goes through one `Client`, which serves it from the
cache when a file holds its key, and otherwise posts it to an
OpenAI-compatible `/chat/completions` endpoint and writes the raw answer to
the cache before returning it. The cache key and the cache file are those of
the earlier client of open_alex_adt_gate (`llm/client.py:382-421, 460-492`),
so its caches replay unchanged (D013).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import warnings
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError

from sdg_tech_impact_tagger.errors import (
    CacheError,
    CacheMiss,
    LLMCallError,
    ModelChangeWarning,
    ModelMismatch,
)

# The backoff between HTTP retries: attempt n sleeps BACKOFF_BASE_S * 2**n,
# capped at BACKOFF_CAP_S. Module attributes, read at each sleep, so tests
# can patch them.
BACKOFF_BASE_S = 0.5
BACKOFF_CAP_S = 8.0


def cache_key(fields: dict[str, Any]) -> str:
    """The cache key of a request's key fields (contract 6.5).

    The sha256 hex digest of the canonical JSON of `fields`: sorted keys,
    separators `,` and `:`, `ensure_ascii` true.
    """
    blob = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# reading a body: lenient models, a field that does not fit is an empty answer
# --------------------------------------------------------------------------


class _Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class _TopLogprob(BaseModel):
    token: str
    logprob: float


class _LogprobEntry(BaseModel):
    token: str = ""
    logprob: float = 0.0
    top_logprobs: list[_TopLogprob] = []


class _ChoiceLogprobs(BaseModel):
    content: list[_LogprobEntry] | None = None


class _Message(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    message: _Message = _Message()
    logprobs: _ChoiceLogprobs | None = None
    finish_reason: str | None = None


class _ChatResponse(BaseModel):
    choices: list[_Choice] = []
    usage: _Usage | None = None


@dataclass(frozen=True)
class Answer:
    """A body read as [OA] `llm/client.py:533-552` reads it.

    `content` is the message content (None when absent), `entries` the
    logprob entries of the first choice as (token, [(top token, logprob)]),
    `finish_reason` `""` when absent, the token counts 0 when absent, and
    the served model and fingerprint when they are non-empty strings.
    """

    content: str | None
    entries: tuple[tuple[str, tuple[tuple[str, float], ...]], ...]
    finish_reason: str
    tokens_in: int
    tokens_out: int
    model_served: str | None
    system_fingerprint: str | None

    @property
    def text(self) -> str:
        """The content, `""` when null."""
        return self.content or ""


def read_body(body: Any) -> Answer:
    """Read a raw body into an `Answer`; a body that does not fit reads as empty."""
    try:
        parsed = _ChatResponse.model_validate(body)
    except ValidationError:
        parsed = _ChatResponse()
    choice = parsed.choices[0] if parsed.choices else _Choice()
    usage = parsed.usage or _Usage()
    content = (
        choice.logprobs.content if choice.logprobs and choice.logprobs.content else []
    )
    entries = tuple(
        (entry.token, tuple((t.token, t.logprob) for t in entry.top_logprobs))
        for entry in content
    )

    def named(key: str) -> str | None:
        value = body.get(key) if isinstance(body, dict) else None
        return value if isinstance(value, str) and value else None

    return Answer(
        content=choice.message.content,
        entries=entries,
        finish_reason=choice.finish_reason or "",
        tokens_in=usage.prompt_tokens,
        tokens_out=usage.completion_tokens,
        model_served=named("model"),
        system_fingerprint=named("system_fingerprint"),
    )


# --------------------------------------------------------------------------
# requests and outcomes
# --------------------------------------------------------------------------


@dataclass
class Request:
    """One call: its kind, key fields, wire body, and what the run needs to log it.

    `kind` is `chat` or `single_token`; `fields` the cache key fields in
    their insertion order; `payload` the wire body; `repeat` the repeat
    number; `retry` whether it is a budget retry; `unreadable` tells, from
    the answer, whether the readout could not read it (for the call log).
    """

    kind: str
    fields: dict[str, Any]
    payload: dict[str, Any]
    repeat: int = 1
    retry: bool = False
    unreadable: Callable[[Answer], bool] = field(
        default=lambda answer: False, repr=False
    )

    @property
    def key(self) -> str:
        """The cache key of the request."""
        return cache_key(self.fields)

    def with_budget(self, max_tokens: int) -> Request:
        """The same request with another `max_tokens`, marked as a budget retry."""
        fields = {
            k: (max_tokens if k == "max_tokens" else v) for k, v in self.fields.items()
        }
        payload = {
            k: (max_tokens if k == "max_tokens" else v) for k, v in self.payload.items()
        }
        return Request(
            kind=self.kind,
            fields=fields,
            payload=payload,
            repeat=self.repeat,
            retry=True,
            unreadable=self.unreadable,
        )


@dataclass(frozen=True)
class Outcome:
    """The answer of a call, whether it came from the cache, and its key."""

    answer: Answer
    cached: bool
    key: str


# --------------------------------------------------------------------------
# the client
# --------------------------------------------------------------------------


class Client:
    """A cached, retrying client of one endpoint, for one run (pass, model).

    Consumes `Request`s, produces `Outcome`s. In replay it never posts: a
    call not in the cache raises `CacheMiss`. With `expect_model`, an answer
    from another model raises `ModelMismatch` and is not cached. Each call
    made or read is passed to `log` with its outcome, in completion order.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str | None,
        cache_dir: Path,
        concurrency: int = 4,
        max_retries: int = 3,
        timeout_s: float = 60.0,
        replay: bool = False,
        expect_model: Sequence[str] | None = None,
        transport: httpx.BaseTransport | None = None,
        names: tuple[str, str] = ("", ""),
        log: Callable[[Request, Outcome, float], None] | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.replay = replay
        self.expect_model = None if expect_model is None else list(expect_model)
        self.names = names
        self.log = log
        self.changes: list[dict[str, Any]] = []
        self._first: tuple[str | None, str | None] | None = None
        self._warned: set[tuple[str | None, str | None]] = set()
        self._lock = threading.Lock()
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(
            base_url=endpoint.rstrip("/"),
            headers=headers,
            timeout=timeout_s,
            transport=transport,
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- one call ----------------------------------------------------------

    def call(self, request: Request) -> Outcome:
        """Answer one request from the cache or the endpoint (contract 6.4)."""
        started = time.perf_counter()
        key = request.key
        path = self.cache_dir / key[:2] / f"{key}.json"
        if path.exists():
            body = self._read_cache(path)
            self._check_model(body, f"the cache file {path}")
            outcome = Outcome(read_body(body), True, key)
        else:
            if self.replay:
                raise CacheMiss(
                    f"replay: no cache file for pass {self.names[0]}, model {self.names[1]}, "
                    f"key {key} (under {self.cache_dir})"
                )
            body = self._post(request.payload)
            self._check_model(body, "the answer")
            self._write_cache(path, key, request, body)
            outcome = Outcome(read_body(body), False, key)
        self._note_served(outcome.answer)
        if self.log is not None:
            self.log(request, outcome, (time.perf_counter() - started) * 1000.0)
        return outcome

    def batch(self, requests: Sequence[Request]) -> list[Outcome]:
        """Answer many requests in a thread pool, results in request order.

        A failing call does not stop the others. An exception that is not an
        `LLMCallError` (a `CacheMiss`, a `CacheError`) is raised as it is once
        the pool is done; otherwise failures raise one `LLMCallError` whose
        `failures` lists `(index, exception)`.
        """
        if not requests:
            return []
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = [pool.submit(self.call, request) for request in requests]
        results: list[Outcome | None] = [None] * len(requests)
        failures: list[tuple[int, BaseException]] = []
        for index, future in enumerate(futures):
            exc = future.exception()
            if exc is None:
                results[index] = future.result()
            elif isinstance(exc, Exception):
                failures.append((index, exc))
            else:
                raise exc
        others = [exc for _, exc in failures if not isinstance(exc, LLMCallError)]
        if others:
            raise others[0]
        if failures:
            first_index, first = failures[0]
            raise LLMCallError(
                f"{len(failures)} of {len(requests)} calls failed "
                f"(first at index {first_index}: {first})",
                failures=failures,
            )
        return [result for result in results if result is not None]

    # -- the cache ---------------------------------------------------------

    @staticmethod
    def _read_cache(path: Path) -> Any:
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CacheError(
                f"the cache file {path} cannot be read as JSON: {exc}"
            ) from exc
        if not isinstance(stored, dict) or "response" not in stored:
            raise CacheError(f"the cache file {path} holds no response")
        return stored["response"]

    @staticmethod
    def _write_cache(path: Path, key: str, request: Request, body: Any) -> None:
        # Written to a file of its own, then renamed, so a reader never sees
        # a torn file and two writers of the same key never collide.
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f"{key}.{uuid4().hex}.tmp"
        text = json.dumps(
            {
                "cache_key": key,
                "kind": request.kind,
                "request": request.fields,
                "response": body,
            },
            ensure_ascii=False,
        )
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

    # -- the network -------------------------------------------------------

    def _post(self, payload: dict[str, Any]) -> Any:
        """POST the body; retry 429, 5xx and transport errors with backoff."""
        last_status: int | None = None
        last_error = "no attempt made"
        for attempt in range(self.max_retries + 1):
            try:
                response = self._http.post("/chat/completions", json=payload)
            except httpx.TransportError as exc:
                last_status = None
                last_error = f"transport error: {type(exc).__name__}: {exc}"
            else:
                if response.is_success:
                    try:
                        return response.json()
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        # A 2xx that is not JSON is an unreadable answer, not a retry.
                        return {"unparseable_body": response.text}
                last_status = response.status_code
                last_error = f"HTTP {response.status_code}: {response.text[:500]}"
                if response.status_code != 429 and response.status_code < 500:
                    raise LLMCallError(last_error, status_code=last_status)
            if attempt < self.max_retries:
                time.sleep(min(BACKOFF_BASE_S * (2**attempt), BACKOFF_CAP_S))
        raise LLMCallError(
            f"exhausted {self.max_retries} retries; last: {last_error}",
            status_code=last_status,
        )

    # -- the model that answered -------------------------------------------

    def _check_model(self, body: Any, what: str) -> None:
        if self.expect_model is None:
            return
        served = body.get("model") if isinstance(body, dict) else None
        if isinstance(served, str) and served not in self.expect_model:
            raise ModelMismatch(
                f"{what} comes from the model {served!r}, not one of {self.expect_model}"
            )

    def _note_served(self, answer: Answer) -> None:
        pair = (answer.model_served, answer.system_fingerprint)
        with self._lock:
            if self._first is None:
                self._first = pair
                return
            if pair == self._first or pair in self._warned:
                return
            self._warned.add(pair)
            change = {
                "first_model_served": self._first[0],
                "first_system_fingerprint": self._first[1],
                "model_served": pair[0],
                "system_fingerprint": pair[1],
            }
            self.changes.append(change)
        warnings.warn(
            ModelChangeWarning(
                f"pass {self.names[0]}, model {self.names[1]}: the endpoint answered as "
                f"{pair[0]!r} (fingerprint {pair[1]!r}), first as {self._first[0]!r} "
                f"(fingerprint {self._first[1]!r})"
            ),
            stacklevel=2,
        )
