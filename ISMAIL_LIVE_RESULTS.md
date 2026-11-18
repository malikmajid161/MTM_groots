# Ismail live-provider verification — 18 November 2026

## Selected candidate and limits of the result

Gemini `gemini-3.5-flash-lite` via Google's chat-completions-compatible endpoint is the current tested candidate. Google lists free input/output for this model on the free tier; account/project billing and quota settings still govern actual access. No billing upgrade or paid-model fallback was enabled by this work. Organizer small-model eligibility is NOT verified.

The original workspace `.env` selects this model, strict extraction, temperature 0 and max_tokens 8192. The configured Gemini key remains local and ignored by Git; previous NVIDIA/Groq keys were preserved. `.env` is not auto-loaded: use `set -a`, `source .env`, `set +a` before the CLI. The key named GEMINI_API or GEMINI_API_KEY was mapped to the generic MODEL_API_KEY locally, without printing it.

## Live supported-case rehearsal

The input was an original synthetic workshop pack plus three updates. It is narrower than the full unseen-task contract: all core resources, named judges, pricing and times are explicit. The broader scenario, which includes additional delivery/panel wording, has NOT passed verification.

| Step | End-to-end seconds observed | Real calls | Provider total tokens | Observed outcome |
|---|---:|---:|---:|---|
| Initial pack | 4.49 | 1 | 3307 | VALID; independently checked all-in total 377 |
| Roman Urdu expense correction | 2.48 | 1 | 3539 | VALID; corrected total 381, old expense replaced |
| Unauthorized completed order reduction | 2.95 | 1 | 3586 | Rejected; required meal quantity 27 retained; current status UNVERIFIED due fulfillment review |
| External venue capacity change | 4.88 | 1 | 3720 | Capacity updated to 25; total 381 and meal quantity 27 retained; fulfillment concern remains |

Total reported tokens for this four-step sequence: **14152**. This is not the total across every exploratory provider probe. Each run used the same production CLI command with its input file; the harness supplied exported environment settings and paced inputs outside timed CLI runs. Runtime trace and raw responses remain local at `/tmp/ismail-live/gemini-corrected/runtime/`. The source `.txt` files are in its parent directory. No prediction was recorded retroactively; the prediction-slip rehearsal remains pending.

Independent checks were compared against the synthetic input, not just the planner's VALID label. A prior Groq 20B run was internally labeled VALID with an incorrect fixed meal cost; it is explicitly NOT counted as a pass.

## Fixes driven by real responses

- Added validated request options, explicit non-streaming responses and detection of truncated/filtered completions. No automatic retries or unreported model switches.
- Added generic schema requests and optional strict transport mode (`MODEL_STRICT_EXTRACTION=1`) for compatible models. Local validation remains authoritative; JSON shape does not prove semantic accuracy.
- Short source and claim aliases reduce token cost and prevent models shortening full content hashes with ellipses. Restore full references locally, including correction metadata; never mutate caller context or reuse stale schema aliases.
- Decode optional strict metadata safely; empty metadata means none. Metadata cannot overwrite core fields or source IDs.
- Restrict operators; absolute corrected totals must replace, not use +=. A committed expense is a fixed total and does not require an independently invented price basis.
- Clarified resource grouping, price basis, already-committed expense vs honorarium, reported actions vs external facts, and read-only update context.
- Added an honest application User-Agent and JSON Accept header; Groq rejected the default urllib request with HTTP 403/1010 before this fix.

## Exploratory failures retained as failures

- NVIDIA Lightning: simple Roman Urdu probe succeeded in 3.36s with 418 reported tokens; default full-pack request timed out around 115s. Non-thinking and bounded-thinking experiments returned unsupported/missing semantics. No complete NVIDIA sequence passed correctness.
- Groq 20B and 120B: fast responses, but some probes omitted facts or misclassified price scope/actions. Free account returned an 8000 TPM quota rejection. Some schema generations failed/truncated. A 120B initial supported case passed arithmetic once; later updates exposed correction-reference and context-repetition bugs fixed here. No complete Groq sequence is certified.
- Gemini's broader original pack returned HTTP 503. It was not treated as a valid plan or retried invisibly.

