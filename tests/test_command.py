"""The command (contract 10.2), run through the installed entry point.

Every run here is a replay or a refusal: no command reaches a network.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import polars as pl
import pytest
from conftest import (
    FIXTURES,
    KEY_ENV,
    PACKAGE,
    RUN_ID_RE,
    SCORE_BLOCKS,
    Endpoint,
    assert_table,
    chat,
    copy_calls,
    model_entry,
    score_question,
    sha12,
    write_texts,
    write_workflow,
    write_works,
)

import sdg_tech_impact_tagger as tagger

# pip installs the command beside the interpreter, with `.exe` on Windows.
COMMAND = Path(sys.executable).parent / (
    "sdg-tech-impact-tagger.exe"
    if sys.platform == "win32"
    else "sdg-tech-impact-tagger"
)
GOOD = '{"RED": 10, "GREEN": 20, "BLUE": 30}'


def command(*args, cwd, env_extra=None, drop_key=True):
    env = {
        k: v
        for k, v in os.environ.items()
        if not (drop_key and k in {KEY_ENV, "UNISTRA_API_KEY"})
    }
    env.update(env_extra or {})
    return subprocess.run(
        [str(COMMAND), *map(str, args)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def listing(directory: Path) -> list[str]:
    return sorted(str(p.relative_to(directory)) for p in directory.rglob("*"))


def test_entry_point_is_installed():
    assert COMMAND.exists(), "[project.scripts] sdg-tech-impact-tagger is not installed"


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------


def score_project(tmp_path, key_env):
    """A one-pass workflow whose cache is filled by a live run from Python, then its outputs removed."""
    write_texts(tmp_path)
    score_question(tmp_path / "q")
    body = (
        model_entry()
        + '[[passes]]\nid = "p"\nquestion_dir = "q"\nmodels = ["m1"]\nunits = { rule = "all" }\n'
    )
    path = write_workflow(tmp_path, body)
    [result] = tagger.run(
        tagger.load_workflow(path),
        transport=Endpoint(lambda p, n: chat(GOOD)).transport,
    )
    table = pl.read_parquet(result.output)
    shutil.rmtree(tmp_path / "runs")
    return path, table


def test_run_a_workflow_file_in_replay(tmp_path, key_env):
    path, table = score_project(tmp_path, key_env)
    done = command("run", path, "--replay", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    replayed = pl.read_parquet(tmp_path / "runs" / "wf" / "p" / "m1.parquet")
    assert replayed.drop("run_id").equals(table.drop("run_id"))
    assert replayed["run_id"].to_list() == table["run_id"].to_list()
    # One line per (pass, model) result.
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    assert len(lines) == 1 and "p" in lines[0] and "m1" in lines[0]
    assert "test-secret" not in done.stdout + done.stderr


def test_run_options_reach_the_run(tmp_path, key_env):
    path, _ = score_project(tmp_path, key_env)
    shutil.move(tmp_path / "cache", tmp_path / "moved")
    other = tmp_path / "two.parquet"
    pl.read_parquet(tmp_path / "works.parquet").head(2).write_parquet(other)
    done = command(
        "run",
        path,
        "--replay",
        "--cache-dir",
        tmp_path / "moved",
        "--output-dir",
        tmp_path / "out",
        "--texts",
        other,
        "--pass",
        "p",
        "--model",
        "m1",
        "--worker",
        "w2",
        "--reverse",
        cwd=tmp_path,
    )
    assert done.returncode == 0, done.stderr
    table = pl.read_parquet(tmp_path / "out" / "p" / "m1.parquet")
    assert table["id"].unique().sort().to_list() == ["a1", "b2"]
    assert (tmp_path / "out" / "p" / "m1" / "calls" / "w2.jsonl").exists()


def test_run_limit(tmp_path, key_env):
    path, _ = score_project(tmp_path, key_env)
    done = command("run", path, "--replay", "--limit", "1", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    table = pl.read_parquet(tmp_path / "runs" / "wf" / "p" / "m1.parquet")
    assert table["id"].unique().to_list() == ["b2"]


def test_run_combine_only(tmp_path, key_env):
    path, table = score_project(tmp_path, key_env)
    assert command("run", path, "--replay", cwd=tmp_path).returncode == 0
    (tmp_path / "runs" / "wf" / "p" / "m1.parquet").unlink()
    shutil.rmtree(tmp_path / "cache")
    # Contract 6.7: combine_only never reads the key, with or without replay.
    done = command("run", path, "--combine-only", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert (
        pl.read_parquet(tmp_path / "runs" / "wf" / "p" / "m1.parquet")
        .drop("run_id")
        .equals(table.drop("run_id"))
    )


def test_run_replay_miss_exits_1(tmp_path, key_env):
    path, _ = score_project(tmp_path, key_env)
    shutil.rmtree(tmp_path / "cache")
    done = command("run", path, "--replay", cwd=tmp_path)
    assert done.returncode == 1
    assert done.stderr.strip()


def test_run_without_key_exits_1_naming_the_variable(tmp_path, key_env):
    path, _ = score_project(tmp_path, key_env)
    shutil.rmtree(tmp_path / "cache")
    done = command("run", path, cwd=tmp_path)
    assert done.returncode == 1
    assert KEY_ENV in done.stderr
    assert not (tmp_path / "runs").exists()


@pytest.mark.slow
def test_run_the_impact_preset_in_replay(tmp_path):
    base = FIXTURES / "protocol_impact"
    copy_calls(base / "calls", tmp_path / "store")
    write_works(tmp_path, "protocol_impact", "texts.parquet")
    done = command(
        "run",
        "--preset",
        "protocol-v1-impact",
        "--texts",
        "texts.parquet",
        "--replay",
        "--cache-dir",
        "store",
        "--output-dir",
        "out",
        cwd=tmp_path,
    )
    assert done.returncode == 0, done.stderr
    tables = [
        (pass_id, model)
        for pass_id in ("sdg_pass1", "sdg_pass2", "adt_pass1", "adt_pass2")
        for model in (
            ("qwen3", "gemma") if pass_id.startswith("sdg") else ("gemma", "qwen3")
        )
    ] + [("impact", "coder"), ("impact", "gemma_thinking")]
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    assert len(lines) == len(tables)
    for (pass_id, model), line in zip(tables, lines, strict=True):
        assert pass_id in line and model in line
        assert_table(
            pl.read_parquet(tmp_path / "out" / pass_id / f"{model}.parquet"),
            base / "expected" / f"{pass_id}__{model}.json",
        )
    assert not (tmp_path / "cache").exists()


# --------------------------------------------------------------------------
# usage errors (exit 2) and refusals (exit 1)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["fly"],
        ["run"],
        ["run", "workflow.toml", "--preset", "protocol-v1"],
        ["run", "--preset", "protocol-v1", "--limit", "many"],
        ["run", "--preset", "protocol-v1", "--no-such-option"],
        ["preset"],
        ["prompt"],
    ],
    ids=lambda a: " ".join(a) or "nothing",
)
def test_usage_errors_exit_2(tmp_path, args):
    done = command(*args, cwd=tmp_path)
    assert done.returncode == 2, (done.stdout, done.stderr)


def test_a_bad_workflow_exits_1(tmp_path):
    (tmp_path / "workflow.toml").write_text(
        '[run]\nname = "wf"\nthreads = 4\n', encoding="utf-8"
    )
    done = command("check", "workflow.toml", cwd=tmp_path)
    assert done.returncode == 1
    assert "threads" in done.stderr


def test_an_unknown_preset_exits_1(tmp_path):
    done = command("preset", "protocol-v9", cwd=tmp_path)
    assert done.returncode == 1


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------


def test_check_prints_ids_and_counts_and_writes_nothing(tmp_path):
    write_works(tmp_path, "protocol_impact", "texts.parquet")
    before = listing(tmp_path)
    done = command(
        "check",
        "--preset",
        "protocol-v1-impact",
        "--texts",
        "texts.parquet",
        cwd=tmp_path,
    )
    assert done.returncode == 0, done.stderr
    assert listing(tmp_path) == before
    out = done.stdout
    assert "sdgp1-ca9ecbb1733d" in out
    assert "adtp1-eb4f16256516+adtdesc-e8f65488c44f" in out
    assert any(RUN_ID_RE.match(word) for word in out.replace(",", " ").split())


def test_check_a_workflow_file(tmp_path, key_env):
    path, _ = score_project(tmp_path, key_env)
    shutil.rmtree(tmp_path / "cache")
    before = listing(tmp_path)
    done = command("check", path, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert listing(tmp_path) == before
    # The id write_question gave the colour question (contract 3.5), and three units.
    prompt_id = "tq-" + sha12(SCORE_BLOCKS["SYS"] + "\n" + SCORE_BLOCKS["USR"])
    assert prompt_id in done.stdout
    assert "3" in done.stdout
    assert any(RUN_ID_RE.match(word) for word in done.stdout.replace(",", " ").split())


# --------------------------------------------------------------------------
# prompt
# --------------------------------------------------------------------------


PROMPT_CASES = {
    # question: (list ids, side names)
    "protocol_v1/sdg_pass1": ((), ()),
    "protocol_v1/sdg_pass2": (("sdg",), ()),
    "protocol_v1/adt_pass2": (("adt",), ()),
    "impact/p3_2": (("adt", "sdg"), ("pos", "neg")),
}


def expected_prompt(question: str, codes: tuple[str, ...]) -> str:
    """Contract 10.2: every call of the unit, each as the [OA] print, one empty line between."""
    lists, sides = PROMPT_CASES[question]
    loaded = tagger.load_question(question)
    texts = {field: f"<{field}>" for field in loaded.text_fields}
    calls = loaded.render(texts, [codes] if codes else [])
    ids = dict(loaded.prompt_ids)
    prompt_id = ids[codes[0]] if codes and codes[0] in ids else ids[""]
    header = f"prompt {prompt_id}"
    for list_id, code in zip(lists, codes, strict=True):
        header += f", {list_id} {code}"
    headers = [header + f", side {side}" for side in sides] if sides else [header]
    assert len(headers) == len(calls)
    return "\n".join(
        f"{h}\n\n--- system ---\n{system}\n\n--- user ---\n{user}\n"
        for h, (system, user) in zip(headers, calls, strict=True)
    )


@pytest.mark.parametrize(
    ("question", "codes"),
    [
        ("protocol_v1/sdg_pass1", ()),
        ("protocol_v1/sdg_pass2", ("SDG-13",)),
        ("protocol_v1/adt_pass2", ("BLOCKCHAIN",)),
        ("impact/p3_2", ("IOT", "SDG-07")),
    ],
)
def test_prompt_prints_every_call_of_the_unit(tmp_path, question, codes):
    args = ["prompt", question]
    for flag, code in zip(("--a", "--b"), codes, strict=False):
        args += [flag, code]
    done = command(*args, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert done.stdout.rstrip("\n") == expected_prompt(question, codes).rstrip("\n")
    assert "<title>" in done.stdout and "<abstract>" in done.stdout
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("question", "codes"),
    [("protocol_v1/sdg_pass2", ("SDG-01",)), ("impact/p3_2", ("AI", "SDG-01"))],
)
def test_prompt_defaults_to_the_first_label_of_each_list(tmp_path, question, codes):
    done = command("prompt", question, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert done.stdout.rstrip("\n") == expected_prompt(question, codes).rstrip("\n")


def test_prompt_with_a_code_not_in_the_list_exits_1(tmp_path):
    done = command("prompt", "protocol_v1/sdg_pass2", "--a", "SDG-18", cwd=tmp_path)
    assert done.returncode == 1


# --------------------------------------------------------------------------
# preset
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["protocol-v1", "protocol-v1-impact", "paper-v1"])
def test_preset_prints_its_toml(tmp_path, name):
    done = command("preset", name, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    shipped = (PACKAGE / "presets" / f"{name}.toml").read_text(encoding="utf-8")
    assert tomllib.loads(done.stdout) == tomllib.loads(shipped)
    # Printed to copy and edit: saved as a file, it loads.
    (tmp_path / "copy.toml").write_text(done.stdout, encoding="utf-8")
    tagger.load_workflow(tmp_path / "copy.toml")
    assert listing(tmp_path) == ["copy.toml"]
