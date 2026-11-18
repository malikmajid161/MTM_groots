# Mind to Machine — Three-Agent Delivery Board

Build baseline: `implementationplan_v6.md`, subject to the corrections below. This file is the execution/task breakdown. Exactly **three coding agents total**: Ismail, Abdullah, Majid, one per teammate. Do not launch additional agents. This board assigns work; it does not start implementation.

## Baseline decisions before implementation

Keep v6's compact claims, closed entity/key enums, Python-derived families for canonical keys, `committed_cost`, `engagement_rule`, source ledger, tiny authorization gate and stale-date regression tests. Resolve the following before coding; these corrections override conflicting v6 passages:

1. **Sessions:** no state means initialize; existing state means update, even for multiple records or forwarded text. Record count never resets state. Adopt a different convention only after help-desk confirmation, before freeze.
2. **Wrong messages:** distinguish external facts from unauthorized reported actions. A supplier claiming an approved order was reduced does not authorize that reduction. Reject the amendment, retain the required order, expose a fulfillment concern; never claim supplier fulfillment was verified. Genuine external capacity/availability changes are accepted and replanned.
3. **Schema:** compact output must still preserve hard/soft modality, operators, currencies, price scope, effective periods, entity references and correction targets. Use explicit typed relationship payloads, not unspecified operands. Add `reported_action` to kinds. Missing essentials become UNKNOWN.
4. **Planning:** enumerate permitted joint choices and validate actual judge/time assignments. Greedy venue/judge/meal repair is exploration order only. The shared-window judge formula is an estimate under its assumptions; handle zero capacity and stated panel/space constraints explicitly.
5. **Proof:** model calls interpret language into supported structures; model assurance alone cannot produce PASS. Unsupported predicates/missing data/incomplete search yield UNVERIFIED. INFEASIBLE requires complete supported search. Persist accepted external facts even if no feasible plan exists; retain last-valid snapshot separately.
6. **Limits:** one monotonic deadline and shared call counter cover extraction, repair, interpretation and every provider retry attempt. Disable hidden retries; reserve time for saving/reporting. Initial <120 seconds; updates <60 seconds and at most five attempts. Trace actual attempts and provider-reported usage, including errors and unavailable usage honestly.
7. **Evidence:** produce cumulative `runtime/submission.txt` containing current plan/status, decisions, full trace, usage totals and prediction comparison. Verify HEAD equals submitted hash and upload evidence after final testing. Preserve submitted evidence before any later runtime reset.
8. **Dates and identity:** retain v6's same-key stale-date gate for comparable claims with trustworthy dates. Distinguish message date from effective date; an authorized retrospective correction requires explicit review, not unconditional rejection. Actor scopes require provenance/trusted pack context, not a self-asserted role. Unknown authority remains unresolved.

## Owners and file boundaries

| Agent | Responsibility | Owned files |
|---|---|---|
| Ismail | Input, extraction, provider access, call limits and raw trace | `extract.py`, `model_io.py`, `tests/test_extract.py`, `tests/test_model_io.py`, `requirements.txt`, `.env.example` |
| Abdullah | Ledger, authority/conflicts, planning, constraints and update semantics | `plan.py`, `state.py`, `tests/test_plan.py`, `tests/test_state.py` |
| Majid | Integration, CLI, reports, acceptance suite and release | `main.py`, `report.py`, `contracts.py`, `tests/test_integration.py`, `tests/test_report.py`, `tests/fixtures/`, `.gitignore`, `README.md`, this board |

All three agents write and run their own tests. Majid owns integration, not everyone's testing. Request changes to another owner's files through a handoff; avoid concurrent edits. Majid alone edits shared contracts/dependencies after agreement (Ismail supplies dependency requirements). Each owner can propose contract patches; publish a tested contract commit before dependent work.

## Iteration and Git protocol

