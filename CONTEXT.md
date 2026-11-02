# Context: the words of this repository

Use these words, with these meanings, in code, docs, tests and commits.

| word | meaning |
|---|---|
| **text** | what the model reads about one work, as named fields of the input table (`title`, `abstract`, an answer to a survey, a section of a full text). |
| **work** | one row of the input table: an id and its text fields. |
| **list** | a set of labels with, for each, an id, a name and any material a question shows about it (definition, boundaries, targets). The SDGs and the ADTs are lists; so are themes or harm types. |
| **level** | the shape of a unit: `work`, `work x list`, or `work x list x list`. |
| **unit** | one thing a question is asked about: a work, a (work, label) pair, a (work, label, label) triple. |
| **question** | one prompt version: its template blocks, the lists it uses, its level, its readout, its letter set and its budgets. A question is identified by its **prompt id**, a hash of its blocks. |
| **readout** | how an answer is turned into a label: `score_json`, `letter_logprob`, `letter_text`, `json_object`. |
| **pass** | one question asked over a set of units with one model, resumable, writing one table. |
| **unit rule** | how a pass's units are chosen from the works and earlier passes: `all`, `threshold`, `cross`, `file`. |
| **source** | an earlier pass's table, for one model, read by a unit rule. |
| **workflow** | passes chained by unit rules, written in one TOML file. A **preset** is a workflow shipped with the package. |
| **model** | an entry of the workflow: an endpoint, the name of the environment variable holding the key, the model name sent, and settings. **Model served** is the name the endpoint reports in its answer. |
| **run** | one execution of a pass for one model: a work directory, a cache, a manifest. |
| **cache** | one file per call holding the raw answer, under a key that hashes the request. |
| **replay** | rebuilding a pass's table from a cache alone, without the network. |

## Words to avoid

- "classifier", "predictor": say question, pass or model.
- "gate", "screen" for a pass: say pass 1, or name the question.
- "prompt" for a question as a whole: a question holds prompt blocks plus how
  its answer is read.
- "pair" for a (work, technology, goal) unit: say triple; a pair is
  (work, label).
- "P1", "P2", "P3" as names: they meant different things in different
  repositories. Use the question's name.
- "WoS id" or `wos_id` for the id of a work: say id.
