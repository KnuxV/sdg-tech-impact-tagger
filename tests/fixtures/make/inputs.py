"""Invented inputs shared by the fixture scripts: works and scripted answers.

Every text and every model answer here is written for the tests; none comes
from a real document. Standard library only, so that the interpreter of each
earlier repository can import it.

The answers are keyed by what a call is about (stage, model, work, label,
side, attempt), and the fixture scripts turn that into the body a stub
endpoint returns for the exact request the earlier code builds.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent
REPO = FIXTURES.parent.parent
QUESTIONS = REPO / "src" / "sdg_tech_impact_tagger" / "questions"

# Not in id order, so that "position in the texts table" and "sorted by id"
# give different orders. One title holds braces, two texts hold non-ASCII
# characters, one abstract is null.
WORKS: list[dict[str, str | None]] = [
    {
        "id": "w-003",
        "title": "Kestrel study: solar microgrids that power rural clinics",
        "abstract": (
            "We size a solar microgrid for three rural clinics and forecast their "
            "demand with a small neural network. Outages fell by half over one year."
        ),
    },
    {
        "id": "w-001",
        "title": "Juniper ledger: a {abstract} record of {0} fishing quotas",
        "abstract": (
            "A permissioned blockchain records the catch quotas of two coastal "
            "cooperatives. Each entry costs 0.3 µ€ and the café owners kept using it."
        ),
    },
    {
        "id": "w-010",
        "title": "Basalt hands: printed prosthetics for children",
        "abstract": (
            "Additive manufacturing produces low cost prosthetic hands. A robot arm "
            "sands each print before fitting, and families report better school attendance."
        ),
    },
    {
        "id": "w-002",
        "title": "Quokka seminar notes",
        "abstract": None,
    },
]

WORK_BY_ID = {work["id"]: work for work in WORKS}
MARKERS = {"w-003": "Kestrel", "w-001": "Juniper", "w-010": "Basalt", "w-002": "Quokka"}

SDG_CODES = [f"SDG-{n:02d}" for n in range(1, 18)]
ADT_CODES = [
    "AI",
    "IOT",
    "COMPUTING_INFRASTRUCTURE",
    "BLOCKCHAIN",
    "ROBOTICS",
    "ADDITIVE_MANUFACTURING",
]

# name_impact of the two shipped lists, as [WS] params.yaml writes them.
ADT_NAMES = {
    "AI": "artificial intelligence",
    "IOT": "the Internet of Things",
    "COMPUTING_INFRASTRUCTURE": "computing infrastructure",
    "BLOCKCHAIN": "blockchain",
    "ROBOTICS": "robotics",
    "ADDITIVE_MANUFACTURING": "additive manufacturing",
}
SDG_NAMES = {
    "SDG-01": "SDG 1, no poverty",
    "SDG-02": "SDG 2, zero hunger",
    "SDG-03": "SDG 3, good health and well-being",
    "SDG-04": "SDG 4, quality education",
    "SDG-05": "SDG 5, gender equality",
    "SDG-06": "SDG 6, clean water and sanitation",
    "SDG-07": "SDG 7, affordable and clean energy",
    "SDG-08": "SDG 8, decent work and economic growth",
    "SDG-09": "SDG 9, industry, innovation and infrastructure",
    "SDG-10": "SDG 10, reduced inequalities",
    "SDG-11": "SDG 11, sustainable cities and communities",
    "SDG-12": "SDG 12, responsible consumption and production",
    "SDG-13": "SDG 13, climate action",
    "SDG-14": "SDG 14, life below water",
    "SDG-15": "SDG 15, life on land",
    "SDG-16": "SDG 16, peace, justice and strong institutions",
    "SDG-17": "SDG 17, partnerships for the goals",
}

NON_JSON = "<html><body>gateway hiccup</body></html>"


# --------------------------------------------------------------------------
# bodies
# --------------------------------------------------------------------------


def chat_body(content, served, fp, *, tin, tout, finish="stop"):
    """An OpenAI-style chat completion body; `model` and the fingerprint only when given."""
    body = {
        "id": "chatcmpl-fixture",
        "object": "chat.completion",
        "created": 1767225600,
    }
    if served is not None:
        body["model"] = served
    if fp is not None:
        body["system_fingerprint"] = fp
    body["choices"] = [
        {
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": finish,
        }
    ]
    body["usage"] = {
        "prompt_tokens": tin,
        "completion_tokens": tout,
        "total_tokens": tin + tout,
    }
    return body


def token_body(content, entries, served, fp, *, tin, tout=1, finish="length"):
    """A chat body with `logprobs.content`: entries are (token, [(top token, logprob)])."""
    body = chat_body(content, served, fp, tin=tin, tout=tout, finish=finish)
    body["choices"][0]["logprobs"] = {
        "content": [
            {
                "token": token,
                "logprob": top[0][1] if top else 0.0,
                "top_logprobs": [{"token": t, "logprob": lp} for t, lp in top],
            }
            for token, top in entries
        ]
    }
    return body


def served_of(body):
    """(model served, fingerprint) of a body as the contract reads them (4.1)."""
    if not isinstance(body, dict):
        return None, None
    model = body.get("model")
    fp = body.get("system_fingerprint")
    return (
        model if isinstance(model, str) else None,
        fp if isinstance(fp, str) else None,
    )


def tokens_in_of(work_id, salt=0):
    return 900 + 37 * list(WORK_BY_ID).index(work_id) + salt


# --------------------------------------------------------------------------
# score_json answers (protocol pass 1)
# --------------------------------------------------------------------------


def _score_object(keys, values):
    return {key: values.get(key, 0) for key in keys}


def _score_content(keys, values):
    return json.dumps(_score_object(keys, values))


SDG_KEYS = [f"SDG{n}" for n in range(1, 18)]


def sdg_pass1_answer(model, work_id):
    tin = tokens_in_of(work_id)
    if model == "qwen3":
        served = "qwen3-2025-07"
        if work_id == "w-003":
            content = _score_content(
                SDG_KEYS, {"SDG3": 60, "SDG7": 90, "SDG13": 25, "SDG9": 24}
            )
            return chat_body(content, served, "fp-q1", tin=tin, tout=120)
        if work_id == "w-001":
            # Floats truncate, values outside [0, 100] clamp.
            content = (
                '{"SDG1": -10, "SDG2": 0, "SDG3": 0, "SDG4": 0, "SDG5": 0, "SDG6": 0, '
                '"SDG7": 0, "SDG8": 25.9, "SDG9": 0, "SDG10": 0, "SDG11": 0, '
                '"SDG12": 150, "SDG13": 0, "SDG14": 80.7, "SDG15": 0, "SDG16": 0, "SDG17": 0}'
            )
            return chat_body(content, served, None, tin=tin, tout=118)
        if work_id == "w-010":
            # A key outside the list: unreadable.
            values = _score_object(SDG_KEYS, {"SDG3": 70, "SDG9": 55})
            values["SDG18"] = 5
            return chat_body(json.dumps(values), served, "fp-q1", tin=tin, tout=125)
        if work_id == "w-002":
            return chat_body("I cannot score this work.", None, None, tin=tin, tout=9)
    if model == "gemma":
        served = "gemma-3-27b"
        if work_id == "w-003":
            content = _score_content(SDG_KEYS, {"SDG3": 40, "SDG7": 75})
            return chat_body(content, served, "fp-g1", tin=tin, tout=110)
        if work_id == "w-001":
            # A boolean is not a number: unreadable.
            content = json.dumps(_score_object(SDG_KEYS, {"SDG14": 55})).replace(
                '"SDG12": 0', '"SDG12": true'
            )
            return chat_body(content, served, "fp-g1", tin=tin, tout=111)
        if work_id == "w-010":
            content = _score_content(SDG_KEYS, {"SDG3": 30, "SDG9": 26, "SDG8": 25})
            return chat_body(content, served, "fp-g1", tin=tin, tout=112)
        if work_id == "w-002":
            # NaN loads in Python and cannot be truncated to an int: unreadable.
            content = json.dumps(_score_object(SDG_KEYS, {})).replace(
                '"SDG1": 0', '"SDG1": NaN'
            )
            return chat_body(content, served, "fp-g1", tin=tin, tout=113)
    raise KeyError((model, work_id))


def adt_pass1_answer(model, work_id):
    tin = tokens_in_of(work_id, 5)
    if model == "gemma":
        served = "gemma-3-27b"
        if work_id == "w-003":
            content = _score_content(
                ADT_CODES, {"AI": 85, "IOT": 20, "COMPUTING_INFRASTRUCTURE": 30}
            )
            return chat_body(content, served, "fp-g1", tin=tin, tout=60)
        if work_id == "w-001":
            content = _score_content(
                ADT_CODES, {"BLOCKCHAIN": 95, "COMPUTING_INFRASTRUCTURE": 25}
            )
            return chat_body(content, served, "fp-g1", tin=tin, tout=61)
        if work_id == "w-010":
            content = _score_content(
                ADT_CODES, {"ADDITIVE_MANUFACTURING": 90, "ROBOTICS": 60, "AI": 5}
            )
            return chat_body(content, served, "fp-g1", tin=tin, tout=62)
        if work_id == "w-002":
            return chat_body("", served, "fp-g1", tin=tin, tout=0)
    if model == "qwen3":
        served = "qwen3-2025-07"
        if work_id == "w-003":
            return chat_body(
                _score_content(ADT_CODES, {"AI": 70}), served, "fp-q1", tin=tin, tout=58
            )
        if work_id == "w-001":
            content = _score_content(ADT_CODES, {"BLOCKCHAIN": 88.8, "IOT": 101})
            return chat_body(content, served, "fp-q1", tin=tin, tout=59)
        if work_id == "w-010":
            content = _score_content(
                ADT_CODES, {"ADDITIVE_MANUFACTURING": 77, "ROBOTICS": 24}
            )
            return chat_body(content, served, "fp-q1", tin=tin, tout=57)
        if work_id == "w-002":
            return chat_body("{}", served, "fp-q1", tin=tin, tout=2)
    raise KeyError((model, work_id))


# --------------------------------------------------------------------------
# letter_logprob answers (protocol pass 2)
# --------------------------------------------------------------------------


def yn_variant(name, served, fp, tin):
    """The Y/N single-token answers, each built to tell a reading rule apart."""
    if name == "Y_SUM":
        entries = [("Y", [("Y", -0.02), ("N", -4.1), (" Y", -5.3), ("Yes", -6.0)])]
        return token_body("Y", entries, served, fp, tin=tin)
    if name == "N_SPACE":
        entries = [("N", [("N", -0.3), (" N", -1.6), ("Y", -2.9)])]
        return token_body("N", entries, served, fp, tin=tin)
    if name == "NULL_CONTENT_Y":
        # No message content: the answer is the first token, " Y", stripped.
        entries = [(" Y", [(" Y", -0.4), ("N", -1.2)])]
        return token_body(None, entries, served, fp, tin=tin)
    if name == "OTHER":
        entries = [("Yes", [("Yes", -0.1), ("Y", -2.5)])]
        return token_body("Yes", entries, served, fp, tin=tin)
    if name == "NONE":
        entries = [("Y", [("Maybe", -0.1), ("Perhaps", -1.0)])]
        return token_body("Y", entries, served, fp, tin=tin)
    if name == "REPEAT":
        # A repeated top token keeps its first position and its last value.
        entries = [("N", [("Y", -1.0), ("N", -0.5), ("Y", -0.3)])]
        return token_body("N", entries, served, fp, tin=tin)
    if name == "CHANNEL":
        entries = [
            ("<|channel|>", [("<|channel|>", -0.0)]),
            ("final", []),
            ("<|message|>", []),
            ("Y", [("Y", -0.05), ("N", -3.2)]),
        ]
        return token_body("Y", entries, served, fp, tin=tin, tout=4)
    if name == "CHANNEL_LAST":
        entries = [("<|message|>", [("<|message|>", -0.0)])]
        return token_body("N", entries, served, fp, tin=tin)
    if name == "EMPTY":
        return NON_JSON
    raise KeyError(name)


SDG_PASS2_PLAN = {
    "qwen3": {
        ("w-003", "SDG-03"): "Y_SUM",
        ("w-003", "SDG-07"): "NULL_CONTENT_Y",
        ("w-003", "SDG-13"): "CHANNEL",
        ("w-001", "SDG-08"): "OTHER",
        ("w-001", "SDG-12"): "REPEAT",
        ("w-001", "SDG-14"): "N_SPACE",
    },
    "gemma": {
        ("w-003", "SDG-03"): "N_SPACE",
        ("w-003", "SDG-07"): "Y_SUM",
        ("w-010", "SDG-03"): "NONE",
        ("w-010", "SDG-08"): "EMPTY",
        ("w-010", "SDG-09"): "CHANNEL_LAST",
    },
}


def sdg_pass2_answer(model, work_id, code):
    name = SDG_PASS2_PLAN[model][(work_id, code)]
    served = {"qwen3": "qwen3-2025-07", "gemma": "gemma-3-27b"}[model]
    fp = {"qwen3": "fp-q2", "gemma": None}[model]
    return yn_variant(name, served, fp, tokens_in_of(work_id, SDG_CODES.index(code)))


def letters_variant(name, served, fp, tin):
    """The five-letter single-token answers of ADT pass 2."""
    if name == "T":
        entries = [("T", [("T", -0.1), ("A", -2.3), (" T", -3.0), ("E", -5.0)])]
        return token_body("T", entries, served, fp, tin=tin)
    if name == "E":
        return token_body(
            "E", [("E", [("E", -0.05), ("M", -3.5)])], served, fp, tin=tin
        )
    if name == "A_WS":
        entries = [(" A", [(" A", -0.2), ("A", -1.9), ("T", -2.2)])]
        return token_body(" A\n", entries, served, fp, tin=tin)
    if name == "N":
        return token_body(
            "N", [("N", [("N", -0.01), ("M", -4.7)])], served, fp, tin=tin
        )
    if name == "M":
        entries = [("M", [("M", -0.6), ("N", -0.9), ("T", -3.3)])]
        return token_body("M", entries, served, fp, tin=tin)
    if name == "OTHER":
        return token_body("X", [("X", [("X", -0.1)])], served, fp, tin=tin)
    raise KeyError(name)


ADT_PASS2_PLAN = {
    "gemma": {
        ("w-003", "AI"): "T",
        ("w-003", "COMPUTING_INFRASTRUCTURE"): "M",
        ("w-001", "BLOCKCHAIN"): "A_WS",
        ("w-001", "COMPUTING_INFRASTRUCTURE"): "N",
        ("w-010", "ADDITIVE_MANUFACTURING"): "E",
        ("w-010", "ROBOTICS"): "OTHER",
    },
    "qwen3": {
        ("w-003", "AI"): "T",
        ("w-001", "BLOCKCHAIN"): "N",
        ("w-001", "IOT"): "M",
        ("w-010", "ADDITIVE_MANUFACTURING"): "A_WS",
    },
}


def adt_pass2_answer(model, work_id, code):
    name = ADT_PASS2_PLAN[model][(work_id, code)]
    served = {"qwen3": "qwen3-2025-07", "gemma": "gemma-3-27b"}[model]
    return letters_variant(
        name, served, "fp-a2", tokens_in_of(work_id, ADT_CODES.index(code))
    )


# --------------------------------------------------------------------------
# letter_text single answers (impact P3.2, DV reasoning layer)
# --------------------------------------------------------------------------

IMPACT_BUDGETS = {
    "coder": (6000, 20000),
    "gemma_thinking": (4000, 12000),
    "gemma": (4000, 12000),
}


def text_variant(name, served, fp, tin, budget, attempt):
    first, retry = budget
    if name == "Y":
        return chat_body("Y", served, fp, tin=tin, tout=812)
    if name == "N":
        return chat_body("N", served, fp, tin=tin, tout=640)
    if name == "Y_WS":
        return chat_body("  Y\n", served, fp, tin=tin, tout=700)
    if name == "SPENT":
        if attempt == 1:
            return chat_body(
                "Weighing the claim, the abstract says",
                served,
                fp,
                tin=tin,
                tout=first,
                finish="length",
            )
        return chat_body("N", served + "-retry", fp, tin=tin, tout=first + 3000)
    if name == "SPENT_TWICE":
        if attempt == 1:
            return chat_body(
                "Weighing", served, fp, tin=tin, tout=first, finish="length"
            )
        return chat_body(
            "Still weighing", served, fp, tin=tin, tout=retry, finish="length"
        )
    if name == "LENGTH_SHORT":
        # Cut by the server below the budget: the [WS] rule does not ask again.
        return chat_body("Weighing", served, fp, tin=tin, tout=300, finish="length")
    if name == "NULL":
        return chat_body(None, served, fp, tin=tin, tout=50)
    raise KeyError(name)


# unit (work, adt, sdg) -> (pos variant, neg variant), per model entry
IMPACT_PLAN = {
    "coder": {
        ("w-003", "AI", "SDG-07"): ("Y", "N"),
        ("w-003", "AI", "SDG-03"): ("SPENT", "Y_WS"),
        ("w-003", "AI", "SDG-13"): ("N", "N"),
        ("w-003", "COMPUTING_INFRASTRUCTURE", "SDG-03"): ("LENGTH_SHORT", "N"),
        ("w-003", "COMPUTING_INFRASTRUCTURE", "SDG-07"): ("N", "SPENT_TWICE"),
        ("w-003", "COMPUTING_INFRASTRUCTURE", "SDG-13"): ("NULL", "N"),
        ("w-010", "ADDITIVE_MANUFACTURING", "SDG-03"): ("Y", "Y"),
    },
    "gemma_thinking": {
        ("w-003", "AI", "SDG-07"): ("Y", "Y"),
        ("w-003", "AI", "SDG-03"): ("N", "N"),
        ("w-003", "AI", "SDG-13"): ("Y", "N"),
        ("w-003", "COMPUTING_INFRASTRUCTURE", "SDG-03"): ("N", "N"),
        ("w-003", "COMPUTING_INFRASTRUCTURE", "SDG-07"): ("Y_WS", "N"),
        ("w-003", "COMPUTING_INFRASTRUCTURE", "SDG-13"): ("N", "N"),
        ("w-010", "ADDITIVE_MANUFACTURING", "SDG-03"): ("Y", "SPENT"),
    },
}


def impact_answer(entry, unit, side, attempt):
    pos, neg = IMPACT_PLAN[entry][unit]
    name = pos if side == "pos" else neg
    work_id, adt, sdg = unit
    if entry == "coder":
        # One unit whose two sides were served by different models.
        if unit == ("w-003", "AI", "SDG-13"):
            served, fp = ("coder-a", "fp-c1") if side == "pos" else ("coder-b", "fp-c2")
        else:
            served, fp = "coder", "fp-c1"
    else:
        served, fp = "gemma-3-27b", None
    tin = tokens_in_of(work_id, ADT_CODES.index(adt) * 17 + SDG_CODES.index(sdg))
    return text_variant(name, served, fp, tin, IMPACT_BUDGETS[entry], attempt)


# --------------------------------------------------------------------------
# letter_text table answers (paper labels)
# --------------------------------------------------------------------------

PAPER_WORKS = ["w-003", "w-001", "w-002"]


def _adt_table(letters):
    header = "work\t" + "\t".join(ADT_CODES)
    return "=== ADT ===\n" + header + "\n1\t" + "\t".join(letters)


def _sdg_table(letters):
    header = "work\t" + "\t".join(SDG_CODES)
    return "=== SDG ===\n" + header + "\n1\t" + "\t".join(letters)


def _sdg_letters(yes):
    return ["Y" if code in yes else "N" for code in SDG_CODES]


def paper_answer(entry, exercise, work_id, attempt):
    """One work's table reply; budgets 16000 and 32000 as the paper preset."""
    served = {"coder": "coder", "gemma": "gemma-3-27b"}[entry]
    tin = tokens_in_of(work_id, 3)
    if exercise == "adt":
        if entry == "coder":
            if work_id == "w-003":
                # Fenced in backticks, with pipes: still the work line.
                text = (
                    "```\n"
                    + _adt_table(["T", "N", "M", "N", "N", "N"]).replace("\t", " | ")
                    + "\n```"
                )
                return chat_body(text, served, "fp-p1", tin=tin, tout=5000)
            if work_id == "w-001":
                if attempt == 1:
                    return chat_body(
                        "=== ADT ===\nwork\tAI\n1\tN",
                        served,
                        "fp-p1",
                        tin=tin,
                        tout=16000,
                        finish="length",
                    )
                return chat_body(
                    _adt_table(["N", "N", "N", "A", "N", "N"]),
                    served,
                    "fp-p2",
                    tin=tin,
                    tout=20000,
                )
            if work_id == "w-002":
                # No table line: unreadable, not cut, not asked again.
                return chat_body("1 N N N N N N", served, "fp-p1", tin=tin, tout=900)
        if entry == "gemma":
            if work_id == "w-003":
                # Another table first: only the ADT table is read.
                text = (
                    _sdg_table(_sdg_letters({"SDG-07"}))
                    + "\n"
                    + _adt_table(["E", "N", "N", "N", "N", "N"])
                )
                return chat_body(text, served, None, tin=tin, tout=7000)
            if work_id == "w-001":
                return chat_body(
                    _adt_table(["N", "N", "T", "A", "N", "N"]),
                    served,
                    None,
                    tin=tin,
                    tout=6500,
                )
            if work_id == "w-002":
                # A letter outside the set: unreadable.
                return chat_body(
                    _adt_table(["N", "N", "N", "N", "N", "Q"]),
                    served,
                    None,
                    tin=tin,
                    tout=800,
                )
    if exercise == "sdg":
        if entry == "coder":
            if work_id == "w-003":
                return chat_body(
                    _sdg_table(_sdg_letters({"SDG-03", "SDG-07"})),
                    served,
                    "fp-p1",
                    tin=tin,
                    tout=9000,
                )
            if work_id == "w-001":
                return chat_body(
                    _sdg_table(_sdg_letters({"SDG-14"})),
                    served,
                    "fp-p1",
                    tin=tin,
                    tout=9100,
                )
            if work_id == "w-002":
                # Two work lines: unreadable.
                text = (
                    _sdg_table(_sdg_letters(set()))
                    + "\n1\t"
                    + "\t".join(_sdg_letters(set()))
                )
                return chat_body(text, served, "fp-p1", tin=tin, tout=9200)
        if entry == "gemma":
            if work_id == "w-003":
                return chat_body(
                    _sdg_table(_sdg_letters({"SDG-07"})),
                    served,
                    None,
                    tin=tin,
                    tout=8000,
                )
            if work_id == "w-001":
                if attempt == 1:
                    return chat_body(
                        "=== SDG ===\n1\tN\tN",
                        served,
                        None,
                        tin=tin,
                        tout=16000,
                        finish="length",
                    )
                return chat_body(
                    _sdg_table(_sdg_letters({"SDG-12"})),
                    served,
                    None,
                    tin=tin,
                    tout=30000,
                )
            if work_id == "w-002":
                return chat_body(
                    _sdg_table(_sdg_letters(set())), served, None, tin=tin, tout=4000
                )
    raise KeyError((entry, exercise, work_id, attempt))


