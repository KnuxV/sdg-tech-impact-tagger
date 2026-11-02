"""Freeze the fixtures whose oracle is open_alex_adt_gate ([OA]).

Run with the interpreter of that repository, read-only:

    ../open_alex_adt_gate/.venv/bin/python -B tests/fixtures/make/make_oa.py

It imports the earlier code by path and runs it on the invented inputs of
`inputs.py`, against a stub transport that serves the scripted answers. What
it writes, under tests/fixtures/:

- render/protocol_v1__*.json: the system and user text of each call;
- wire.json: cache keys, wire bodies and cache file text of single calls;
- protocol_impact/calls/: the cache files the [OA] client wrote for the four
  protocol passes, both models;
- protocol_impact/expected/<pass>__<model>.json: their tables, in the new
  columns (contract 8.3);
- protocol_impact/expected/sdg_pass2__qwen3__final_channel.json: the same
  cache read with `final_channel` extraction;
- protocol_impact/sdg_pass2_keys.json: the cache key of each SDG pass 2 unit;
- units/threshold.json: threshold units selected by [OA] on invented scores.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OA = HERE.parents[3] / "open_alex_adt_gate"
sys.path.insert(0, str(OA / "src"))
sys.path.insert(0, str(HERE))

import httpx
import polars as pl
from inputs import (
    ADT_NAMES,
    FIXTURES,
    NON_JSON,
    QUESTIONS,
    SDG_NAMES,
    WORKS,
    adt_pass1_answer,
    adt_pass2_answer,
    chat_body,
    sdg_pass1_answer,
    sdg_pass2_answer,
    served_of,
    table_fixture,
    token_body,
    write_json,
)
from open_alex_adt_gate import adt_pass2, llm_passes, sdg_pass1
from open_alex_adt_gate.adt_pass1 import build_adt_scores, descriptions_text
from open_alex_adt_gate.llm.client import (
    ChatRequest,
    LLMClient,
    SingleTokenRequest,
)
from open_alex_adt_gate.llm.prompts import load_prompts
from open_alex_adt_gate.sdg_pass2 import build_pass2

P = QUESTIONS / "protocol_v1"
SDG1_FILE = P / "sdg_pass1" / "sdg_pass1.md"
SDG2_TEMPLATE = P / "sdg_pass2" / "sdg_pass2_v3.md"
SDG2_GOALS = P / "sdg_pass2" / "sdg_pass2_v3"
ADT1_TEMPLATE = P / "adt_pass1" / "adt_pass1_v3.md"
ADT1_DESC = P / "adt_pass1" / "adt_descriptions_v3.md"
ADT2_TEMPLATE = P / "adt_pass2" / "adt_pass2_v4.md"
ADT2_DESC = P / "adt_pass2" / "adt_descriptions_v3.md"
ADT2_BOUND = P / "adt_pass2" / "adt_boundaries_v4.md"

CALLS = FIXTURES / "protocol_impact" / "calls"
EXPECTED = FIXTURES / "protocol_impact" / "expected"
SERVED = {"qwen3": "qwen3", "gemma": "gemma"}

CALL_COLUMNS = ["model", "model_served", "system_fingerprint", "prompt_id", "run_id"]
CALL_DTYPES = ["String", "String", "String", "String"]


def transport(table):
    """A stub endpoint serving `table[(system, user, max_tokens)]`; refuses anything else."""

    def handler(request):
        payload = json.loads(request.content)
        key = (
            payload["messages"][0]["content"],
            payload["messages"][1]["content"],
            payload["max_tokens"],
        )
        body = table[key]
        if body == NON_JSON:
            return httpx.Response(200, text=NON_JSON)
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


def client(table, cache=CALLS):
    return LLMClient(
        base_url="http://oracle.invalid/api",
        api_key="oracle",
        cache_dir=cache,
        concurrency=1,
        transport=transport(table),
    )


def stored(body):
    """The body as the client stores it: a non-JSON reply becomes `unparseable_body`."""
    return {"unparseable_body": NON_JSON} if body == NON_JSON else body


def documents():
    return llm_passes.stage_documents(
        pl.DataFrame(
            WORKS, schema={"id": pl.String, "title": pl.String, "abstract": pl.String}
        )
    )


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def render_fixtures():
    sdg1_blocks, _ = load_prompts(SDG1_FILE, "sdgp1")
    sdg2 = llm_passes.load_sdg_pass2_texts(SDG2_TEMPLATE, SDG2_GOALS)
    adt1 = llm_passes.load_adt_pass1_texts(ADT1_TEMPLATE, ADT1_DESC)
    adt2 = llm_passes.load_adt_pass2_texts(ADT2_TEMPLATE, ADT2_DESC, ADT2_BOUND)
    texts_cases = [
        {"title": WORKS[1]["title"], "abstract": WORKS[1]["abstract"]},
        {"title": WORKS[3]["title"], "abstract": None},
        {"title": "<title>", "abstract": "<abstract>"},
    ]

    def sdg1(texts, units):
        user = sdg1_blocks["USER_SCORE17"].format(
            title=texts["title"], abstract=texts["abstract"] or ""
        )
        return [(sdg1_blocks["SYSTEM_SCORE17"], user)]

    def sdg2_calls(texts, units):
        return [
            (
                sdg2.blocks[code]["SYSTEM_PASS2"],
                sdg2.blocks[code]["USER_PASS2"].format(
                    title=texts["title"], abstract=texts["abstract"] or ""
                ),
            )
            for (code,) in units
        ]

    def adt1_calls(texts, units):
        system = adt1.blocks["SYSTEM_ADT_SCORE"].format(
            descriptions=descriptions_text(adt1.descriptions)
        )
        user = adt1.blocks["USER_ADT_SCORE"].format(
            title=texts["title"], abstract=texts["abstract"] or ""
        )
        return [(system, user)]

    def adt2_calls(texts, units):
        return [
            (
                adt_pass2.system_text(adt2.blocks),
                adt_pass2.user_text(
                    adt2.blocks,
                    texts["title"],
                    texts["abstract"],
                    adt2.descriptions[code][0],
                    adt2.descriptions[code][1],
                    adt2.boundaries[code],
                ),
            )
            for (code,) in units
        ]

    specs = [
        ("protocol_v1/sdg_pass1", sdg1, [[]]),
        ("protocol_v1/sdg_pass2", sdg2_calls, [[["SDG-13"], ["SDG-03"]], [["SDG-01"]]]),
        ("protocol_v1/adt_pass1", adt1_calls, [[]]),
        (
            "protocol_v1/adt_pass2",
            adt2_calls,
            [[["ROBOTICS"], ["AI"]], [["COMPUTING_INFRASTRUCTURE"]]],
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
                        "calls": [
                            list(call)
                            for call in render(texts, [tuple(u) for u in units])
                        ],
                    }
                )
        write_json(
            FIXTURES / "render" / (name.replace("/", "__") + ".json"),
            {"question": name, "cases": cases},
        )


# --------------------------------------------------------------------------
# single calls: keys, wire bodies, cache files
# --------------------------------------------------------------------------

COLOUR_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "colour_scores",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "RED": {"type": "integer"},
                "GREEN": {"type": "integer"},
                "BLUE": {"type": "integer"},
            },
            "required": ["RED", "GREEN", "BLUE"],
            "additionalProperties": False,
        },
    },
}


def wire_fixture(tmp):
    """Each case: one request through the [OA] client; the payload it sent, the key, the file."""
    title = "Red kite été {abstract}"
    cases = [
        (
            "score_json",
            ChatRequest(
                model="m1",
                system="You score colours.",
                user=f"Text: {title}\n",
                seed=7,
                temperature=0.0,
                max_tokens=50,
                response_format=COLOUR_SCHEMA,
            ),
            chat_body(
                '{"RED": 10, "GREEN": 0, "BLUE": 55}',
                "m1-served",
                "fp-x",
                tin=20,
                tout=12,
            ),
        ),
        (
            "letter_logprob",
            SingleTokenRequest(
                model="m1",
                system="Answer Y or N.",
                user=f"Text: {title}\nColour: Blue\nY or N:",
                seed=7,
                temperature=0.0,
                max_tokens=1,
                top_logprobs=5,
            ),
            token_body(
                "Y", [("Y", [("Y", -0.2), (" N", -1.7)])], "m1-served", None, tin=21
            ),
        ),
        (
            "letter_text",
            SingleTokenRequest(
                model="m1",
                system="Answer Y or N.",
                user=f"Text: {title}\nColour: Blue\nY or N:",
                seed=7,
                temperature=0.0,
                max_tokens=300,
                top_logprobs=0,
                extra_body={"logprobs": False},
            ),
            chat_body("N", "m1-served", "fp-x", tin=22, tout=40),
        ),
        (
            "letter_text_thinking",
            SingleTokenRequest(
                model="m1",
                system="Answer Y or N.",
                user=f"Text: {title}\nColour: Blue\nY or N:",
                seed=7,
                temperature=0.0,
                max_tokens=300,
                top_logprobs=0,
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": True},
                    "logprobs": False,
                },
            ),
            chat_body("Y", "m1-served", "fp-x", tin=22, tout=250),
        ),
    ]
    out = []
    for name, req, body in cases:
        sent = []

        def handler(request, body=body, sent=sent):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json=body)

        cache = tmp / name
        oa = LLMClient(
            base_url="http://oracle.invalid/v1",
            api_key="oracle",
            cache_dir=cache,
            concurrency=1,
            transport=httpx.MockTransport(handler),
        )
        if isinstance(req, ChatRequest):
            key = oa._chat_key(req)
            fields = oa._chat_key_fields(req)
            oa.chat(req, "fixture")
        else:
            key = oa._single_token_key(req)
            fields = oa._single_token_key_fields(req)
            oa.single_token(req, "fixture")
        files = list(cache.rglob("*.json"))
        assert len(files) == 1 and files[0].name == f"{key}.json", files
        out.append(
            {
                "case": name,
                "fields": fields,
                "key": key,
                "repeat_2_key": LLMClient._hash_fields({**fields, "repeat": 2}),
                "payload": sent[0],
                "body": body,
                "file_text": files[0].read_text(encoding="utf-8"),
            }
        )
    write_json(FIXTURES / "wire.json", out)


# --------------------------------------------------------------------------
# the four protocol passes, both models
# --------------------------------------------------------------------------


def score_rows(frame, answers, model):
    rows = []
    for row in frame.sort("wos_id", "code").iter_rows(named=True):
        served, fp = served_of(stored(answers[row["wos_id"]]))
        rows.append(
            [
                row["wos_id"],
                row["code"],
                1,
                model,
                served,
                fp,
                row["prompt_id"],
                row["score"],
                row["tokens_in"],
                row["tokens_out"],
                row["parse_failure"],
            ]
        )
    return table_fixture(
        [
            "id",
            "code",
            "repeat",
            *CALL_COLUMNS,
            "score",
            "tokens_in",
            "tokens_out",
            "parse_failure",
        ],
        [
            "String",
            "String",
            "Int64",
            *CALL_DTYPES,
            "Float64",
            "Int64",
            "Int64",
            "Boolean",
        ],
        rows,
    )


def letter_rows(frame, answers, model, letters, prob_columns, extraction="first_token"):
    """Pass 2 rows in the new columns; the probabilities read again by the [OA] client parser."""
    reader = LLMClient(
        base_url="http://oracle.invalid", api_key="x", cache_dir=Path("/nonexistent")
    )
    rows = []
    for row in frame.sort("wos_id", "code").iter_rows(named=True):
        body = stored(answers[(row["wos_id"], row["code"])])
        parsed = reader._parse_single_token(body, "k", True, extraction, tuple(letters))
        if extraction == "first_token":
            assert parsed.label == row["label"]
            for letter, column in zip(letters, prob_columns, strict=True):
                if column in row:
                    expected = None if parsed.probs is None else parsed.probs[letter]
                    assert expected == row[column], (row, letter)
        probs = [
            None if parsed.probs is None else parsed.probs[letter] for letter in letters
        ]
        served, fp = served_of(body)
        rows.append(
            [
                row["wos_id"],
                row["code"],
                row["pass1_score"],
                1,
                model,
                served,
                fp,
                row["prompt_id"],
                parsed.label,
                *probs,
                row["tokens_in"],
                row["tokens_out"],
                parsed.label == "OTHER",
            ]
        )
    columns = [
        "id",
        "code",
        "source_score",
        "repeat",
        *CALL_COLUMNS,
        "label",
        *[f"p_{letter.lower()}" for letter in letters],
        "tokens_in",
        "tokens_out",
        "parse_failure",
    ]
    dtypes = [
        "String",
        "String",
        "Float64",
        "Int64",
        *CALL_DTYPES,
        "String",
        *["Float64"] * len(letters),
        "Int64",
        "Int64",
        "Boolean",
    ]
    return table_fixture(columns, dtypes, rows)


def protocol():
    if CALLS.exists():
        shutil.rmtree(CALLS)
    docs = documents()
    sdg1_blocks, sdg1_id = load_prompts(SDG1_FILE, "sdgp1")
    sdg2 = llm_passes.load_sdg_pass2_texts(SDG2_TEMPLATE, SDG2_GOALS)
    adt1 = llm_passes.load_adt_pass1_texts(ADT1_TEMPLATE, ADT1_DESC)
    adt2 = llm_passes.load_adt_pass2_texts(ADT2_TEMPLATE, ADT2_DESC, ADT2_BOUND)
    inventory = pl.DataFrame(
        {
            "code": [f"SDG-{n:02d}" for n in range(1, 18)],
            "is_un_target": [True] * 17,
            "target_id": ["0.0"] * 17,
            "target_text": ["unused"] * 17,
        }
    )
    sdg2_keys = {}
    reader = LLMClient(
        base_url="http://oracle.invalid", api_key="x", cache_dir=Path("/nonexistent")
    )
    by_id = {row["wos_id"]: row for row in docs.iter_rows(named=True)}

    for model in ("qwen3", "gemma"):
        # SDG pass 1, the score17 arm.
        answers = {
            doc["wos_id"]: sdg_pass1_answer(model, doc["wos_id"])
            for doc in docs.iter_rows(named=True)
        }
        table = {
            (
                sdg1_blocks["SYSTEM_SCORE17"],
                sdg1_blocks["USER_SCORE17"].format(
                    title=doc["title"], abstract=doc["abstract"]
                ),
                1024,
            ): answers[doc["wos_id"]]
            for doc in docs.iter_rows(named=True)
        }
        scores = sdg_pass1.build_scores(
            client(table),
            docs,
            "score17",
            SERVED[model],
            sdg1_blocks,
            sdg1_id,
            seed=42,
            max_tokens=1024,
        )
        write_json(
            EXPECTED / f"sdg_pass1__{model}.json", score_rows(scores, answers, model)
        )

        # SDG pass 2 on the pairs at or above 0.25, goal by goal as [OA] ran it.
        pairs = llm_passes.sdg_candidates(scores, docs, 0.25, "score17")
        answers2, table2 = {}, {}
        for row in pairs.iter_rows(named=True):
            code = row["code"]
            body = sdg_pass2_answer(model, row["wos_id"], code)
            answers2[(row["wos_id"], code)] = body
            doc = by_id[row["wos_id"]]
            user = sdg2.blocks[code]["USER_PASS2"].format(
                title=doc["title"], abstract=doc["abstract"]
            )
            table2[(sdg2.blocks[code]["SYSTEM_PASS2"], user, 1)] = body
            req = SingleTokenRequest(
                model=model,
                system=sdg2.blocks[code]["SYSTEM_PASS2"],
                user=user,
                seed=42,
            )
            sdg2_keys.setdefault(model, {})[f"{row['wos_id']}|{code}"] = (
                reader._single_token_key(req)
            )
        frames = [
            build_pass2(
                client(table2),
                docs,
                group,
                SERVED[model],
                sdg2.blocks[code],
                inventory,
                sdg2.prompt_ids[code],
                42,
            )
            for (code,), group in pairs.group_by("code", maintain_order=True)
        ]
        pass2 = pl.concat(frames)
        write_json(
            EXPECTED / f"sdg_pass2__{model}.json",
            letter_rows(pass2, answers2, model, ["Y", "N"], ["p_yes", None]),
        )
        if model == "qwen3":
            write_json(
                EXPECTED / "sdg_pass2__qwen3__final_channel.json",
                letter_rows(
                    pass2, answers2, model, ["Y", "N"], ["p_yes", None], "final_channel"
                ),
            )

        # ADT pass 1.
        answers = {
            doc["wos_id"]: adt_pass1_answer(model, doc["wos_id"])
            for doc in docs.iter_rows(named=True)
        }
        system = adt1.blocks["SYSTEM_ADT_SCORE"].format(
            descriptions=descriptions_text(adt1.descriptions)
        )
        table = {
            (
                system,
                adt1.blocks["USER_ADT_SCORE"].format(
                    title=doc["title"], abstract=doc["abstract"]
                ),
                1024,
            ): answers[doc["wos_id"]]
            for doc in docs.iter_rows(named=True)
        }
        adt_scores = build_adt_scores(
            client(table),
            docs,
            SERVED[model],
            adt1.blocks,
            adt1.descriptions,
            adt1.prompt_id,
            42,
            1024,
        )
        write_json(
            EXPECTED / f"adt_pass1__{model}.json",
            score_rows(adt_scores, answers, model),
        )

        # ADT pass 2 on the pairs at or above 0.25.
        pairs = llm_passes.adt_candidates(adt_scores, docs, 0.25)
        answers2, table2 = {}, {}
        for row in pairs.iter_rows(named=True):
            code = row["code"]
            body = adt_pass2_answer(model, row["wos_id"], code)
            answers2[(row["wos_id"], code)] = body
            doc = by_id[row["wos_id"]]
            user = adt_pass2.user_text(
                adt2.blocks,
                doc["title"],
                doc["abstract"],
                adt2.descriptions[code][0],
                adt2.descriptions[code][1],
                adt2.boundaries[code],
            )
            table2[(adt_pass2.system_text(adt2.blocks), user, 1)] = body
        pass2 = adt_pass2.build_adt_pass2(
            client(table2),
            docs,
            pairs,
            SERVED[model],
            adt2.blocks,
            adt2.descriptions,
            adt2.boundaries,
            adt2.prompt_ids,
            42,
        )
        letters = list(adt_pass2.LETTERS)
        write_json(
            EXPECTED / f"adt_pass2__{model}.json",
            letter_rows(
                pass2, answers2, model, letters, [f"p_{x.lower()}" for x in letters]
            ),
        )
    write_json(FIXTURES / "protocol_impact" / "sdg_pass2_keys.json", sdg2_keys)
    write_json(
        FIXTURES / "protocol_impact" / "works.json",
        {
            "columns": ["id", "title", "abstract"],
            "rows": [[w["id"], w["title"], w["abstract"]] for w in WORKS],
        },
    )


# --------------------------------------------------------------------------
# threshold units
# --------------------------------------------------------------------------


def threshold_units():
    """[OA] selection and order of threshold units on an invented ADT pass 1 table."""
    docs = documents()
    codes = [
        "AI",
        "IOT",
        "COMPUTING_INFRASTRUCTURE",
        "BLOCKCHAIN",
        "ROBOTICS",
        "ADDITIVE_MANUFACTURING",
    ]
    values = {
        "w-003": [0.9, 0.0, 0.25, 0.1, 0.5, 0.3],
        "w-001": [0.249, 0.6, 0.0, 1.0, 0.0, 0.0],
        "w-010": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # a parse failure, scored 0.0
        "w-002": [0.0, 0.0, 0.0, 0.0, 0.7, 0.26],
    }
    rows = []
    for work_id, scores in values.items():
        for code, score in zip(codes, scores, strict=True):
            rows.append(
                {
                    "wos_id": work_id,
                    "code": code,
                    "arm": "adt_score",
                    "score": score,
                    "parse_failure": work_id == "w-010",
                }
            )
    source = pl.DataFrame(rows, schema=llm_passes.SCORES_REQUIRED)
    cases = []
    for at_least in (0.25, 0.0, 0.5):
        units = llm_passes.adt_candidates(source, docs, at_least)
        cases.append(
            {
                "at_least": at_least,
                "units": [
                    [r["wos_id"], r["code"], r["pass1_score"]]
                    for r in units.iter_rows(named=True)
                ],
            }
        )
    write_json(
        FIXTURES / "units" / "threshold.json",
        {
            "source": [
                [r["wos_id"], r["code"], r["score"], r["parse_failure"]] for r in rows
            ],
            "cases": cases,
        },
    )


def lists_fixture():
    """The shipped lists as the earlier runs named the labels (contract 2.2)."""
    from open_alex_adt_gate.adt_pass1 import adt_descriptions
    from open_alex_adt_gate.sdg_pass2 import goal_name

    sdg = [
        {
            "id": code,
            "json_key": f"SDG{int(code[4:])}",
            "name": sdg_pass1.SDG_TITLES[code],
            "number": code[4:],
            "name_short": goal_name(code),
            "name_impact": SDG_NAMES[code],
        }
        for code in sdg_pass1.SDG_TITLES
    ]
    described = adt_descriptions(ADT1_DESC)
    adt = [
        {
            "id": code,
            "json_key": code,
            "name": described[code][0],
            "name_impact": ADT_NAMES[code],
        }
        for code in adt_pass2.ADT_LABEL_CODES
    ]
    write_json(FIXTURES / "lists.json", {"sdg": sdg, "adt": adt})


def main():
    import tempfile

    lists_fixture()

    render_fixtures()
    with tempfile.TemporaryDirectory() as tmp:
        wire_fixture(Path(tmp))
    protocol()
    threshold_units()
    print("make_oa: done")


if __name__ == "__main__":
    main()
