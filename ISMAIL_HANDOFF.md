# Ismail implementation handoff

Branch: `codex/ismail`. Base: `1a3cd44` on integration branch `main`.
I0 provider commit: `681838f`. The following extraction commit completes this handoff.
Status: ready for review/integration; not marked DONE because shared-contract integration and live smoke verification remain outstanding.

## What is implemented

- `model_io.py`: standard-library chat-completions-compatible JSON HTTP adapter; configurable full endpoint/model/key. No automatic retries. Remote HTTPS required, localhost HTTP allowed. Optional exact model allowlist; list must come from organizers.
- `RunBudget(seconds=60, max_calls=5, reserve_seconds=3)`: create once per CLI invocation before input/extraction; pass the SAME object to every model operation. For initial run use seconds below 120 and an appropriate call cap. Time for downstream planning/reporting must fit remaining deadline; CLI owns checking that too.
- Provider request runs in a child process with parent wall timeout, so a trickling response cannot run indefinitely. Budget rejection before dispatch creates no fictitious trace call. Failed attempts are counted and traced. No retry or repair is hidden.
- `TraceRecorder(path)`: loads session's prior numbered JSONL records and appends new real attempts. Records configured and provider-reported model separately, full payload/raw response, nullable provider usage, timing/error type. `totals()` returns null for any token field with missing usage in any call; never estimates. `print_trace()` is available; CLI/report owner supplies decision/rejection printing too.
- `load_input(path)`: strict UTF-8/UTF-8-BOM handling, original line endings/text preserved, byte digest and source ID. Whole file is a provenance source; headers stay verbatim. No sender/date or record boundary guesses; no session resets.
- `extract(batch, context, budget, recorder, client=None)`: dictionary seam pending shared `contracts.py`. `context['seen_digests']` skips exact prior files with zero calls; caller persists only successfully processed digests, not failed attempts. Caller supplies minimal relevant ledger context and reconciles stable resource IDs using provenance. Provider/config failures propagate so CLI can save an honest unresolved report. Malformed extraction JSON returns UNRESOLVED without repair calls.
- Canonical claims preserve compact v6 names; Python planner derives family. Unknown enums, missing essential fields/currency/price basis and incomplete relationships become UNKNOWN. Typed payloads and reported actions/corrections retained. PENDING_VALIDATION is not PASS. Planner must validate payload types, reference resolution, arithmetic and authority.

## Integration instructions for Majid and Abdullah

1. Merge provider then extraction commits (or merge the branch once; do not also cherry-pick those changes).
2. Publish `contracts.py` and adapt dictionary seams with Ismail before declaring contract gate complete. No shared contract was present at implementation start; no other owner's files were changed.
3. Wire the single RunBudget/TraceRecorder into CLI; preserve recorder/state across update inputs. Never infer new session from record count.
4. Decide outcome per claim, not just per source: one source file can contain multiple messages and mixed valid/invalid claims. Original sender/date evidence remains in source text; normalized timestamps/identity need contract agreement before using them as trusted authorization/date evidence.
5. Current claimed-role data is NOT authenticated. An extracted reported_action must go through Abdullah's unauthorized-amendment rule.
6. Trace failed calls plus decisions, print all required fields/totals, and produce cumulative upload artifact. Do not let CLI silently swallow configuration/provider exceptions.
7. `.env.example` is a template only; environment variables must be exported. Nothing auto-loads `.env`. Do not commit secrets or runtime files. Ismail modules require no third-party packages.

## Verification

Command: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py' -v`
Result at handoff: 16 tests passed, all provider responses mocked; no actual provider calls and no actual provider token usage.
Coverage: trace reload/sequence/totals, missing usage, failures without retry, shared time/call cap, subprocess timeout plumbing, malformed provider response, allowlist/tag checks, verbatim multiline input, invalid encoding/empty files, compact schema normalization, unsupported fields, typed relationships, duplicate zero calls, malformed JSON without repair, Roman Urdu source preservation, mixed greeting, actions and correction metadata.
These mocks test adapter/normalizer behavior, NOT model extraction accuracy or live latency.

## Open checks

- MODEL_ENDPOINT, MODEL_NAME, MODEL_API_KEY, MODEL_APPROVED_MODELS were not configured. Organizer-approved list and real English/Roman Urdu smoke call remain unverified. No live performance/accuracy claim is made.
- No end-to-end planner/CLI exists in this worktree yet. Full run/update timing, final report and integration acceptance belong to later shared iterations.
- Tests and live runs must be reported separately. Do not call the whole project complete from this handoff.
