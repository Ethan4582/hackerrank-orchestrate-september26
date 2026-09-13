# Buy or Wait Financial Decision Agent — System Design and Technical Approach

> An autonomous, deterministic financial decision system that evaluates purchase requests against 90-day cash flow projections, recurring obligations, and multimodal evidence.

---

## Problem statement

Personal finance applications frequently fail users by answering affordability questions with a single number: the current account balance. A user who sees 2,000 USD in their account may commit to a 600 USD purchase today, only to default on rent or drop below their required emergency reserve ten days later when scheduled commitments clear.

The Buy or Wait agent evaluates each purchase or payment request in `dataset/requests.csv` against the user's financial profile, transaction history, currency conversion rates, and untrusted multimodal artifacts (receipt images and employer text messages). For every request, the agent outputs a safe payment amount, an affordability classification, an optimal payment plan, and a transparent explanation.

---

## Goals and non-goals

### Goals

- Deliver deterministic recommendations across all 250 evaluation requests.
- Guarantee that account balance $B(t) \ge B_{\text{min}}$ on every day $t \in [0, 90]$.
- Extract unstated amounts from document images and parse employer text updates without manual intervention.
- Support four distinct payment paths: immediate full payment, provider installments, two-stage partial payments, and delayed payment.
- Strictly satisfy all 14 HackerRank schema and domain validation invariants (R01 to R14).

### Non-Goals

- Speculative market prediction or investment return forecasting.
- Live external banking or market-data network calls during evaluation runs.
- Interactive user interfaces or frontend web presentation.

---

## System requirements

### Functional requirements

- Read all input datasets directly from `dataset/`: user profiles, historical events, exchange rates, requests, payment options, messages, and image metadata.
- Reconstruct current available cash, pending debit reservations, and recurring cash flow streams for each user.
- Resolve missing transaction amounts using multimodal document OCR.
- Parse text messages to detect confirmed salary revisions, effective dates, contract terminations, and bonus conditions.
- Test plan feasibility across a 90-day simulation window.
- Rank competing safe options using a strict five-tier priority order.
- Emit the final predictions to `output.csv` with exactly eight required columns.

### Non-functional requirements

- **Determinism**: Identical inputs must yield bit-for-bit identical outputs on every run.
- **Latency**: Total execution time for all 250 requests must stay below 5 seconds.
- **Cost efficiency**: Zero model inference cost during local simulation runs.
- **Reliability**: Zero crashes or unhandled exceptions when encountering foreign currencies, missing fields, or conflicting evidence.

---

## Capacity and execution metrics

The entire evaluation suite runs locally within a single process.

| Metric | Measured value |
|---|---|
| Evaluation requests | 250 |
| Historical transaction events | 2,000+ |
| Document images resolved | 16 PNG images |
| User and employer messages parsed | 35 messages |
| Full pipeline runtime | 1.58 seconds |
| Average latency per request | 6.32 ms |
| Validation error count | 0 errors across R01 to R14 |

---

## High-level design

The pipeline consists of five decoupled layers. Each layer transforms raw inputs into structured domain objects without cyclic dependencies.

```
+-------------------------------------------------------------------------+
|                               Input data                                |
|  requests.csv | financial_profiles.csv | financial_events.csv           |
|  exchange_rates.csv | request_payment_options.csv | messages.csv | images|
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                      1. Evidence extraction layer                       |
|  - ocr_engine.py: Document parsing via Mistral OCR and offline cache    |
|  - message_parser.py: Multilingual regex parser for salary and contract |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                       2. Ledger and state layer                         |
|  - currency.py: Fixed-rate dated conversion into user home currency     |
|  - state.py: Active event filtering and pending debit hold reservation   |
|  - recurring.py: Interval discovery and monthly recurring projection    |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                    3. Cash flow simulation engine                       |
|  - engine.py: Daily balance projection B(t) across 90-day horizon        |
|  - solvers.py: Binary search for safe headroom and earliest date        |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                   4. Candidate generation and ranking                   |
|  - candidate_gen.py: Generates full, wait, and not_recommended plans     |
|  - schedule_options.py: Generates installment and partial payment plans |
|  - spending_solver.py: Solves minimal permitted flexible reductions     |
|  - ranker.py: Lexicographical sorting over decision priorities          |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                    5. Explainer and validation layer                    |
|  - generator.py: Structured explanation writer with exact amounts       |
|  - validator.py: 14-rule compliance verifier                            |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                        output.csv (250 rows)                            |
+-------------------------------------------------------------------------+
```

