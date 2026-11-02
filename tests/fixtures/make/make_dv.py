"""Freeze the fixtures whose oracle is divergence-validation ([DV]).

Run after make_oa.py, with the interpreter of that repository, read-only:

    /home/knuxv/Codebase/divergence-validation/.venv/bin/python -B tests/fixtures/make/make_dv.py

What it writes, under tests/fixtures/:

- render/impact__p2.json, render/impact__p2_reasoning.json: the text of each
  call, a null abstract formatted as [DV] did (`None`);
- dv/calls/, dv/expected/p2__<entry>.json: the logprob layer of impact/p2 on
  a file of units, read with the exact spelling;
- dv/expected/p2_reasoning__gemma.json: the reasoning layer, letter_text with
  the [DV] budget rule;
- protocol_impact/expected/sdg_pass2__qwen3__exact.json: the [OA] cache of
  SDG pass 2 read again with the exact spelling of the [DV] client.

The [DV] client reads one probability, `p_yes`; `p_n` is the same formula
with the letters swapped, exp(N) / (exp(Y) + exp(N)), 1.0 or 0.0 when one
letter alone is present.
"""

from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DV = HERE.parents[3] / "divergence-validation"
sys.path.insert(0, str(DV / "src"))
sys.path.insert(0, str(HERE))

import httpx
import polars as pl
from divergence_based_validation.llm.client import LLMClient
from divergence_based_validation.stages import labels_p3
from divergence_based_validation.stages.labels_p1 import _build_requests, load_prompts
from inputs import (
    ADT_NAMES,
    DV_UNITS,
    FIXTURES,
    NON_JSON,
    QUESTIONS,
    SDG_NAMES,
    WORK_BY_ID,
    WORKS,
    dv_p2_answer,
    dv_p3_answer,
    served_of,
    table_fixture,
    write_json,
)

P2 = QUESTIONS / "impact" / "p2" / "p2.md"
CALL_COLUMNS = ["model", "model_served", "system_fingerprint", "prompt_id", "run_id"]
CALL_DTYPES = ["String", "String", "String", "String"]
ROOT = FIXTURES / "dv"


def transport(table):
    def handler(request):
        payload = json.loads(request.content)
        key = (
            payload["messages"][0]["content"],
            payload["messages"][1]["content"],
            payload["max_tokens"],
        )
        return httpx.Response(200, json=table[key])

    return httpx.MockTransport(handler)


def reader():
    return LLMClient(
        base_url="http://oracle.invalid", api_key="x", cache_dir=Path("/nonexistent")
    )


def p_n_exact(body, extraction="first_token"):
    """`p_n` by the [DV] formula with the letters swapped."""
    parsed = reader()._parse_single_token(body, "k", True, extraction)
    lp_y, lp_n = parsed.top_logprobs.get("Y"), parsed.top_logprobs.get("N")
    if lp_y is None and lp_n is None:
        return None
    if lp_y is None:
        return 1.0
    if lp_n is None:
        return 0.0
    return math.exp(lp_n) / (math.exp(lp_y) + math.exp(lp_n))


def joined(values):
    found = sorted({v for v in values if v is not None})
    return "|".join(found) if found else None


def pairs_frame():
    rows = []
    for work_id, adt, sdg in DV_UNITS:
        work = WORK_BY_ID[work_id]
        rows.append(
            {
                "wos_id": work_id,
                "adt": adt,
                "sdg": sdg,
                "title": work["title"],
                "abstract": work["abstract"],
            }
        )
    return pl.DataFrame(
        rows,
        schema={
            "wos_id": pl.String,
            "adt": pl.String,
            "sdg": pl.String,
            "title": pl.String,
            "abstract": pl.String,
        },
    )


