"""Freeze the fixtures whose oracle is wos_paper_sample ([WS]).

Run after make_oa.py, with the interpreter of that repository, read-only:

    /home/knuxv/Codebase/wos_paper_sample/.venv/bin/python -B tests/fixtures/make/make_ws.py

It imports the earlier code by path. What it writes, under tests/fixtures/:

- render/impact__p3_2.json, render/paper__*.json: the text of each call;
- protocol_impact/calls/: the cache files of the impact pass (P3.2) for the
  model entries `coder` and `gemma_thinking`, units crossed by [WS] from the
  pass 2 tables that make_oa.py froze;
- protocol_impact/expected/impact__<entry>.json: their tables;
- paper/calls/, paper/expected/: the paper passes of the preset paper-v1;
- units/cross.json: cross and file units with flags, as [WS] selects them.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[3] / "wos_paper_sample"
sys.path.insert(0, str(WS / "src"))
sys.path.insert(0, str(HERE))

import httpx
import polars as pl
from inputs import (
    ADT_NAMES,
    FIXTURES,
    IMPACT_BUDGETS,
    PAPER_WORKS,
    QUESTIONS,
    SDG_NAMES,
    WORK_BY_ID,
    WORKS,
    impact_answer,
    paper_answer,
    paper_impact_answer,
    served_of,
    table_fixture,
    write_json,
)
from wos_paper_sample import impact_pass, llm_passes, paper_pass
from wos_paper_sample.llm.client import LLMClient

P32 = QUESTIONS / "impact" / "p3_2" / "impact_p3_2.md"
TARGETS = QUESTIONS / "impact" / "p3_2" / "impact_sdg_targets.json"
PREAMBLE = QUESTIONS / "paper" / "impact_v1" / "impact_p3_2_work.md"
PAPER_FILES = {
    "adt": QUESTIONS / "paper" / "adt_v1" / "paper_adt_v1.md",
    "sdg": QUESTIONS / "paper" / "sdg_v1" / "paper_sdg_v1.md",
}
CALL_COLUMNS = ["model", "model_served", "system_fingerprint", "prompt_id", "run_id"]
CALL_DTYPES = ["String", "String", "String", "String"]
SCHEMA = {"id": pl.String, "title": pl.String, "abstract": pl.String}


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


def client(table, cache):
    return LLMClient(
        base_url="http://oracle.invalid/api",
        api_key="oracle",
        cache_dir=cache,
        concurrency=1,
        transport=transport(table),
    )


def documents(ids=None):
    works = WORKS if ids is None else [WORK_BY_ID[i] for i in ids]
    return llm_passes.stage_documents(pl.DataFrame(works, schema=SCHEMA))


def load_expected(name):
    data = json.loads(
        (FIXTURES / "protocol_impact" / "expected" / f"{name}.json").read_text("utf-8")
    )
    columns = [c for c in data["columns"] if c != "run_id"]
    return pl.DataFrame(
        [dict(zip(columns, row, strict=True)) for row in data["rows"]],
        infer_schema_length=None,
    ).rename({"id": "wos_id"})


def joined(values):
    found = sorted({v for v in values if v is not None})
    return "|".join(found) if found else None


def impact_blocks_and_ids():
    blocks = impact_pass.impact_blocks(P32)
    targets_text = TARGETS.read_text(encoding="utf-8")
    prompt_id = impact_pass.impact_prompt_id(blocks, targets_text, prefix="p3.2")
    return blocks, json.loads(targets_text)["targets"], prompt_id, targets_text


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def render_fixtures():
    blocks, targets, _, targets_text = impact_blocks_and_ids()
    texts_cases = [
        {"title": WORKS[1]["title"], "abstract": WORKS[1]["abstract"]},
        {"title": WORKS[3]["title"], "abstract": None},
        {"title": "<title>", "abstract": "<abstract>"},
    ]
    settings = {"max_tokens": 6000, "top_logprobs": 0, "extra_body": {}}

    def doc_frame(texts):
        return pl.DataFrame(
            [{"wos_id": "x", **texts}],
            schema={"wos_id": pl.String, "title": pl.String, "abstract": pl.String},
        )

    def p32(texts, units):
        frame = pl.DataFrame(
            {
                "wos_id": ["x"] * len(units),
                "adt": [u[0] for u in units],
                "sdg": [u[1] for u in units],
            },
            schema={"wos_id": pl.String, "adt": pl.String, "sdg": pl.String},
        )
        reqs = impact_pass.impact_requests(
            frame,
            doc_frame(texts),
            blocks,
            targets,
            ADT_NAMES,
            SDG_NAMES,
            "m",
            42,
            settings,
        )
        return [[r.system, r.user] for r in reqs]

    def labels(exercise):
        def render(texts, units):
            b = paper_pass.labels_blocks(PAPER_FILES[exercise])
            req = paper_pass.labels_request(
                texts, b, "m", 42, {"max_tokens": 1, "extra_body": {}}
            )
            return [[req.system, req.user]]

        return render

    preamble = paper_pass.work_preamble(PREAMBLE)

    def work(texts, units):
        frame = pl.DataFrame(
            {"adt": [u[0] for u in units], "sdg": [u[1] for u in units]}
        )
        ordered = paper_pass.pair_order(frame)
        pairs = list(zip(ordered["adt"], ordered["sdg"], strict=True))
        req = paper_pass.work_request(
            texts,
            pairs,
            preamble,
            blocks,
            targets,
            ADT_NAMES,
            SDG_NAMES,
            "m",
            42,
            {"max_tokens": 1, "extra_body": {}},
        )
        return [[req.system, req.user]]

    specs = [
        (
            "impact/p3_2",
            p32,
            [[["AI", "SDG-07"], ["ROBOTICS", "SDG-13"]], [["BLOCKCHAIN", "SDG-01"]]],
        ),
        ("paper/adt_v1", labels("adt"), [[]]),
        ("paper/sdg_v1", labels("sdg"), [[]]),
        (
            "paper/impact_v1",
            work,
            [
                [["ROBOTICS", "SDG-03"], ["AI", "SDG-07"], ["AI", "SDG-03"]],
                [["IOT", "SDG-11"]],
            ],
        ),
    ]
    for name, render, unit_sets in specs:
        cases = []
        for texts in texts_cases:
            for units in unit_sets:
                cases.append(
                    {
                        "texts": texts,
                        "units": units,
                        "null_text": "",
                        "calls": render(texts, [tuple(u) for u in units]),
                    }
                )
        write_json(
            FIXTURES / "render" / (name.replace("/", "__") + ".json"),
            {"question": name, "cases": cases},
        )
    # The ids the [WS] code computes, to be checked against IDS.tsv by the tests.
    paper_ids = {
        "paper/adt_v1": paper_pass.labels_prompt_id(
            paper_pass.labels_blocks(PAPER_FILES["adt"]), "adt"
        ),
        "paper/sdg_v1": paper_pass.labels_prompt_id(
            paper_pass.labels_blocks(PAPER_FILES["sdg"]), "sdg"
        ),
        "paper/impact_v1": paper_pass.work_prompt_id(preamble, blocks, targets_text),
        "impact/p3_2": impact_pass.impact_prompt_id(
            blocks, targets_text, prefix="p3.2"
        ),
        "impact/p3_2 as p3.1": impact_pass.impact_prompt_id(
            blocks, targets_text, prefix="p3.1"
        ),
    }
    assert paper_ids["impact/p3_2"] == "p3.2-f72f01757eef", paper_ids
    assert paper_ids["paper/impact_v1"] == "p3.2w-50ba3b728c25", paper_ids
    assert paper_ids["paper/adt_v1"] == "adt1-d95d2cfc8f17", paper_ids
    assert paper_ids["paper/sdg_v1"] == "sdg1-042b7b2c693f", paper_ids


# --------------------------------------------------------------------------
# the impact pass of protocol-v1-impact
# --------------------------------------------------------------------------

IMPACT_ENTRIES = {
    "coder": ("coder", {"logprobs": False}),
    "gemma_thinking": (
        "gemma",
        {"chat_template_kwargs": {"enable_thinking": True}, "logprobs": False},
    ),
}


def impact():
    calls = FIXTURES / "protocol_impact" / "calls"
    docs = documents()
    blocks, targets, prompt_id, _ = impact_blocks_and_ids()
    adt = {m: load_expected(f"adt_pass2__{m}") for m in ("gemma", "qwen3")}
    sdg = {m: load_expected(f"sdg_pass2__{m}") for m in ("gemma", "qwen3")}
    units = impact_pass.impact_units(docs, adt, sdg, ["E", "A", "T", "M"], ["Y"])
    flags = [c for c in units.columns if c.startswith(("adt_", "sdg_"))]
    assert flags == ["adt_gemma", "adt_qwen3", "sdg_gemma", "sdg_qwen3"], flags
    unit_keys = [(r["wos_id"], r["adt"], r["sdg"]) for r in units.iter_rows(named=True)]
    for entry, (model, extra_body) in IMPACT_ENTRIES.items():
        first, retry = IMPACT_BUDGETS[entry]
        settings = {
            "max_tokens": first,
            "retry_max_tokens": retry,
            "top_logprobs": 0,
            "extra_body": extra_body,
        }
        reqs = impact_pass.impact_requests(
            units, docs, blocks, targets, ADT_NAMES, SDG_NAMES, model, 42, settings
        )
        table = {}
        for n, req in enumerate(reqs):
            unit, side = unit_keys[n // 2], ("pos", "neg")[n % 2]
            table[(req.system, req.user, first)] = impact_answer(entry, unit, side, 1)
            table[(req.system, req.user, retry)] = impact_answer(entry, unit, side, 2)
        frame = impact_pass.impact_answers(
            client(table, calls),
            units,
            docs,
            blocks,
            targets,
            ADT_NAMES,
            SDG_NAMES,
            model,
            42,
            settings,
            prompt_id,
            f"impact-{model}",
        )
        rows = []
        for row in frame.iter_rows(named=True):
            unit = (row["wos_id"], row["adt"], row["sdg"])
            bodies = {
                side: impact_answer(
                    entry, unit, side, 2 if row[f"{side}_retried"] else 1
                )
                for side in ("pos", "neg")
            }
            usage = {side: bodies[side]["usage"] for side in bodies}
            assert (
                row["tokens_in"]
                == usage["pos"]["prompt_tokens"] + usage["neg"]["prompt_tokens"]
            )
            assert (
                row["tokens_out"]
                == usage["pos"]["completion_tokens"] + usage["neg"]["completion_tokens"]
            )
            served = [served_of(bodies[s]) for s in ("pos", "neg")]
            rows.append(
                [
                    row["wos_id"],
                    row["code"],
                    row["adt"],
                    row["sdg"],
                    *[row[f] for f in flags],
                    1,
                    model,
                    joined(s[0] for s in served),
                    joined(s[1] for s in served),
                    row["prompt_id"],
                    row["pos_label"],
                    row["neg_label"],
                    row["pos_retried"],
                    row["neg_retried"],
                    usage["pos"]["prompt_tokens"],
                    usage["pos"]["completion_tokens"],
                    usage["neg"]["prompt_tokens"],
                    usage["neg"]["completion_tokens"],
                    row["tokens_in"],
                    row["tokens_out"],
                    row["parse_failure"],
                ]
            )
        rows.sort(key=lambda r: (r[0], r[1]))
        columns = [
            "id",
            "code",
            "adt",
            "sdg",
            *flags,
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
            + ["Boolean"] * len(flags)
            + ["Int64", *CALL_DTYPES, "String", "String", "Boolean", "Boolean"]
            + ["Int64"] * 6
            + ["Boolean"]
        )
        write_json(
            FIXTURES / "protocol_impact" / "expected" / f"impact__{entry}.json",
            table_fixture(columns, dtypes, rows),
        )
    # The plan order: agreed units first, each part by id then code.
    write_json(
        FIXTURES / "protocol_impact" / "impact_plan.json",
        [[r["wos_id"], r["code"]] for r in units.iter_rows(named=True)],
    )


# --------------------------------------------------------------------------
# the paper preset
# --------------------------------------------------------------------------

PAPER_ENTRIES = {
    "coder": ("coder", {"logprobs": False}),
    "gemma": (
        "gemma",
        {"chat_template_kwargs": {"enable_thinking": True}, "logprobs": False},
    ),
}


def paper():
    root = FIXTURES / "paper"
    calls = root / "calls"
    if calls.exists():
        shutil.rmtree(calls)
    docs = documents(PAPER_WORKS)
    by_id = {r["wos_id"]: r for r in docs.iter_rows(named=True)}
    write_json(
        root / "works.json",
        {
            "columns": ["id", "title", "abstract"],
            "rows": [
                [w, WORK_BY_ID[w]["title"], WORK_BY_ID[w]["abstract"]]
                for w in PAPER_WORKS
            ],
        },
    )
    label_frames = {"adt": {}, "sdg": {}}
    for exercise in ("adt", "sdg"):
        blocks = paper_pass.labels_blocks(PAPER_FILES[exercise])
        prompt_id = paper_pass.labels_prompt_id(blocks, exercise)
        for entry, (model, extra_body) in PAPER_ENTRIES.items():
            params = {
                "model": model,
                "exercise": exercise,
                "seed": 42,
                "max_tokens": 16000,
                "retry_max_tokens": 32000,
                "extra_body": extra_body,
            }
            table = {}
            for work_id in PAPER_WORKS:
                req = paper_pass.labels_request(
                    by_id[work_id], blocks, model, 42, params
                )
                table[(req.system, req.user, 16000)] = paper_answer(
                    entry, exercise, work_id, 1
                )
                table[(req.system, req.user, 32000)] = paper_answer(
                    entry, exercise, work_id, 2
                )
            chunk = docs.select("wos_id").with_columns(code=pl.lit("WORK"))
            frame = paper_pass._label_rows(
                chunk, docs, blocks, client(table, calls), params, prompt_id
            )
            label_frames[exercise][entry] = frame
            rows = []
            for row in frame.iter_rows(named=True):
                body = paper_answer(
                    entry, exercise, row["wos_id"], 2 if row["retried"] else 1
                )
                served, fp = served_of(body)
                rows.append(
                    [
                        row["wos_id"],
                        row["code"],
                        1,
                        model,
                        served,
                        fp,
                        row["prompt_id"],
                        row["label"],
                        row["retried"],
                        row["tokens_in"],
                        row["tokens_out"],
                        row["parse_failure"],
                    ]
                )
            rows.sort(key=lambda r: (r[0], r[1]))
            write_json(
                root / "expected" / f"paper_{exercise}__{entry}.json",
                table_fixture(
                    [
                        "id",
                        "code",
                        "repeat",
                        *CALL_COLUMNS,
                        "label",
                        "retried",
                        "tokens_in",
                        "tokens_out",
                        "parse_failure",
                    ],
                    [
                        "String",
                        "String",
                        "Int64",
                        *CALL_DTYPES,
                        "String",
                        "Boolean",
                        "Int64",
                        "Int64",
                        "Boolean",
                    ],
                    rows,
                ),
            )

    # Impact: one call per work over the union of both models' labels.
    blocks, targets, _, targets_text = impact_blocks_and_ids()
    preamble = paper_pass.work_preamble(PREAMBLE)
    prompt_id = paper_pass.work_prompt_id(preamble, blocks, targets_text)
    units = impact_pass.impact_units(
        docs, label_frames["adt"], label_frames["sdg"], ["E", "A", "T", "M"], ["Y"]
    )
    flags = [c for c in units.columns if c.startswith(("adt_", "sdg_"))]
    assert flags == ["adt_coder", "adt_gemma", "sdg_coder", "sdg_gemma"], flags
    units = pl.concat(
        [
            paper_pass.pair_order(g)
            for _, g in units.sort("wos_id").group_by("wos_id", maintain_order=True)
        ]
    )
    groups = [g for _, g in units.group_by("wos_id", maintain_order=True)]
    for entry, (model, extra_body) in PAPER_ENTRIES.items():
        params = {"max_tokens": 32000, "extra_body": extra_body}
        reqs, texts, table = [], [], {}
        for g in groups:
            doc = by_id[g["wos_id"][0]]
            pairs = list(zip(g["adt"], g["sdg"], strict=True))
            req = paper_pass.work_request(
                doc,
                pairs,
                preamble,
                blocks,
                targets,
                ADT_NAMES,
                SDG_NAMES,
                model,
                42,
                params,
            )
            text = (doc["title"] or "") + "\n" + (doc["abstract"] or "")
            reqs.append(req)
            texts.append(text)
            table[(req.system, req.user, 32000)] = paper_impact_answer(
                entry, doc["wos_id"], pairs, text, 1
            )
            table[(req.system, req.user, 48000)] = paper_impact_answer(
                entry, doc["wos_id"], pairs, text, 2
            )
        # The body of run_paper_impact's `answer`, for one chunk holding every work.
        results, retried = paper_pass._with_retry(
            client(table, calls),
            reqs,
            f"paper-impact-{model}",
            lambda i, text, groups=groups, texts=texts: (
                paper_pass.parse_work(text, groups[i].height, texts[i]) is not None
            ),
            48000,
        )
        rows = []
        for i, (g, res) in enumerate(zip(groups, results, strict=True)):
            parsed = paper_pass.parse_work(res.text, g.height, texts[i])
            if parsed is None:
                parsed = [
                    {
                        "pos_label": "OTHER",
                        "neg_label": "OTHER",
                        "beneficial_kind": None,
                        "quotes_ok": False,
                    }
                ] * g.height
            pairs = list(zip(g["adt"], g["sdg"], strict=True))
            body = paper_impact_answer(
                entry, g["wos_id"][0], pairs, texts[i], 2 if i in retried else 1
            )
            served, fp = served_of(body)
            for unit, p in zip(g.iter_rows(named=True), parsed, strict=True):
                rows.append(
                    [
                        unit["wos_id"],
                        unit["code"],
                        unit["adt"],
                        unit["sdg"],
                        *[unit[f] for f in flags],
                        1,
                        model,
                        served,
                        fp,
                        prompt_id,
                        p["pos_label"],
                        p["neg_label"],
                        p["beneficial_kind"],
                        p["quotes_ok"],
                        g.height,
                        i in retried,
                        res.tokens_in,
                        res.tokens_out,
                        p["pos_label"] == "OTHER",
                    ]
                )
        rows.sort(key=lambda r: (r[0], r[1]))
        columns = [
            "id",
            "code",
            "adt",
            "sdg",
            *flags,
            "repeat",
            *CALL_COLUMNS,
            "pos_label",
            "neg_label",
            "beneficial_kind",
            "quotes_ok",
            "n_pairs",
            "retried",
            "tokens_in",
            "tokens_out",
            "parse_failure",
        ]
        dtypes = (
            ["String"] * 4
            + ["Boolean"] * len(flags)
            + [
                "Int64",
                *CALL_DTYPES,
                "String",
                "String",
                "String",
                "Boolean",
                "Int64",
                "Boolean",
                "Int64",
                "Int64",
                "Boolean",
            ]
        )
        write_json(
            root / "expected" / f"paper_impact__{entry}.json",
            table_fixture(columns, dtypes, rows),
        )


# --------------------------------------------------------------------------
# cross and file units
# --------------------------------------------------------------------------


def cross_units():
    """[WS] cross units over invented sources: union, flags, agreed first; and a file of units."""
    docs = documents()
    adt = {
        "m1": [
            ("w-003", "AI", "T"),
            ("w-003", "ROBOTICS", "N"),
            ("w-001", "BLOCKCHAIN", "A"),
            ("w-010", "ROBOTICS", "OTHER"),
            ("w-010", "ADDITIVE_MANUFACTURING", "E"),
        ],
        "m2": [
            ("w-003", "AI", "M"),
            ("w-001", "BLOCKCHAIN", "N"),
            ("w-001", "IOT", "T"),
            ("w-010", "ADDITIVE_MANUFACTURING", "A"),
        ],
    }
    sdg = {
        "m1": [
            ("w-003", "SDG-07", "Y"),
            ("w-003", "SDG-03", "N"),
            ("w-001", "SDG-14", "Y"),
            ("w-010", "SDG-03", "Y"),
            ("w-010", "SDG-04", "OTHER"),
        ],
    }

    def frames(sources):
        return {
            name: pl.DataFrame(rows, schema=["wos_id", "code", "label"], orient="row")
            for name, rows in sources.items()
        }

    cases = []
    for name, adt_positive, sdg_positive in (
        ("eatm_y", ["E", "A", "T", "M"], ["Y"]),
        ("with_other", ["T", "OTHER"], ["Y", "OTHER"]),
    ):
        units = impact_pass.impact_units(
            docs, frames(adt), frames(sdg), adt_positive, sdg_positive
        )
        flags = [c for c in units.columns if c.startswith(("adt_", "sdg_"))]
        cases.append(
            {
                "name": name,
                "adt_positive": adt_positive,
                "sdg_positive": sdg_positive,
                "flags": flags,
                "agreed_first": [
                    [r[c] for c in ("wos_id", "code", "adt", "sdg", *flags)]
                    for r in units.iter_rows(named=True)
                ],
            }
        )
    pairs = pl.DataFrame(
        {
            "wos_id": ["w-010", "w-003", "w-003", "w-002"],
            "adt": ["ADDITIVE_MANUFACTURING", "IOT", "AI", "ROBOTICS"],
            "sdg": ["SDG-03", "SDG-07", "SDG-07", "SDG-16"],
        }
    )
    file_units = impact_pass._pairs_units(
        pairs,
        docs,
        frames(adt),
        frames(sdg),
        ["E", "A", "T", "M"],
        ["Y"],
        ADT_NAMES,
        SDG_NAMES,
    )
    flags = [c for c in file_units.columns if c.startswith(("adt_", "sdg_"))]
    write_json(
        FIXTURES / "units" / "cross.json",
        {
            "adt": adt,
            "sdg": sdg,
            "cases": cases,
            "file": {
                "rows": [list(r) for r in pairs.iter_rows()],
                "flags": flags,
                "units": [
                    [r[c] for c in ("wos_id", "code", "adt", "sdg", *flags)]
                    for r in file_units.iter_rows(named=True)
                ],
            },
        },
    )


def main():
    render_fixtures()
    impact()
    paper()
    cross_units()
    print("make_ws: done")


if __name__ == "__main__":
    main()
