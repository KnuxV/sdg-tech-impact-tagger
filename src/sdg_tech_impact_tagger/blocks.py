"""The block reader of prompt files and the hashes built on it (contract 3.2, 3.5)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from sdg_tech_impact_tagger.errors import QuestionError

# Contract 3.2: the reader of [WS] impact_pass.py with the name class widened.
BLOCK_RE = re.compile(
    r"^## ([A-Za-z0-9_.-]+)[ \t]*\n+```text\n(.*?)\n```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)

OPEN_MARKER = "[[OPEN"


def sha12(text: str) -> str:
    """The first 12 hex characters of the sha256 of `text` in UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def file_sha256(path: Path) -> str:
    """The hex sha256 of a file's bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_blocks(path: Path) -> dict[str, str]:
    """The blocks of a prompt file, name to body, in file order.

    Consumes the path of a markdown file; produces each `## NAME` fenced
    `text` block's body verbatim. Raises `QuestionError` when the file is
    missing or holds two blocks of the same name.
    """
    path = Path(path)
    if not path.is_file():
        raise QuestionError(f"the block file {path} does not exist")
    blocks: dict[str, str] = {}
    for name, body in BLOCK_RE.findall(path.read_text(encoding="utf-8")):
        if name in blocks:
            raise QuestionError(f"{path} holds two blocks named {name}")
        blocks[name] = body
    return blocks