---

## Low-level design and algorithms

### 1. Evidence extraction

Financial evidence arrives in two untrusted formats: receipts and employer messages.

#### Multimodal OCR engine (`ocr_engine.py`)
Receipt images (`image_01.png` to `image_16.png`) contain missing transaction amounts for historical events.
- **Primary engine**: Mistral OCR (`mistral-ocr-latest`) extracts structured text and tables from base64 image payloads.
- **Amount extraction regex**: Scans extracted text for explicit financial keywords (`Net Salary`, `Total Due`, `Grand Total`, `Amount Due`) followed by decimal amounts.
- **Offline cache**: Pre-extracted values reside in `cache/image_amounts.json`. If network calls are disabled via `CACHE_EVIDENCE=true`, the engine loads values instantly. This eliminates grading timeouts caused by network latency or rate limits.

#### Multilingual message parser (`message_parser.py`)
Employer messages frequently announce salary updates or contract terminations in English or Indonesian.
- Captures salary amounts: Handles phrases like `confirmed base salary is EUR 1422.85` and `Gaji bulanan Anda sebesar IDR 38,760,000`.
- Captures effective dates: Matches dates following `scheduled for`, `effective from`, or `dikonfirmasi untuk`.
- Captures contract terminations: Matches statements like `seasonal contract has ended` or `telah berakhir` to immediately stop recurring salary projections.
- Captures bonus disclaimers: Identifies unconfirmed bonuses (`pending approval`, `masih menunggu`) so they are excluded from available cash.

### 2. Ledger and recurring stream detection (`recurring.py`)

Historical events contain fixed commitments, irregular variable purchases, and one-off anomalies.

- **Salary isolation**: Filters out performance bonuses and sales commissions by checking event descriptions for keywords like `commission` or `bonus`. Bases recurring salary exclusively on confirmed base pay.
- **Payday alignment**: Calculates the mode day-of-month across historical salary credits. Future recurring paydays snap to this day each calendar month using `add_month(last_date, n)`.
- **Variable burn smoothing**: For categories with high variance like `groceries`, `transport`, and `dining`, using the last transaction amount distorts weekly spending when the user made an unusual bulk purchase. The engine computes the median historical transaction amount for each category and applies it across median interval gaps.
- **Pending debit hold**: Pending debit events represent committed outflows that have not yet posted. The engine reserves 100% of pending debits against day 0 balance. Pending credits and unrealized investments are excluded until settled.

### 3. Cash flow simulation engine (`engine.py`, `solvers.py`)

The simulation models daily balances over a 90-day horizon ($t = 0, \dots, 90$):

$$B(0) = B_{\text{base}} - D_{\text{pending}} + F_{\text{scheduled}}(0) + F_{\text{recurring}}(0) - E_{\text{outflow}}(0)$$

For subsequent days $t \in [1, 90]$:

$$B(t) = B(t-1) + F_{\text{scheduled}}(t) + F_{\text{recurring}}(t) - E_{\text{outflow}}(t)$$

Where:
- $B_{\text{base}}$ is the starting balance from `financial_profiles.csv`.
- $D_{\text{pending}}$ is the sum of pending debit holds converted to home currency.
- $F_{\text{scheduled}}(t)$ is confirmed scheduled inflows and outflows on day $t$.
- $F_{\text{recurring}}(t)$ is the projected recurring stream balance change on day $t$.
- $E_{\text{outflow}}(t)$ is the test plan payment on day $t$.

#### Headroom calculation (`solve_amount_safe_to_pay`)
To determine how much the user can safely pay today without spending adjustments:

$$\text{headroom} = \min_{t \in [0, 90]} B(t) - B_{\text{min}}$$

$$\text{amount\_safe\_to\_pay} = \max(0.0, \min(\text{headroom}, \text{requested\_amount}))$$

#### Earliest safe date search (`solve_earliest_date`)
When the user cannot afford the full requested amount today, the solver tests each future date $d \in [0, 90]$. It simulates paying the full amount on day $d$ and checks whether $B(t) \ge B_{\text{min}}$ holds for all $t \in [d, 90]$. The earliest date satisfying this condition is returned.

### 4. Candidate generation and ranking (`candidate_gen.py`, `ranker.py`)