# --------------------------------------------------------------------------
# json_object impact_pairs_v1 answers (paper impact)
# --------------------------------------------------------------------------


def paper_impact_answer(entry, work_id, pairs, source_text, attempt):
    """One work's JSON reply over its pairs, `pairs` the (adt, sdg) in asked order."""
    served = {"coder": "coder", "gemma": "gemma-3-27b"}[entry]
    tin = tokens_in_of(work_id, 11)
    items = []
    for n, (adt, sdg) in enumerate(pairs, start=1):
        items.append(
            {
                "pair": f"P{n}",
                "beneficial": "N",
                "beneficial_kind": "none",
                "beneficial_quote": "",
                "detrimental": "N",
                "detrimental_quote": "",
            }
        )
    sentence = source_text.split("\n")[1].split(". ")[0] if "\n" in source_text else ""
    if entry == "coder" and work_id == "w-003":
        # P1 beneficial with a quote copied from the abstract; P2 a quote not in the text.
        items[0].update(
            beneficial="Y", beneficial_kind="outcome", beneficial_quote=sentence
        )
        if len(items) > 1:
            items[1].update(detrimental="Y", detrimental_quote="Outages doubled.")
        text = "Here is the object:\n" + json.dumps({"pairs": items}) + "\nDone."
        return chat_body(text, served, "fp-i1", tin=tin, tout=20000)
    if entry == "coder" and work_id == "w-001":
        if attempt == 1:
            return chat_body(
                '{"pairs": [{"pair": "P1", "benef',
                served,
                "fp-i1",
                tin=tin,
                tout=32000,
                finish="length",
            )
        items[0].update(
            beneficial="Y", beneficial_kind="utility", beneficial_quote=sentence
        )
        return chat_body(
            json.dumps({"pairs": items}), served, "fp-i2", tin=tin, tout=40000
        )
    if entry == "gemma" and work_id == "w-003":
        # Pairs numbered wrong: unreadable, not cut, not asked again.
        bad = [dict(item, pair=f"P{n + 2}") for n, item in enumerate(items)]
        return chat_body(json.dumps({"pairs": bad}), served, None, tin=tin, tout=15000)
    if entry == "gemma" and work_id == "w-001":
        # A Y with an empty quote: readable, quotes not ok. An extra key is allowed.
        items[0].update(
            beneficial="Y",
            beneficial_kind="outcome",
            beneficial_quote="  ",
            confidence="high",
        )
        return chat_body(
            json.dumps({"pairs": items}), served, None, tin=tin, tout=16000
        )
    return chat_body(json.dumps({"pairs": items}), served, None, tin=tin, tout=12000)


