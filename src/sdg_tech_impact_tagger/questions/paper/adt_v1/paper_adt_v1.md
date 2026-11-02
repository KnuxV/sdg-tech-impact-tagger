# Paper level: technologies, version 1

One call per work for the six advanced digital technologies at once. The
message holds the ADT codebook (the wording of ADT pass 2 of protocol v1,
with each technology's definition and boundary rules) and asks for a table
with one letter per technology: E, A, T, M or N.

First run in `wos_paper_sample`, where a script generated it from the
annotation packet of that repository, for a batch of one work numbered 1.
Status: experimental. It ships as it was run, so that its id matches
the runs, with a known fault: the codebook it embeds tells the model to
answer with a single letter, while the outer instruction asks for a table.

Prompt id `adt1-d95d2cfc8f17`: the sha256 of SYSTEM, a newline, then
USER_TEMPLATE.

Placeholders: `{title}` and `{abstract}` in USER_TEMPLATE, replaced as
plain text, not by `str.format`.

Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), see
`LICENSE-DATA.md`.

Only the fenced `text` blocks under the `## NAME` headings below count
toward the prompt id; this header does not. The blocks are byte for byte
those of the earlier runs and are never edited: a changed wording is a new
question under a new name.

## SYSTEM

```text
You are annotating scholarly works. Everything you need is in the message. Use no other source.
```

## USER_TEMPLATE