- Use three isolated clones or worktrees, never concurrent branch switches in one checkout. Branches: `codex/ismail`, `codex/abdullah`, `codex/majid`. Use the repository's actual integration branch; record its name during setup rather than assuming `main` exists.
- Majid integrates. Every iteration ends with a small tested commit from **each** owner, not one final commit at the end of the day. Commit messages: `[I1][ismail] extraction slice`, etc.
- Before committing: review diff; run owned tests; stage explicit source/test paths. Never stage `.env`, credentials or generated `runtime/` evidence. Do not fake test success or usage.
- Push the task branch when a remote is configured. Send the commit hash immediately with changed interfaces, test command/result, actual usage (or unavailable/no provider calls), and any remaining blocker. Without a remote, exchange a locally accessible commit; do not claim it was pushed.
- Majid merges one dependency-ready commit at a time, resolves conflicts with its owner, runs the affected contract/integration tests, and publishes the integrated HEAD. Do not both merge and cherry-pick the same change.
- Before starting the next dependent task, each agent fetches and merges the published integrated HEAD into their own branch and reruns affected tests. Do not assume another agent's uncommitted files are available. Independent work can proceed against agreed contracts meanwhile.
- A failing gate stays open: owner fixes it and publishes a new commit before dependent work is accepted. Report blockers immediately; do not wait for the next checkpoint.
- Board states: `TODO -> IN PROGRESS -> REVIEW -> DONE`, or `BLOCKED` with dependency/reason. Start with all tasks TODO. DONE requires tests, commit hash, and integration acceptance. Majid updates the board at checkpoints without inventing progress.
- Each iteration: two-minute planning, parallel implementation, tested commit handoff, integrated demo, brief adjustment of remaining scope. Cut polish before correctness, trace or rejection checks.

## Shared contract gate — I0, 10:00–10:10

| ID / owner | Task | Acceptance and tests | Dependency |
|---|---|---|---|
| I0-M / Majid | Initialize scaffolding, ignore rules, README command, contract types and test harness. Record integration branch. | Imports work; `.env` and runtime ignored; contract round-trip test; no pack facts embedded. Commit contract baseline first. | None |
| I0-I / Ismail | Verify credentials, approved model list, SDK timeout/retry behavior and English/Roman Urdu access. Propose extraction/provider signatures. | One real smoke call with exact provider usage/latency and honest errors; credentials never committed. Commit access adapter/config example and tests. | Contract agreement |
| I0-A / Abdullah | Define ledger, plan/status, decisions, constraint payloads and canonical semantic mapping with Majid. | Synthetic normalized records cover core keys, committed cost and engagement; invalid required fields become UNKNOWN. Commit planner/state skeleton and tests. | Contract agreement |

Majid publishes contracts before I1. Put actual types in `contracts.py`; use compact wire names from v6 and readable internal types as desired. Minimum interfaces to agree:

- `load_input(path) -> InputBatch`: original text and provenance; uncertainty retained, no destructive session inference.
- `extract(batch, context, budget, recorder) -> Extraction`: no direct state mutation; normalized claims, constraints, ambiguities and irrelevant IDs.
- `apply_update(state, extraction) -> UpdateResult`: new ledger/current plan, last-valid snapshot, decisions and affected areas; no provider calls hidden inside planning.
- `render(result, cumulative_trace, prediction)`: terminal + local artifacts; raw call recorder owned by Ismail, presentation owned by Majid.
- Single shared `RunBudget` and trace record contract: monotonic deadline, attempts, exact model/tag/input/output/usage/error. Provider fixtures are explicitly mocks; real smoke calls are separate.
- Stable source/entity/claim IDs across files: keep original source-local labels, reconcile against the ledger only with evidence; ambiguous matches never silently merge resources. All quantities retain units/scope.
- Constraints carry source, modality and typed payload: time relationships reference both activities; count bounds reference population; availability references resource/time basis; caps reference category/currency; uplifts reference base/rate/target/rounding; extras reference item/quantity/price basis/commitment. Corrections target claim IDs or scoped entity/key/effective period.

**I0 gate:** all agents can explain interfaces; contract baseline integrated; help-desk questions assigned to teammates. Unanswered rules remain visible assumptions, not fabricated answers.

## I1 — Working vertical slice, 10:10–11:15

