# Buy or Wait? Financial Decision Agent

Deterministic, multimodal financial decision pipeline that projects 90-day cash flow trajectories to evaluate purchase requests against user safety constraints, scheduled commitments, and payment options.

## Quick Start

### 1. Requirements and Setup

Install Python dependencies (Python 3.10+):

```bash
pip install -r requirements.txt
```

Set environment variables if running live OCR (optional):

```bash
cp .env.example .env
# Set MISTRAL_API_KEY in .env if running live OCR calls.
# Offline mode is enabled by default via pre-warmed image cache.
```

### 2. Execution

Generate predictions for all 250 evaluation requests:

```bash
python main.py
```

Run benchmark against the 25 golden sample requests:

```bash
python evaluation/main.py
```

### 3. Architecture Overview

- `main.py`: Entrypoint for full-dataset prediction and validation.
- `src/data/`: Typed models, CSV loaders, and dated FX converters.
- `src/evidence/`: Document OCR engine with offline fallback cache and multilingual message parser.
- `src/ledger/`: Pending debit holds, event normalization, and recurring stream interval detection.
- `src/simulation/`: 90-day daily balance simulation and analytical solvers.
- `src/planner/`: Candidate plan generation, flexible spending optimizer, and 5-tier ranker.
- `src/explainer/`: Grounded, fact-based natural language justifications.
- `src/validation/`: 14 HackerRank schema and domain validation assertions.
- `evaluation/`: Token usage accounting and golden sample benchmark.