```text
There is one exercise. Its instructions are given below word for word. Each question is answered alone: the answer for one technology does not depend on the others.

EXERCISE ADT. For EACH work and EACH of the six technologies, answer as the ADT instructions say, with one letter: E, A, T, M or N. That is six letters per work.

Read each work in full before answering. Then reply with the table and nothing else: the line === ADT ===, then tab-separated lines, one per work, with this header line first:
work	AI	IOT	COMPUTING_INFRASTRUCTURE	BLOCKCHAIN	ROBOTICS	ADDITIVE_MANUFACTURING
'work' is the work number given below (for example 1).

=== ADT CODEBOOK ===

## INSTRUCTIONS

You decide how a scholarly work, read through its title and abstract, relates to one advanced digital technology.

First decide whether the technology, as its definition and boundary rules describe it, is in the text at all. Then, if it is, decide the relation between the authors and the technology.

Answer with exactly one letter:

E  External. The technology as it exists in the world is what the work studies: its adoption, effects, costs, risks, performance, perception or governance, where the instance belongs to others.
A  Artefact. The authors build, propose, design or adapt the technology, or a system made from it, and offer it as their contribution.
T  Tool. The authors use the technology to obtain a result about something else.
M  Mention. The technology is in the text, but the authors do nothing with it and it is not what the work studies.
N  The technology is not in the text. It is neither named nor described, or the word means something else, or the text names only a broad label and no instance of the technology.

Rules that apply to every technology:

- Judge only from the title and the abstract as written. The abstract may be empty or may hold other text, such as a table of contents: judge what is there. A technology the text describes in its own terms without its usual name is in the text. A technology the text neither names nor describes is not, however likely: a statistical analysis was run on some computer, a survey was hosted on some website, and neither is evidence of anything.
- A broad label is not a technology. Industry 4.0 or 5.0, the fourth industrial revolution, Society 5.0, digital transformation, digitalisation, digital technologies, digital twin, smart manufacturing, intelligent manufacturing, digital manufacturing, smart city, smart farming, precision agriculture and metaverse are not evidence by themselves; judge the named technologies the text describes under them.
- A word or abbreviation used in another sense is not the technology, and the answer is N.
- A text can involve several technologies. Judge only the one you are asked about.

How to choose between E, A, T and M once the technology is in the text:

- E applies when what the work says is about the technology as it exists in the world, deployed, adopted, sold, regulated or anticipated by others. A study of the effect of AI adoption on emissions, a survey of farmers' drone use, a test of an off-the-shelf chatbot and a policy framework for blockchain are E. If the authors built the instance, it is A, however thoroughly they evaluate it.
- A is what is offered. If the text presents the model, system, method or device as what the authors propose, develop or introduce, it is A, even when they also apply it to a domain problem. A system the authors plan or propose to build, in a protocol or project description, is also A. If they used an existing technology and the contribution is the finding about the domain, it is T. A system built for an environment ("a routing method designed for sensor networks") is A for the technology built, M for the environment.
- A built and then tested remains A, whether tested in a trial, a deployment or a simulation.
- T needs a signal. The text must show the authors doing something with the technology to get a result, in any voice: "we applied a random forest", "images were classified using a neural network", "processed in Google Earth Engine". Tuning a model, or comparing existing algorithms that the authors train or fit themselves for a result about the domain, is still T; testing a product or system deployed by others is E. A technology in the text without such a signal is M.
- M covers the rest: a fact about the technology, a comparison with it, the setting ("in the age of AI"), an intended application the authors name without building or using it ("a material for soft robotics", "suitable for 5G"), a platform or hardware named only as where something is hosted, stored or ran ("hosted on AWS", "trained on a GPU"), or future work named in passing.
- When the abstract is empty, the title is the text and is signal enough: a title presenting the technology as built, used or studied is A, T or E; it is M only when it names the technology as a setting or an intended application. A title that names neither the technology nor one of its methods is N, however likely the technology is behind its topic.
- Reviews of the literature: answer for the technology's role in the work reviewed. A review of models or methods that use the technology is T, or A when it surveys proposed architectures or techniques; a review of the technology's adoption, effects, costs or governance is E.

Answer with a single letter: E, A, T, M or N. Output nothing else.

## AI

**Artificial intelligence and big data analytics**

Systems that infer from their input how to produce outputs such as predictions, content, recommendations or decisions: machine learning and deep learning of every kind, and logic- and knowledge-based approaches such as expert systems. This includes big data analytics and data mining presented as the method of analysis.

Boundary rules:

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

## IOT

**Internet of Things**

Physical devices and objects that sense or act and are connected to a network, with the services that collect, exchange and process their data.

Boundary rules:

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

## COMPUTING_INFRASTRUCTURE

**Computing infrastructure**

Shared or specialised computing and network resources: cloud, edge and fog computing, data centres, high-performance and quantum computing, accelerator hardware, big data platforms, and mobile networks such as 5G. Ordinary computers and generic software are not meant.

Boundary rules:

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

## BLOCKCHAIN

**Blockchain**

A ledger shared across a network of computers, in which records are grouped into blocks linked by cryptographic hashes and validated by a consensus mechanism, and the applications built on it, cryptocurrencies included.

Boundary rules:

Counts as blockchain:
- Blockchains and distributed ledgers, smart contracts, crypto tokens and non-fungible tokens, decentralised finance, the consensus mechanisms and mining of a ledger.
- Cryptocurrencies, including cryptocurrencies studied as financial assets: prices, volatility, hedging, market behaviour.

Does not count as blockchain:
- Encryption and cryptography with no ledger.
- A ledger in the accounting sense.
- Consensus among agents, sensors or clinicians with no ledger; digital assets meaning files or IT resources.

## ROBOTICS

**Robotics**

Programmed physical machines that sense and act on their environment with a degree of autonomy, to move, manipulate or position: industrial, service, medical and mobile robots, drones and other unmanned or self-driving vehicles. Software with no physical body, such as a chatbot, is not a robot.

Boundary rules:

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

## ADDITIVE_MANUFACTURING

**Additive manufacturing**

A computer-controlled production technology that creates three-dimensional objects by joining materials layer by layer.

Boundary rules:

Counts as additive manufacturing:
- 3D printing and additive manufacturing of any material: polymer, metal, ceramic, concrete, food, bioprinting.
- Rapid prototyping when it produces physical parts layer by layer.

Does not count as additive manufacturing:
- Manufacturing in general, CNC machining, moulding, casting, subtractive processes, smart manufacturing.
- Industry 4.0 by itself.
- Rapid prototyping of software, interfaces or designs.
- A process name used in another trade, such as electron-beam melting to refine a metal.


=== THE WORKS ===

--- Work 1 ---
Title: {title}
Abstract: {abstract}
```
