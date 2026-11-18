# MTM Groots

A message-driven hackathon planner. The organizer brief defines the judging requirements. The delivery board overrides conflicting parts of implementation plan v6.

## Run

Use Python 3.10 or later. Export `MODEL_ENDPOINT`, `MODEL_NAME`, and `MODEL_API_KEY` as shown in `.env.example`. Supply `MODEL_APPROVED_MODELS` if using the organizer's allowlist.

```text
python main.py path/to/messages.txt
```

Use the same command for the initial pack and every update. An existing session receives an update regardless of message count. Archive any submission evidence before moving the generated runtime directory aside to start a new session.

## Integration

The integration branch is `main`. Majid works on `codex/majid`. The extractor calls `budget.reserve_attempt()` immediately before each provider request and records every attempt, including errors, with the recorder. Use the remaining budget for the provider timeout. The planner receives a JSON-compatible ledger and the current extraction. Keep source references stable and preserve accepted facts even when a current plan cannot be verified.

`runtime/session.json` holds the committed session. `runtime/submission.txt` and `runtime/report.html` are regenerated from it. The local HTTP rehearsal runs the production CLI and planner with deterministic provider responses. Use a real configured provider for wording accuracy, latency and provider usage verification.

Run the local suite with `python -m unittest discover -s tests`.

For a prediction comparison, record the expected tags on the judging slip first. Optionally put the same whitespace-separated tags in `runtime/predicted_tags.txt` before the update. The report records the expected and actual tags and consumes the file.

The reader uses explicit message headers when present. A header date with a timezone can order comparable claims in the pack. A sender name in a text file does not verify authority. The planner leaves directives with unverifiable authority unresolved.

## Judging handoff

From the integrated checkout, confirm that `git status --porcelain` is empty and record the exact candidate with `git rev-parse HEAD`. Confirm that it matches the commit hash on GitHub before submitting the repo URL and hash. Move any practice `runtime/` directory aside after preserving its evidence.

Run the judging pack and each subsequent message file through the same CLI command. Keep `runtime/` in place between updates. Record the prediction before the designated update. Verify the current plan or its explicit status, the rejection reason, numbered model attempts, and provider-reported token totals.

After the last update, upload `runtime/submission.txt` and preserve a copy. Open `runtime/report.html` for the judges. Use Ismail's provider test evidence and Abdullah's planner acceptance results when deciding whether the integrated commit is ready.