# --------------------------------------------------------------------------
# divergence-validation layers on a file of units
# --------------------------------------------------------------------------

DV_UNITS = [
    ("w-003", "AI", "SDG-07"),
    ("w-003", "AI", "SDG-13"),
    ("w-002", "ROBOTICS", "SDG-03"),
    ("w-010", "ADDITIVE_MANUFACTURING", "SDG-03"),
]


def dv_p2_answer(entry, unit, side):
    """Single-token Y/N answers of the [DV] logprob layer (exact spelling)."""
    served = {"gemma": "gemma-3-27b", "mistral_small": "mistral-small-3.2"}[entry]
    tin = tokens_in_of(unit[0], 2 * DV_UNITS.index(unit) + (side == "neg"))
    plan = {
        "gemma": {
            DV_UNITS[0]: ("Y_SUM", "N_SPACE"),
            DV_UNITS[1]: ("NULL_CONTENT_Y", "N"),
            DV_UNITS[2]: ("REPEAT", "N"),
            DV_UNITS[3]: ("Y", "OTHER"),
        },
        "mistral_small": {
            DV_UNITS[0]: ("Y", "N"),
            DV_UNITS[1]: ("NO_CHOICES", "N"),
            DV_UNITS[2]: ("N", "N"),
            DV_UNITS[3]: ("SPACE_ONLY", "Y"),
        },
    }
    name = plan[entry][unit][0 if side == "pos" else 1]
    if name == "Y":
        return token_body(
            "Y", [("Y", [("Y", -0.1), ("N", -2.4)])], served, "fp-d", tin=tin
        )
    if name == "N":
        return token_body(
            "N", [("N", [("N", -0.2), ("Y", -1.8)])], served, "fp-d", tin=tin
        )
    if name == "NO_CHOICES":
        body = chat_body("Y", served, "fp-d", tin=tin, tout=1)
        body["choices"] = []
        return body
    if name == "SPACE_ONLY":
        # Only spelled with a space: exact reading finds no letter.
        entries = [(" Y", [(" Y", -0.3), (" N", -1.5)])]
        return token_body(" Y", entries, served, "fp-d", tin=tin)
    return yn_variant(name, served, "fp-d", tin)


def dv_p3_answer(unit, side, attempt):
    """letter_text answers of the [DV] reasoning layer, gemma with thinking on."""
    plan = {
        DV_UNITS[0]: ("Y", "N"),
        DV_UNITS[1]: ("SPENT", "N"),
        DV_UNITS[2]: ("N", "SPENT_TWICE"),
        DV_UNITS[3]: ("Y_WS", "LENGTH_SHORT"),
    }
    name = plan[unit][0 if side == "pos" else 1]
    tin = tokens_in_of(unit[0], 2 * DV_UNITS.index(unit) + (side == "neg"))
    return text_variant(name, "gemma-3-27b", "fp-t", tin, (4000, 12000), attempt)


# --------------------------------------------------------------------------
# writing fixtures
# --------------------------------------------------------------------------


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def table_fixture(columns, dtypes, rows):
    """An expected table: column names in order (run_id included), dtypes of all but
    run_id, and rows (lists in the order of the columns without run_id), sorted."""
    return {"columns": columns, "dtypes": dtypes, "rows": rows}
