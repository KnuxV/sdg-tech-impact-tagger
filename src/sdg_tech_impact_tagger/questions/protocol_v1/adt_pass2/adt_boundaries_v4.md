# ADT boundaries, protocol v1

One block per advanced digital technology, under its code: the rules that
tell the technology from what is not it, shown by ADT pass 2 for the unit's
technology as `{boundaries}`. A block holds no name line; the name comes
from `adt_descriptions_v3.md`.

First run in `open_alex_adt_gate`. Status: frozen, protocol v1 (2026-10-08),
version 4. Each block is hashed alone, with the prefix `adtbound-<slug>`,
the slug being the code lower cased with underscores turned into hyphens.
The ids are listed in `IDS.tsv` at the root of the questions.

Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), see
`LICENSE-DATA.md`.

Only the fenced `text` blocks under the `## NAME` headings below count
toward the prompt id; this header does not. The blocks are byte for byte
those of the earlier runs and are never edited: a changed wording is a new
question under a new name.

## AI

```text
Counts as AI:
- Any model learned from data: machine learning and deep learning of every kind, including conventional methods such as random forests, gradient boosting, support vector machines, k-nearest neighbours, k-means and other clustering, and neural networks; computer vision, natural language processing, language models and reinforcement learning.
- Also, although not all learn from data: Bayesian networks, fuzzy logic systems, expert systems and rule-based AI, and topic models such as LDA.
- Chatbots and conversational agents, and robotic process automation.
- Evolutionary and swarm methods: genetic and evolutionary algorithms, particle swarm, ant colony, differential evolution, swarm intelligence.
- Big data analytics and data mining when the text presents them as the method of analysis. "Big data" named only as a setting ("in the era of big data") is M.

Does not count as AI:
- Classical statistics, also when used to predict: regression models (linear, logistic, panel, spatial, and penalised regression such as lasso, ridge or elastic net), analysis of variance, correlation, descriptive statistics, time series models such as ARIMA, and forecasts from trends. Such a model counts only when the text itself presents it as machine learning or evaluates it alongside machine learning models.
- Words that only qualify a system or a task: intelligent, smart, automated, digital, or a task named without its method (prediction, classification, recognition, detection, feature extraction or selection, optimisation). The text must name or describe a learned model or one of the methods above.
- Simulated annealing, and linear or integer programming.
- Simulation and modelling without learning, and signal processing without learning.
- Big data platforms and software, such as Hadoop or Spark: they are computing infrastructure, not AI.
- Virtual, augmented and mixed reality and the metaverse by themselves. A learned model used inside such a system counts for that model.
- Other senses of the words: an electrical power transformer; a diffusion model of heat, particles, prices or innovations; Albert or Ann as a name; active learning or a learning model as a way of teaching; pattern recognition receptors; computer vision syndrome; "neural" in the biological sense.
```

## IOT

```text
Counts as Internet of Things:
- Networked devices that sense or act and exchange data: IoT systems, wireless sensor networks, body area networks, smart meters, connected smart home devices.
- Wearables that send their data to a phone, a network or a platform.
- Cyber-physical systems in which networked sensing and actuation is described.
- RFID or other tags that report to a networked system; smart grids when connected metering or control is described.

Does not count as Internet of Things:
- A sensor, meter, instrument or microcontroller board that is not connected to anything.
- A phone, tablet or computer by itself.
- Monitoring from a distance with no connected device described, remote sensing included.
- Sensor materials, and wearable materials or textiles, studied for their physical properties, and any wearable device that does not communicate.
- Cyber-physical systems described only as autonomous physical agents (that is Robotics) or only as computing (that is not IoT).
```

## COMPUTING_INFRASTRUCTURE

```text
Counts as computing infrastructure:
- Cloud computing, edge and fog computing, high-performance computing and supercomputers, data centres.
- Big data platforms, software and distributed data systems: Hadoop, MapReduce, Spark, Kafka, NoSQL stores, data warehouses, distributed file systems.
- 5G and other mobile network generations as network infrastructure, and 5G or 6G network components: antennas, base-station and device hardware, chips.
- Quantum computing only: quantum computers, processors, qubits, circuits, algorithms, annealing, error correction, quantum software.
- Computing hardware: FPGA, GPU, system-on-chip, accelerators, neuromorphic and photonic hardware.
- A named cloud platform, such as Google Earth Engine or a commercial cloud service.
- Role of a platform, network component or hardware: A when the authors design it; T when the text presents the work as done with it as part of the method; M when it is named only as an intended use or as where something is hosted, stored or ran.

Does not count as computing infrastructure:
- Ordinary computers, laptops, phones, and computation in general: that an analysis was computed is not evidence of infrastructure.
- The internet, Wi-Fi, Bluetooth, ordinary databases, generic software, apps, websites, online platforms and social media.
- Remote sensing, satellites, GIS and geospatial data by themselves.
- Quantum key distribution, quantum communication and quantum sensing, unless the text ties them to quantum computing.
- Infrastructure the text neither names nor describes, however likely it is that the study used some.
- Other senses of the words: 5g or 6g as a compound label, a dye, a mass or a gene variant; a point cloud or a weather cloud; quantum-mechanical simulation of molecules; AWS not meaning the cloud service; a data center named only as a data source.
```

## BLOCKCHAIN

```text
Counts as blockchain:
- Blockchains and distributed ledgers, smart contracts, crypto tokens and non-fungible tokens, decentralised finance, the consensus mechanisms and mining of a ledger.
- Cryptocurrencies, including cryptocurrencies studied as financial assets: prices, volatility, hedging, market behaviour.

Does not count as blockchain:
- Encryption and cryptography with no ledger.
- A ledger in the accounting sense.
- Consensus among agents, sensors or clinicians with no ledger; digital assets meaning files or IT resources.
```

## ROBOTICS

```text
Counts as robotics:
- Robots of every kind: industrial, service, social, surgical and agricultural robots, robotic arms, robotic exoskeletons.
- Drones and unmanned aerial, ground, surface or underwater vehicles, including a drone used only to carry a camera or sensor.
- Cyber-physical systems described as autonomous physical agents.
- Autonomous and self-driving vehicles, ships and trucks.

Does not count as robotics:
- Chatbots and other software agents: they are AI, not robotics, unless embodied in a physical robot.
- Automation in general without a robot: process control, conveyors, programmable logic controllers.
- Robotic process automation, which is software with no physical agent: it is AI, not robotics.
- Other senses of the words: an animal's exoskeleton; a drone bee; UAS not meaning unmanned aircraft; an unattended ("unmanned") instrument; a "robot advisor" in finance.
```

## ADDITIVE_MANUFACTURING

```text
Counts as additive manufacturing:
- 3D printing and additive manufacturing of any material: polymer, metal, ceramic, concrete, food, bioprinting.
- Rapid prototyping when it produces physical parts layer by layer.

Does not count as additive manufacturing:
- Manufacturing in general, CNC machining, moulding, casting, subtractive processes, smart manufacturing.
- Industry 4.0 by itself.
- Rapid prototyping of software, interfaces or designs.
- A process name used in another trade, such as electron-beam melting to refine a metal.
```