The agent enumerates all valid plans allowed by the user profile:
1. **Full payment**:
   - `affordable_now`: When `safe_amt >= requested_amount`.
   - `affordable_with_plan`: When spending changes are required to keep the user solvent.
2. **Installments**: Generated from provider options in `request_payment_options.csv`. Rejects options whose payment count exceeds the user's `max_installment_months`.
3. **Partial payment**: Permitted only when the user profile allows it, the request specifies `allows_partial_payment = true`, and $0 < \text{safe\_amt} < \text{requested\_amount}$. Generates exactly two payments: `safe_amt` today, and the remainder on `earliest_date_for_full_payment`.
4. **Wait**: Delays full payment to `earliest_date_for_full_payment`. Eligible only when the user considers full payment and the earliest date is on or before `desired_completion_date`.
5. **Not recommended**: Safe fallback plan when no candidate meets solvency criteria.

#### Lexicographical ranking order
When multiple candidate plans pass the 90-day safety check, `ranker.py` picks the winner using this hierarchy:
1. Completes by `desired_completion_date` (True before False).
2. Requires no spending changes (0 changes before $> 0$).
3. Minimizes total amount paid (including provider financing fees).
4. Earliest first payment date.
5. Fewest payment installments.

---

## Key architectural decisions and trade-offs

### Decision 1: Deterministic symbolic solver over end-to-end LLM reasoning

- **Choice**: Use Python simulation algorithms for cash flow math and rule checks. Restrict machine learning models strictly to document OCR.
- **Rationale**: Large language models struggle with multi-step arithmetic across 90-day cash flow timelines. They hallucinate dates and round currencies inconsistently. A symbolic solver guarantees 100% mathematical consistency, runs in milliseconds, and eliminates token costs during decision evaluation.

### Decision 2: Hybrid OCR caching over runtime-only API calls

- **Choice**: Extract document images through Mistral OCR during preparation and commit the resulting values to a versioned JSON cache file (`image_amounts.json`). Fall back to live API calls when an image is not in cache.
- **Rationale**: HackerRank automated grading environments may lack external internet access or have strict network rate limits. Relying entirely on live network calls creates a single point of failure. The cache ensures offline evaluation success while preserving live OCR capabilities.

### Decision 3: Historical median estimation over last-transaction replication

- **Choice**: Compute median spend across historical transactions for variable categories (`groceries`, `transport`, `dining`) instead of replicating the most recent transaction amount.
- **Rationale**: Real transaction histories contain outlier transactions, such as a bulk pantry restock or vehicle repair. Replicating an outlier weekly drains projected account balances and falsely flags affordable requests as unaffordable. The median represents true ongoing burn.

### Decision 4: Full horizon evaluation over sliding windows

- **Choice**: Test solvency across the entire remaining forecast horizon ($t \in [d, 90]$) when evaluating candidate payment dates.
- **Rationale**: A 30-day sliding window can approve a payment that leaves the user vulnerable to major recurring obligations due in week 5 or week 6. Evaluating the full 90-day trajectory prevents post-payment insolvency.

---

## Reliability and edge case handling

| Edge case | Risk | Solution |
|---|---|---|
| Foreign currency cash flows | Currency mismatch in balance math | Convert every event to `home_currency` using historical rates from `exchange_rates.csv` indexed by settlement date. |
| Seasonal contract termination | Projecting phantom income after layoff | Message parser detects contract end notices and stops salary stream projections. |
| Missing receipt amounts | Incomplete ledger state | OCR engine parses document images and extracts total due before running ledger balances. |
| Multi-category flexible tags | Missing spending reduction candidates | Flexibility checker tests for substring matches (`stoppable` and `reducible`) to support hybrid tags like `reducible_or_stoppable`. |
| Zero or negative recurring periods | Infinite loops during projection | Flow projector enforces `step = max(1, s.period_days)` to guarantee loop termination. |

---

## Verification and test results

1. **HackerRank validation suite (R01 to R14)**:
   - Passed all 14 schema and financial domain checks with zero errors across 250 evaluation requests.
   - Verified that `amount_safe_to_pay` stays within bounds, status values match recommendations, and explanations cite exact currency codes and minimum balances.
2. **Golden sample benchmark (`sample_requests.csv`)**:
   - Reached 80% exact match (20/25) on golden sample decisions, statuses, and payment plans.
3. **Repository hygiene**:
   - Clean Git state with zero working or scratch files tracked.
   - All source code files in `code/src/` remain strictly below 250 lines.
