# ADT descriptions, protocol v1

One block per advanced digital technology, under its code: the display name
on the first line, a blank line, then a short definition. ADT pass 1 shows
all six; ADT pass 2 shows the unit's technology as `{technology}` and
`{definition}`. The same file serves both passes and is shipped beside
each.

First run in `open_alex_adt_gate`. Status: frozen, protocol v1 (2026-10-08),
revision 3. Ids: `adtdesc-e8f65488c44f` over the six blocks in the order
below (ADT pass 1), and `adtdesc-<slug>-<hash>` over one block alone (ADT
pass 2), the slug being the code lower cased with underscores turned into
hyphens. All are listed in `IDS.tsv` at the root of the questions.

Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), see
`LICENSE-DATA.md`.

Only the fenced `text` blocks under the `## NAME` headings below count
toward the prompt id; this header does not. The blocks are byte for byte
those of the earlier runs and are never edited: a changed wording is a new
question under a new name.

## AI

```text
Artificial intelligence and big data analytics

Systems that infer from their input how to produce outputs such as predictions, content, recommendations or decisions: machine learning and deep learning of every kind, and logic- and knowledge-based approaches such as expert systems. This includes big data analytics and data mining presented as the method of analysis.
```

## IOT

```text
Internet of Things

Physical devices and objects that sense or act and are connected to a network, with the services that collect, exchange and process their data.
```

## COMPUTING_INFRASTRUCTURE

```text
Computing infrastructure

Shared or specialised computing and network resources: cloud, edge and fog computing, data centres, high-performance and quantum computing, accelerator hardware, big data platforms, and mobile networks such as 5G. Ordinary computers and generic software are not meant.
```

## BLOCKCHAIN

```text
Blockchain

A ledger shared across a network of computers, in which records are grouped into blocks linked by cryptographic hashes and validated by a consensus mechanism, and the applications built on it, cryptocurrencies included.
```

## ROBOTICS

```text
Robotics

Programmed physical machines that sense and act on their environment with a degree of autonomy, to move, manipulate or position: industrial, service, medical and mobile robots, drones and other unmanned or self-driving vehicles. Software with no physical body, such as a chatbot, is not a robot.
```

## ADDITIVE_MANUFACTURING

```text
Additive manufacturing

A computer-controlled production technology that creates three-dimensional objects by joining materials layer by layer.
```