def render_fixtures():
    texts_cases = [
        {"title": WORKS[1]["title"], "abstract": WORKS[1]["abstract"]},
        {"title": WORKS[3]["title"], "abstract": None},
        {"title": "<title>", "abstract": "<abstract>"},
    ]
    for name, prefix, expected_id in (
        ("impact/p2", "p2", "p2-ed1dd92de43c"),
        ("impact/p2_reasoning", "p3", "p3-ed1dd92de43c"),
    ):
        prompts, prompt_id = load_prompts(P2, prefix=prefix)
        assert prompt_id == expected_id, prompt_id
        cases = []
        for texts in texts_cases:
            for units in (
                [["AI", "SDG-07"], ["ROBOTICS", "SDG-13"]],
                [["BLOCKCHAIN", "SDG-01"]],
            ):
                frame = pl.DataFrame(
                    [{"wos_id": "x", "adt": a, "sdg": s, **texts} for a, s in units],
                    schema={
                        "wos_id": pl.String,
                        "adt": pl.String,
                        "sdg": pl.String,
                        "title": pl.String,
                        "abstract": pl.String,
                    },
                )
                reqs, _ = _build_requests(
                    frame, "m", {}, prompts, 42, ADT_NAMES, SDG_NAMES
                )
                # [DV] formats a null as the four characters None: null_text = "None".
                cases.append(
                    {
                        "texts": texts,
                        "units": units,
                        "null_text": "None",
                        "calls": [[r.system, r.user] for r in reqs],
                    }
                )
        write_json(
            FIXTURES / "render" / (name.replace("/", "__") + ".json"),
            {"question": name, "cases": cases},
        )


def p2_layer():
    calls = ROOT / "calls"
    if calls.exists():
        shutil.rmtree(calls)
    prompts, prompt_id = load_prompts(P2, prefix="p2")
    pairs = pairs_frame()
    for entry, model in (("gemma", "gemma"), ("mistral_small", "mistral-small")):
        reqs, meta = _build_requests(
            pairs, model, {}, prompts, 42, ADT_NAMES, SDG_NAMES
        )
        table = {}
        for req, m in zip(reqs, meta, strict=True):
            unit = (m["wos_id"], m["adt"], m["sdg"])
            table[(req.system, req.user, req.max_tokens)] = dv_p2_answer(
                entry, unit, m["dimension"]
            )
        client = LLMClient(
            base_url="http://oracle.invalid/api",
            api_key="oracle",
            cache_dir=calls,
            concurrency=1,
            transport=transport(table),
        )
        results = client.run_batch(reqs, batch_id=f"p2-{model}")
        rows = []
        for n, unit in enumerate(DV_UNITS):
            pos, neg = results[2 * n], results[2 * n + 1]
            bodies = [dv_p2_answer(entry, unit, side) for side in ("pos", "neg")]
            served = [served_of(b) for b in bodies]
            rows.append(
                [
                    unit[0],
                    f"{unit[1]}|{unit[2]}",
                    unit[1],
                    unit[2],
                    1,
                    model,
                    joined(s[0] for s in served),
                    joined(s[1] for s in served),
                    prompt_id,
                    pos.label,
                    neg.label,
                    pos.p_yes,
                    p_n_exact(bodies[0]),
                    neg.p_yes,
                    p_n_exact(bodies[1]),
                    pos.tokens_in,
                    pos.tokens_out,
                    neg.tokens_in,
                    neg.tokens_out,
                    pos.tokens_in + neg.tokens_in,
                    pos.tokens_out + neg.tokens_out,
                    "OTHER" in (pos.label, neg.label),
                ]
            )
        rows.sort(key=lambda r: (r[0], r[1]))
        columns = [
            "id",
            "code",
            "adt",
            "sdg",
            "repeat",
            *CALL_COLUMNS,
            "pos_label",
            "neg_label",
            "pos_p_y",
            "pos_p_n",
            "neg_p_y",
            "neg_p_n",
            "pos_tokens_in",
            "pos_tokens_out",
            "neg_tokens_in",
            "neg_tokens_out",
            "tokens_in",
            "tokens_out",
            "parse_failure",
        ]
        dtypes = (
            ["String"] * 4
            + ["Int64", *CALL_DTYPES, "String", "String"]
            + ["Float64"] * 4
            + ["Int64"] * 6
            + ["Boolean"]
        )
        write_json(
            ROOT / "expected" / f"p2__{entry}.json",
            table_fixture(columns, dtypes, rows),
        )
    write_json(
        ROOT / "works.json",
        {
            "columns": ["id", "title", "abstract"],
            "rows": [[w["id"], w["title"], w["abstract"]] for w in WORKS],
        },
    )
    (ROOT / "units.csv").write_text(
        "id,adt,sdg\n" + "".join(f"{w},{a},{s}\n" for w, a, s in reversed(DV_UNITS)),
        encoding="utf-8",
    )


