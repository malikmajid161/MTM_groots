# MTM Groots

A message-driven event planner for venue, schedule, food, judging and budget decisions. It reads English and Roman Urdu messages, extracts structured evidence with an LLM, and uses Python to calculate and validate a plan. New message files update the existing session while preserving sources, decisions and model traces.

## Setup

Use Python 3.10 or later. The backend uses the Python standard library.

```bash
cp .env.example .env
```

Fill in `MODEL_ENDPOINT`, `MODEL_NAME` and `MODEL_API_KEY`. Keep `.env` local; never commit credentials. The application does **not** automatically load `.env`. In Bash, export its settings before running:

```bash
set -a
source .env
set +a
```

Quote JSON values in `.env`, for example:

```bash
MODEL_OPTIONS_JSON='{"temperature":0,"max_tokens":8192}'
```

| Setting | Purpose |
| --- | --- |
| `MODEL_ENDPOINT` | Full chat-completions-compatible HTTPS endpoint. Local HTTP endpoints are allowed for testing. |
| `MODEL_NAME` | Exact provider model ID. |
| `MODEL_API_KEY` | Key used for the configured endpoint. Provider-specific key names alone do not configure the client. |
| `MODEL_APPROVED_MODELS` | Optional comma-separated organizer allowlist of exact model IDs. |
| `MODEL_OPTIONS_JSON` | Optional supported provider request parameters. |
| `MODEL_STRICT_EXTRACTION` | Set to `1` for a provider supporting the strict extraction schema. |
| `MODEL_VERIFY_EXTRACTION` | Set to `1` to review the initial extraction with a second recorded LLM call. |

The tested Gemini configuration and alternative endpoint examples are in `.env.example`. Provider quota, availability and organizer model eligibility must be checked separately. The application does not silently switch models or retry failed requests.

## Minimal testing CLI

```bash
python cli.py
```

Paste the test `.txt` file path when prompted. The launcher loads `.env`, runs the planner, prints the readable plan and displays the saved `plan.txt` and `trace.txt` paths. Each invocation starts a fresh test in `runtime/tests/`, preserving prior evidence.

You can also pass the path directly:

```bash
python cli.py "/path/to/test file.txt"
```

For a follow-up message, reuse the result directory printed by the first run:

```bash
python cli.py update.txt --session "runtime/tests/<your-run-directory>"
```

## Input and execution

Supply a UTF-8 plain-text message file:

```bash
python main.py path/to/messages.txt
```

The same command handles an initial pack and subsequent updates:

```bash
python main.py path/to/initial_pack.txt
python main.py path/to/update.txt
```

Open `runtime/report.html` to review the plan, AI traces and updates in Abdullah’s dashboard. Its upload button loads saved `session.json` files.

Explicit `From:` headers separate messages. Dates can appear on a separate `Date:` header or inline as `From: sender | Date: timestamp`. Comparable dates help prevent older facts replacing newer ones. A sender's stated title does not authenticate authority.

CSV, structured JSON, PDF and ZIP are not supported as direct structured inputs. Extract message `.txt` files from a ZIP before running them. The expected-results document supplied with a test pack is for independent checking and must stay out of model input.

Keep `runtime/` in place between updates. Exact duplicate files are ignored without model calls. To start a separate scenario, preserve its evidence and move the existing `runtime/` directory aside first. Concurrent updates to the same session are blocked by a session lock.

## Minimal result page

After running the planner, generate an offline summary page:

```bash
python ui.py runtime/session.json
```

Open `runtime/result.html` in a browser. It shows the current status, five planning areas, blocking issues, latest decisions and links to the full trace. Failed runs clearly label any previous saved result. The page reads saved evidence only and makes no model calls. Regenerate it after subsequent runs to display the latest session.

## Processing and validation

1. Read the original messages and preserve source references.
2. Extract JSON claims and typed constraints with one model call.
3. When `MODEL_VERIFY_EXTRACTION=1`, make a second call to check omissions, resource identities and mappings against the messages.
4. Apply updates and calculate candidates in Python; planning itself makes no model calls.
5. Save the current result, separate last-valid snapshot, decisions and cumulative trace.

Normal configured runs use two LLM calls per file when extraction review is enabled. Empty or duplicate inputs use zero calls; failed runs may stop after one. Every attempt shares the run deadline and call budget. The CLI reserves 115 seconds for an initial run and 55 seconds for an update, leaving reporting headroom against the 120/60-second requirements. Updates allow at most five attempts. These limits do not guarantee provider availability.

