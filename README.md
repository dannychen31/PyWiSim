# Evaluating Two-Phase Commit over Lossy and Mobile Wireless Links

This repository contains a small simulation study of commit-style coordination over lossy and mobile wireless links. It uses PyWiSim as the event-driven simulator and compares three protocol:

- `ONE_SHOT`: the coordinator sends COMMIT once and does not wait for replies
- `2PC`: a basic two-phase commit implementation with prepare, vote, and decision phases
- `2PC_RETRY`: a retry-based 2PC variant with vote timeouts, retransmissions, and decision acknowledgments

## Repository Contents

* `baseline_one_shot.py` — one-shot baseline
* `tpc_basic.py` — plain two-phase commit
* `tpc_retry.py` — 2PC extended with vote timeouts, retransmissions, and decision acknowledgments
* `mobility.py` — waypoint-style node mobility
* `experiment.py` — sweeps over node counts, loss parameters, and seeds to generate the evaluation dataset
* `make_figures.py` — aggregates results and generates plots
* `data/` — generated CSV outputs
* `figures/` — generated plots

## Prerequisites

The simulation requires Python 3. Only need standard library modules to run the core simulation, plus `matplotlib` and `pandas` to generate figures.

```bash
pip install matplotlib pandas
```

## Reproducing the Results

To regenerate the results reported in the paper:

1. **Run the experiments:**
   Execute the experiment driver to run all trials. This sweeps the defined parameter space (loss levels, $n \in \{3,5,8\}$, static vs. mobile) across 30 random seeds.
   ```bash
   python src/experiment.py
   ```
   This generates `data/results.csv` and `data/README_results.txt`.

2. **Generate the figures:**
   Process the raw CSV data into averaged summaries and create the plots.
   ```bash
   python src/make_figures.py
   ```
   This generates `data/summary_by_n_loss.csv` along with `.jpg` figures for completion rate, coordinator decision rate, latency, message count, and incomplete delivery.

## Simulation Setup

The current experiment configuration uses:

- protocols: `ONE_SHOT`, `2PC`, `2PC_RETRY`
- participants: `3`, `5`, `8`
- loss settings: `0.0`, `0.1`, `0.2`, `0.3`, `0.4`
- scenarios: static and mobile
- seeds: `0` through `29` (per setting)

## Summary

The paper evaluated three commit-style protocols over lossy and mobile wireless links: a one-shot baseline, basic two-phase commit, and a retry-based 2PC variant. The main result is a tradeoff. The one-shot baseline has the lowest message cost, but it frequently leaves only part of the system with a final decision. Basic 2PC loses completion quickly as the configured loss setting increases. Adding timeouts, retransmissions, and decision acknowledgments improved completion and coordinator decision rates in the tested scenarios, especially in the static case and in moderate-loss mobile settings, but those gains came with higher latency and much larger message overhead.