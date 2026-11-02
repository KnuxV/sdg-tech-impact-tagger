"""The command `sdg-tech-impact-tagger` (contract 10.2): run, check, prompt, preset.

Exit status 0 when every asked pass finished or waits on chunks of other
workers, 1 on any refusal of the package (`TaggerError`, its message on
standard error, never a key), 2 on a usage error.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections.abc import Sequence
from pathlib import Path

from sdg_tech_impact_tagger.errors import TaggerError, WorkflowError
from sdg_tech_impact_tagger.questions import load_question
from sdg_tech_impact_tagger.runner import check_lines, run
from sdg_tech_impact_tagger.workflow import (
    PRESETS,
    PRESETS_DIR,
    Workflow,
    load_workflow,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdg-tech-impact-tagger",
        description="Label texts with an LLM by versioned questions and declarative workflows.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run_cmd = commands.add_parser("run", help="run a workflow or a preset")
    run_cmd.add_argument("workflow", nargs="?", help="the workflow TOML file")
    run_cmd.add_argument("--preset", help="a shipped preset instead of a file")
    run_cmd.add_argument("--texts", help="the texts parquet (overrides [run].texts)")
    run_cmd.add_argument(
        "--replay", action="store_true", help="no network: every call from the cache"
    )
    run_cmd.add_argument(
        "--pass", dest="passes", action="append", help="run only this pass"
    )
    run_cmd.add_argument(
        "--model", dest="models", action="append", help="run only this model"
    )
    run_cmd.add_argument("--limit", type=int, help="keep the first N works")
    run_cmd.add_argument(
        "--worker", default="main", help="the worker name of the claims"
    )
    run_cmd.add_argument(
        "--reverse", action="store_true", help="visit chunks from the last"
    )
    run_cmd.add_argument(
        "--combine-only", action="store_true", help="combine, make no call"
    )
    run_cmd.add_argument("--output-dir", help="overrides [run].output_dir")
    run_cmd.add_argument("--cache-dir", help="overrides [run].cache_dir")

    check_cmd = commands.add_parser(
        "check", help="check a workflow and plan it; no call"
    )
    check_cmd.add_argument("workflow", nargs="?", help="the workflow TOML file")
    check_cmd.add_argument("--preset", help="a shipped preset instead of a file")
    check_cmd.add_argument("--texts", help="the texts parquet (overrides [run].texts)")

    prompt_cmd = commands.add_parser("prompt", help="print the calls of one unit")
    prompt_cmd.add_argument(
        "question", help="a shipped question name or a question directory"
    )
    prompt_cmd.add_argument("--a", dest="code_a", help="the code of list a")
    prompt_cmd.add_argument("--b", dest="code_b", help="the code of list b")

    preset_cmd = commands.add_parser("preset", help="print a preset's TOML")
    preset_cmd.add_argument("name", help=f"one of {', '.join(PRESETS)}")
    return parser


def _workflow(parser: argparse.ArgumentParser, args: argparse.Namespace) -> Workflow:
    if (args.workflow is None) == (args.preset is None):
        parser.error("give exactly one of WORKFLOW and --preset")
    if args.preset is not None:
        return load_workflow(preset=args.preset)
    return load_workflow(args.workflow)


def _run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    workflow = _workflow(parser, args)
    changes = {}
    if args.output_dir:
        changes["output_dir"] = Path(args.output_dir).absolute()
    if args.cache_dir:
        changes["cache_dir"] = Path(args.cache_dir).absolute()
    if changes:
        workflow = dataclasses.replace(workflow, **changes)
    results = run(
        workflow,
        texts=Path(args.texts) if args.texts else None,
        replay=args.replay,
        passes=args.passes,
        models=args.models,
        limit=args.limit,
        worker=args.worker,
        reverse=args.reverse,
        combine_only=args.combine_only,
    )
    for result in results:
        if result.output_written:
            state = f"written {result.output}"
        elif result.missing:
            state = f"waiting on chunks {result.missing} held by other workers"
        else:
            state = "not run: a source table was not written"
        print(
            f"{result.pass_id} {result.model}: {result.units} units, {result.chunks} chunks, "
            f"{len(result.written)} answered, {len(result.skipped_on_disk)} on disk; {state}"
        )
    return 0


def _check(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    workflow = _workflow(parser, args)
    for line in check_lines(workflow, Path(args.texts) if args.texts else None):
        print(line)
    return 0


def _prompt(args: argparse.Namespace) -> int:
    question = load_question(args.question)
    texts = {name: f"<{name}>" for name in question.text_fields}
    sides = ["a", "b"][
        : {"work": 0, "work x list": 1, "work x list x list": 2}[question.level]
    ]
    given = {"a": args.code_a, "b": args.code_b}
    codes = tuple(given[s] or question.label_lists[s].codes[0] for s in sides)
    calls = question.render(texts, [codes] if codes else [])
    ids = question.prompt_ids
    header = f"prompt {ids[codes[0]] if codes and codes[0] in ids else ids['']}"
    for side, code in zip(sides, codes, strict=True):
        header += f", {question.lists[side]} {code}"
    if question.side_names and len(calls) == len(question.side_names):
        headers = [f"{header}, side {name}" for name in question.side_names]
    else:
        headers = [header] * len(calls)
    print(
        "\n".join(
            f"{h}\n\n--- system ---\n{system}\n\n--- user ---\n{user}\n"
            for h, (system, user) in zip(headers, calls, strict=True)
        ),
        end="",
    )
    return 0


def _preset(args: argparse.Namespace) -> int:
    if args.name not in PRESETS:
        raise WorkflowError(f"no preset {args.name!r}; shipped: {', '.join(PRESETS)}")
    print((PRESETS_DIR / f"{args.name}.toml").read_text(encoding="utf-8"), end="")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; return the exit status (0, 1 on a refusal, 2 on usage)."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return _run(parser, args)
        if args.command == "check":
            return _check(parser, args)
        if args.command == "prompt":
            return _prompt(args)
        return _preset(args)
    except TaggerError as exc:
        print(f"sdg-tech-impact-tagger: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