## Remaining owner handoffs

**Abdullah:** a rejected reported action adds a persistent fulfillment issue and makes current status UNVERIFIED even after a later valid factual change. Reconcile this with the brief's requirement that rejecting the wrong message keeps the plan valid; retain the planning requirement and make fulfillment concerns explicit without falsely claiming confirmed delivery. Unresolved review issues also have no demonstrated resolution path. Do not mark wrong-message scoring complete from the rejection alone.

**Majid:** rerun the exact CLI/release suite after integration, inspect offline report and cumulative trace, rehearse a prediction BEFORE a designated update, and verify the final submitted hash. These live cases do not establish that every unseen constraint is implemented.

**Ismail:** broader wording/constraint coverage and repeated-run accuracy remain unverified. The successful Gemini sequence is evidence for this supported case, not a general correctness guarantee. Model-list approval and quota availability at judging remain external prerequisites.

## Integrated backend checkpoint (supersedes the owner handoffs above)

Majid's remaining integration commits through `05e2bd9` are merged. The user authorized Ismail to complete backend work and subsequently assigned UI work to Abdullah. The integrated suite now passes **61 tests**.

The broader original-wording Cedar pack completed all four production CLI runs at `/tmp/ismail-live/integrated-full/`:

| Run | Wall seconds | Calls | Reported tokens | Independent outcome |
|---|---:|---:|---:|---|
| Initial | 7.37 | 1 | 4655 | VALID; total 377, order 27 |
| Roman Urdu correction | 2.34 | 1 | 3659 | VALID; replacement total 381 |
| Unauthorized reduction | 2.15 | 1 | 3660 | Rejected; approved order 27 and valid plan retained |
| Venue capacity change | 4.35 | 1 | 3790 | VALID; capacity 25, total 381 |

Total reported tokens: 15764. A prediction file was written before the first update, but used invalid tag `general`. The report correctly recorded a prediction error; prediction acceptance is **not** marked complete.

New aggregate-judge, parallel, duration-only pack at `/tmp/ismail-live/aggregate-audited/` passed in **10.72 seconds**, two calls, **3805 + 4417 = 8222** reported tokens. Independently checked: 44 students / teams of 4 = 11 teams; cap 2 requires 6 engaged judges; attendance and meals = 44 + 3 + 6 = 53; cost = venue 70 + food 53*4 + judges 6*13 + printing 21 = 381. Schedule explicitly includes the 9-minute break within the 75-minute duration and parallel assignments.

Earlier aggregate probes are retained as failures: one omitted a duplicate aggregate event judge count (now derived from the explicit pool quantity), one omitted the break and emitted a zero vendor commitment, and another mislabeled the venue price as committed cost. Those runs do not count as passes. The configured optional extraction review now compares the draft with the original messages and returns a complete corrected extraction. Both calls, raw responses and usage are recorded; this remains language interpretation, not independent proof of every unseen requirement.

`MODEL_VERIFY_EXTRACTION=1` is enabled in the local .env and documented in .env.example. Full four-run verification with this option is still pending. No paid fallback was enabled. Organizer model eligibility and official submission remain external checks.

## User-requested stop checkpoint

Further fixes were stopped at the user's request. The committed checkpoint passes 70 automated tests. The easy bundle passed live at 16.72s initial and 5.25s update, with expected totals 189000 and 191000. Medium response replay through the fixed backend matched 333600 and 360600; this is offline regression evidence, not a fresh live pass. Fresh medium attempts returned provider HTTP 503 high-demand errors. Hard attempts remain unverified and are not accepted as correct; some earlier candidates also counted a duplicate old quotation. Captured responses and all failed runs remain under /tmp/ismail-live/judge-fixed-v1 through judge-fixed-v6. No claims of full bundle acceptance or official submission are made.