| ID / owner | Deliverable | Required tests | Depends on |
|---|---|---|---|
| I1-I / Ismail | Verbatim input handling, one batched extraction, enum normalization, raw call recording. Empty/duplicate prechecks; invalid enums UNKNOWN without automatic repair. | English/Roman Urdu; mixed greeting and requirement; malformed JSON; unknown enums; raw provenance; provider usage missing/present; duplicate zero calls. | I0 contract |
| I1-A / Abdullah | Five-area candidate planner: headcounts, permitted engagement, committed expenses counted once, basic schedule and explicit judge assignments. Initial state plus basic correction update. | Independent arithmetic assertions; cost replacement without duplication; capacity/food bounds; judge coverage/time; complete five-area output. | I0 contract; normalized fixtures allow work before extractor finishes |
| I1-M / Majid | Wire `python main.py <file>`; minimal terminal output and persisted state/plan/trace. Own original synthetic pack and correction file. | CLI subprocess cold run plus one update; input file unchanged; saved state reused; terminal shows numbered real calls and totals; mocked integration is marked as mocked. | I0; integrate I1-I and I1-A as available |

**11:15 demo:** initial pack and one update run through the real entry point. Run one live provider integration when access works; report actual wall time and usage. Commit/push each slice and publish integrated HEAD. Incomplete constraints must display UNKNOWN, never PASS.

## I2 — Safe updates and constraint completion, 11:15–12:00

| ID / owner | Deliverable | Required tests | Depends on |
|---|---|---|---|
| I2-I / Ismail | Compact typed relationship extraction; reported actions; scoped correction references; minimal update context; enforced call/time budget. | Percentage base/rate/rounding; activity relation operands; price scope; reported action vs external fact; injected instructions treated as data; slow calls/retries stay within budget. | Integrated I1 + frozen payload contract |
| I2-A / Abdullah | Authorization/stale-date gates, decision ledger, accepted-fact persistence, proposal rollback, six constraint families and joint choice search. | Cross-area directives; unknown authority; non-binding proposals; older/equal/missing dates; retrospective correction review; supplier order amendment rejected; external capacity reduction retained; heterogeneous judge slots; joint-search counterexample; unsupported/incomplete search UNVERIFIED. | Integrated I1; typed fixtures, then I2-I |
| I2-M / Majid | Multi-record/multiline update integration, revision-safe persistence, failures visible without corrupting ledger, regression harness. | Forward/quote does not reset session; prior trace retained; failures preserve usable saved state; accepted infeasible fact persists; report distinguishes last-valid snapshot from current status. | Integrated I1; integrate I2-I/I2-A |

**12:00 demo:** initial run followed by price correction, unauthorized order amendment and credible external fact change. All owners commit tested increments. If time is short, retain tiny authority/stale-date checks and supported constraints; expose gaps instead of implying completion.

## I3 — Reviewable output and full rehearsal, 12:00–13:00

| ID / owner | Deliverable | Required tests | Depends on |
|---|---|---|---|
| I3-I / Ismail | Audit real provider attempts, latency, exact model/tags and nullable usage; review Abdullah's source-to-claim seam. | Real smoke run reports exact usage; timeout/error attempts recorded; no hidden retries or fake Python calls; shared five-attempt limit enforced. | Integrated I2 |
| I3-A / Abdullah | Boundary/feasibility hardening; review Majid's displayed plan against actual ledger/constraints. | Mandatory features vs unknown features; required meal tier; zero judge capacity; panels/parallel spaces when specified; category cap/uplift/extra checks; no stale snapshot presented as current valid plan. | Integrated I2 |
| I3-M / Majid | Self-contained offline HTML, escaped untrusted content, cumulative submission artifact, predicted-vs-actual call tags and full timed rehearsal. | Offline report opens; raw message HTML injection escaped; plan/rejections/trace readable; submission includes every run; initial <120s, three updates each <60s and ≤5 attempts; Git remains clean after runs. | Integrated I2; I3-I/I3-A fixes |

