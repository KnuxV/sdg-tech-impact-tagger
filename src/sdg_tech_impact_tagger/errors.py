"""The exceptions and the warning of the package (contract section 11).

Every exception derives from `TaggerError`, so a caller can catch the
package's refusals in one clause. A refusal raised before the first call of
a run writes nothing.
"""

from __future__ import annotations


class TaggerError(Exception):
    """Base of every error the package raises on purpose."""


class WorkflowError(TaggerError):
    """The workflow file, or an argument of `run`, does not fit the contract."""


class QuestionError(TaggerError):
    """A question directory, or an answer model, does not fit the contract."""


class ListError(TaggerError):
    """A list file does not fit the contract (section 2.2)."""


class TextsError(TaggerError):
    """The texts table does not fit, is missing, or lacks a field `render` needs."""


class UnitsError(TaggerError):
    """A unit rule cannot build its units, or `render` was given a bad unit."""


class KeyMissing(TaggerError):
    """The environment variable holding a key is unset or empty in a live run."""


class ManifestMismatch(TaggerError):
    """`run.json` belongs to another run, or is missing under `combine_only`."""


class IncompleteRun(TaggerError):
    """Combine was asked while planned chunks are missing."""


class CombineError(TaggerError):
    """A chunk file does not fit the plan, the schema or the run."""


class LLMCallError(TaggerError):
    """A call, a batch or a sub-chunk failed.

    `status_code` is the last HTTP status of a failed call (None for a
    transport error or an aggregate); `failures` lists `(index, exception)`
    for the calls of a batch that failed.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        failures: list[tuple[int, BaseException]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.failures = list(failures or [])


class ModelMismatch(LLMCallError):
    """An answer, fresh or cached, came from a model outside `expect_model`."""


class CacheMiss(TaggerError):
    """In replay, a call is not in the cache."""


class CacheError(TaggerError):
    """A cache file cannot be read as JSON holding a `response`."""


class ModelChangeWarning(UserWarning):
    """The model served or its fingerprint changed within a run (D012)."""