The backend supports local clock times and explicitly dated times, duration-only schedules, judge pools and individual judges, parallel judging assignments, venue features and availability, meal tiers and preferences, dietary portions within a total meal order, shared delivery charges, committed bills and supported typed constraints. Solver-selected durations for included activities without stated durations are exposed separately in the schedule.

| Status | Meaning |
| --- | --- |
| `VALID` | The candidate passes the implemented checks for the accepted structured evidence. This does not prove the LLM extracted every source requirement correctly. |
| `INFEASIBLE` | No candidate satisfies the complete supported search and checks. |
| `UNVERIFIED` | Missing evidence, unsupported semantics, unresolved issues or an incomplete search prevent proof. This is not a successful planning result. |

Unauthorized reported amendments do not overwrite approved orders. Credible external facts, such as reduced venue capacity, are retained even when they invalidate the current plan. A last-valid snapshot is historical evidence, not confirmation that the current facts remain feasible.

## Generated evidence

| File | Contents |
| --- | --- |
| `runtime/session.json` | Current ledger/result, last-valid snapshot, sources and cumulative runs. |
| `runtime/plan.txt` | Readable current plan/status, issues and key message decisions. |
| `runtime/trace.txt` | Separate cumulative input evidence, model calls, errors, timing and reported usage. |
| `runtime/submission.txt` | Plain-text plan, decisions, full traces and reported usage. |
| `runtime/report.html` | Self-contained offline HTML report. |

Traces include numbered attempts, configured and returned model identifiers, inputs, outputs, errors and provider-reported token usage. Missing usage stays unknown; it is not fabricated. Failed provider attempts remain in the evidence.

For a prediction comparison, record expected call tags **before** an update. For the current extraction/review pipeline:

```bash
printf 'reading\n' > runtime/predicted_tags.txt
python main.py path/to/update.txt
```

The report compares the predicted and actual tag sets and consumes the prediction file. `reading` is the model-call tag; `general` is not a valid prediction tag. Record any required judging slip separately before execution.

## Tests and current acceptance status

```bash
python -m unittest discover -s tests
```

At the published backend checkpoint, **70 automated tests pass**. These include mocked provider/CLI tests, generic planner regressions and captured-response replay. They are distinct from live language-extraction acceptance.

| Supplied bundle | Verified result |
| --- | --- |
| Easy | Live initial and update passed; totals matched PKR 189,000 and PKR 191,000. |
| Medium | Captured Gemini response replay through the fixed backend matched PKR 333,600 and PKR 360,600, including the venue switch. Fresh live attempts encountered provider HTTP 503 errors. |
| Hard | Full live acceptance remains incomplete. Attempts exposed extraction, resource identity and constraint-mapping failures; they are not certified passes. |

See [ISMAIL_LIVE_RESULTS.md](ISMAIL_LIVE_RESULTS.md) for evidence and failed experiments. Further fixes were stopped at the user's request after publishing this checkpoint. Passing the automated suite does not establish that all unseen packs work.

## Modules and team handoff

| Module | Responsibility |
| --- | --- |
| `extract.py` | Verbatim inputs, source aliases, extraction schema and review. |
| `model_io.py` | Provider requests, bounded attempts and raw tracing. |
| `plan.py` | Normalization, candidate search, assignments and deterministic checks. |
| `state.py` | Update decisions, stale facts, corrections and last-valid state. |
| `main.py` | CLI, session persistence, locking and integration adapters. |
| `contracts.py` | Shared data contracts and run budget. |
| `report.py` | Plain-text and offline HTML evidence. |

`main` is the integration branch. Abdullah owns the UI work. The UI should use the `UpdateResult` contract and preserve the distinction between the current result, last-valid snapshot and failed run evidence. Food output may include component quantities and delivery; budget output includes a category breakdown.

The delivery board in [AGILE_TASKS.md](AGILE_TASKS.md) records task ownership and overrides conflicting implementation-plan assumptions.

## Submission handoff

Preserve practice evidence before starting the official session. Verify a clean checkout and record `git rev-parse HEAD`; confirm that hash matches the submitted remote commit. Keep the same runtime session through all official updates, record the prediction before its designated update, and inspect the final plan/status and cumulative trace. Submit the requested repository/hash and upload `runtime/submission.txt` through the organizer's form. Model eligibility, official upload and teammate explanation rehearsal are separate acceptance steps.

## Live dashboard

Run `python3 serve_ui.py` and open http://127.0.0.1:8000/. Choose **New session** to upload a UTF-8 messages TXT file. Progress shows processing stages and elapsed time; the resulting session renders automatically, including provider failures. Each upload saves its plan, trace and session under `runtime/ui/<session-id>/`. **Upload session** still opens previously saved JSON evidence. Refreshing starts with an empty dashboard; use **Upload session** to open saved evidence.
