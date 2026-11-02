# AGENTS.md - operating rules for AI sessions on this repository

This repository is a Python package that labels texts with an LLM behind any
OpenAI-compatible endpoint: sustainable development goals (SDGs), advanced
digital technologies (ADTs), the impact of a technology on a goal, or any
other list of labels. It gathers into one tested package the labelling code
that earlier research repositories each carried a copy of. Those runs are the
oracle: given the raw answers they cached, the package must rebuild the
tables they wrote, row for row. Your job is to add code, prove it with tests,
and leave a trace. You do not make design decisions.

## Start of every session

1. Read `README.md`, `CONTEXT.md`, the last three entries of `JOURNAL.md`, and
   `DECISIONS.md` in full. Read `docs/contract.md` before touching code. Use
   the words of `CONTEXT.md` and none of the words it says to avoid.
2. Run `git status`. The tree should be clean apart from ignored paths. If it
   is not, report what is there and ask before touching it: Kevin edits this
   repository by hand, and another session may own a change.
3. Run `uv run ruff check .`, `uv run ruff format --check .` and, once tests
   exist, `uv run pytest -q`. If one is not clean, report it and fix or ask
   before doing anything else.
4. Run `sha256sum -c src/sdg_tech_impact_tagger/questions/SHA256SUMS` once
   that file exists. If a shipped question file has changed, stop and report.
5. State in one paragraph what you are about to do.

## Things you never do

- Read, list, search or copy anything in
  `../scientific-publication-retrieval-2023-2025`, and never write to it.
- Edit a shipped question. A question is identified by the hash of its
  blocks, and that id is cited in published work. A changed question is a new
  question with a new name; the old one stays.
- Put the text of a real document in a committed file. The earlier runs read
  Web of Science and OpenAlex titles and abstracts; none of that text appears
  in a test, a fixture, a doc, a journal entry or a commit message. Fixtures
  are texts and model answers you write yourself. Caches of earlier runs are
  read in place, never copied into this repository.
- Commit an API key, a `.env` file or a cache directory. Keys are read from
  the environment variable the configuration names.
- Make a design choice without a `DECISIONS.md` entry. What a pass returns,
  how an answer is read, which units a rule selects, what is cached and under
  which key, and what counts as reproducing an earlier run are decisions.
- Edit a test file during an implementation session. Tests are read-only for
  the implementer; if a test looks wrong, say so in the journal and stop.
- Assert a count, an agreement rate or a timing you have not computed
  yourself. Report a discrepancy, never smooth it over.
- Call a paid endpoint from a test. Tests use recorded or hand-written
  responses.
- Rewrite history: never force push, amend or rebase a commit from an earlier
  session, or revert another session's work.
- Use em dashes in any prose you write.

## How a piece of work is built

Order is fixed: contract, test, implementation, each its own commit.

1. **Contract.** `docs/contract.md` states what goes in and what comes out:
   inputs, output schemas, and what happens to an input that does not fit.
   Behaviour taken from an earlier repository names the file it comes from.
2. **Test.** In a session that has not seen the implementation, write the
   tests from the contract and from small hand-written fixtures. Assert exact
   rows, not shapes. The tests that count go through the public Python
   interface or the command.
3. **Implementation.** Written against the tests, which are not edited.

Reproducing the earlier runs from their caches is measured, reported and
journalled. It is not a unit test, because the caches hold licensed text and
stay outside the repository.

## Code conventions

- `uv` for everything; never `pip install`.
- Polars for data; pandas only at a library boundary, converted back at once.
- `httpx` for HTTP; no provider SDK.
- Every public function has a docstring stating its contract in terms of what
  it consumes and produces. Comments explain intent, not syntax.
- `ruff check` and `ruff format` clean before the session ends.

## Version control

- One commit per completed unit of work, when ruff and the tests are clean.
- Run `git status` before every commit and stage only the files you wrote.
  Never commit a file you did not touch, and never commit Kevin's uncommitted
  edits.
- Subject line short and imperative, saying what changed. Add a body when the
  why is not obvious.
- Kevin pushes. Do not push.

## End of every session

1. Ruff and the tests. Do not close green if one fails; say what failed.
2. Append to `JOURNAL.md`:

```
## YYYY-MM-DD HH:MM  <topic>
Done: ...
Tests added: ...
Open / unsure: ...
```

Terse, chronological, never edited after the fact.

3. Commit the journal entry as the last commit of the session.

## When you are unsure

Stop and ask. A question in the journal costs nothing; an invented design
choice costs the package. In particular, anything about which questions
ship, how an answer is read, how models are combined and what counts as
reproducing an earlier run is Kevin's.