def p3_layer():
    calls = ROOT / "calls"
    prompts, prompt_id = load_prompts(P2, prefix="p3")
    pairs = pairs_frame()
    cfg = {
        "max_tokens": 4000,
        "top_logprobs": 0,
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": True},
            "logprobs": False,
        },
    }
    reqs, meta = _build_requests(pairs, "gemma", cfg, prompts, 42, ADT_NAMES, SDG_NAMES)
    table = {}
    for req, m in zip(reqs, meta, strict=True):
        unit = (m["wos_id"], m["adt"], m["sdg"])
        table[(req.system, req.user, 4000)] = dv_p3_answer(unit, m["dimension"], 1)
        table[(req.system, req.user, 12000)] = dv_p3_answer(unit, m["dimension"], 2)
    params = {
        "llm": {"base_url": "http://oracle.invalid/api"},
        "api_key": "oracle",
        "labels_p3": {
            "chunk_size": 100,
            "passes": 1,
            "concurrency": 1,
            "timeout_s": 5.0,
        },
    }
    _used, results, again = labels_p3._label_model(
        "gemma", reqs, 12000, params, calls, transport(table)
    )
    retried = set(again)
    rows = []
    for n, unit in enumerate(DV_UNITS):
        pos, neg = results[2 * n], results[2 * n + 1]
        bodies = [
            dv_p3_answer(unit, side, 2 if 2 * n + k in retried else 1)
            for k, side in enumerate(("pos", "neg"))
        ]
        served = [served_of(b) for b in bodies]
        rows.append(
            [
                unit[0],
                f"{unit[1]}|{unit[2]}",
                unit[1],
                unit[2],
                1,
                "gemma",
                joined(s[0] for s in served),
                joined(s[1] for s in served),
                prompt_id,
                pos.label,
                neg.label,
                2 * n in retried,
                2 * n + 1 in retried,
                pos.tokens_in,
                pos.tokens_out,
                neg.tokens_in,
                neg.tokens_out,
                pos.tokens_in + neg.tokens_in,
                pos.tokens_out + neg.tokens_out,
                "OTHER" in (pos.label, neg.label),
            ]
        )
    rows.sort(key=lambda r: (r[0], r[1]))
    columns = [
        "id",
        "code",
        "adt",
        "sdg",
        "repeat",
        *CALL_COLUMNS,
        "pos_label",
        "neg_label",
        "pos_retried",
        "neg_retried",
        "pos_tokens_in",
        "pos_tokens_out",
        "neg_tokens_in",
        "neg_tokens_out",
        "tokens_in",
        "tokens_out",
        "parse_failure",
    ]
    dtypes = (
        ["String"] * 4
        + ["Int64", *CALL_DTYPES, "String", "String", "Boolean", "Boolean"]
        + ["Int64"] * 6
        + ["Boolean"]
    )
    write_json(
        ROOT / "expected" / "p2_reasoning__gemma.json",
        table_fixture(columns, dtypes, rows),
    )


def exact_reread():
    """The qwen3 SDG pass 2 cache of make_oa.py read with the [DV] exact spelling."""
    base = FIXTURES / "protocol_impact"
    keys = json.loads((base / "sdg_pass2_keys.json").read_text("utf-8"))["qwen3"]
    first = json.loads((base / "expected" / "sdg_pass2__qwen3.json").read_text("utf-8"))
    columns = first["columns"]
    names = [c for c in columns if c != "run_id"]
    rows = []
    for row in first["rows"]:
        record = dict(zip(names, row, strict=True))
        key = keys[f"{record['id']}|{record['code']}"]
        body = json.loads(
            (base / "calls" / key[:2] / f"{key}.json").read_text("utf-8")
        )["response"]
        parsed = reader()._parse_single_token(body, key, True)
        assert parsed.label == record["label"]
        record["p_y"] = parsed.p_yes
        record["p_n"] = p_n_exact(body)
        rows.append([record[c] for c in names])
    write_json(
        base / "expected" / "sdg_pass2__qwen3__exact.json",
        table_fixture(columns, first["dtypes"], rows),
    )


def main():
    assert NON_JSON
    render_fixtures()
    p2_layer()
    p3_layer()
    exact_reread()
    print("make_dv: done")


if __name__ == "__main__":
    main()