**12:30–13:00 rehearsal:** Majid runs exact judging command with a fresh original synthetic pack and three one-at-a-time updates (two changes, one plausible wrong message). Record prediction before the chosen update. Ismail audits calls/usage; Abdullah audits plan constraints and rejection reasons. Rotate explanations so every teammate can explain all modules. Each agent commits its tested fixes; Majid publishes rehearsal result and integrated HEAD.

## I4 — Stabilize and freeze, 13:00–13:25

- **13:00–13:15:** only high-impact fixes. Ismail owns extraction/provider failures; Abdullah owns invalid planning/update behavior; Majid owns CLI/report/integration failures. Every fix has a regression test, tested commit and integrated verification. No feature expansion.
- **13:15–13:25:** Majid runs final relevant suite and verifies clean Git/HEAD; all owners stop editing once final hash is selected. Push and submit repo URL/hash before 13:25; confirm organizer access for private repo. No edits after freeze.
- **Before official unseen test:** remove only disposable runtime, preserve any required evidence, confirm clean `git status --porcelain` and exact `git log -1 --format=%H` match. Maintain state across subsequent update files.
- **After official final update:** verify final plan and cumulative trace, upload `runtime/submission.txt` through organizer form, preserve submitted evidence. Do not change source after freeze.

## Handoff template — required after every agent increment

```text
Task / owner / status:
Branch / commit hash / pushed or local-only:
Changed files and interface changes:
Tests: exact command, pass/fail summary (mock/live distinguished):
Real provider usage and timing, or unavailable/no provider calls:
Depends on integrated HEAD:
Remaining issues / next consumer:
```

## Agent start instructions

**Ismail:** Read this board and v6 with these overrides. Own extraction/provider boundaries, write and run your tests each iteration, and hand off tested commits to Majid immediately. Publish contract needs before dependent work. Never silently change another owner's interface or fabricate tokens.

**Abdullah:** Read this board and v6 with these overrides. Own planning/ledger/updates, work from synthetic normalized fixtures while extraction develops, and prove outcomes through your own tests. Commit and hand off each iteration. Never hide accepted external facts, approve unauthorized amendments or claim unsupported constraints pass.

**Majid:** Read this board and v6 with these overrides. Own shared contracts, CLI/reporting, board and integration; write and run your own tests as well as integration gates. Merge tested increments promptly and publish HEAD so both other agents can continue. Do not mark a task DONE before its acceptance evidence and integration pass. Own release evidence and upload checklist.

## Live board (update at each checkpoint)

| Iteration | Ismail | Abdullah | Majid | Integrated HEAD / demo evidence |
|---|---|---|---|---|
| I0 | TODO | TODO | REVIEW | Proposed integration contracts pushed as `e0effec`; teammate agreement and integration pending. |
| I1 | TODO | TODO | REVIEW | CLI and cumulative reporting pushed as `72c8045`; mocked CLI tests pass. |
| I2 | TODO | TODO | REVIEW | State preservation and prediction tracking pushed as `c97bd1e`; live adapter integration pending. |
| I3 | REVIEW | REVIEW | REVIEW | Integrated branch passed the four-run production CLI rehearsal against a local mock HTTP provider at `bb313c2`. Live provider and unsupported constraint checks remain open. |
| I4 | REVIEW | REVIEW | REVIEW | `a9e8dec` passes 42 tests, including typed updates and a failed HTTP attempt through the production CLI with mock provider responses. |

No work or tests are marked complete by creating this task breakdown. Clock times are the brief's build window; if starting later, preserve the 13:25 freeze and shorten scope explicitly rather than shifting the deadline.

### Remaining judging checks

- Ismail: run a real provider smoke test with English and Roman Urdu, verify exact model IDs and reported usage, and hand off the supported model configuration.
- Abdullah: demonstrate a complete plan from aggregate judge data and relative event timing. The current fixed-grid planner expects identified judges and an explicitly timed judging activity. Verify mixed hard constraints and report any unsupported cases.
- Majid: repeat the judging rehearsal with both changes integrated and a real provider configured. Verify artifacts, call counts, wall times, clean Git, and the candidate submission hash.
