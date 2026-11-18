# MTM Groots

A message-driven hackathon planner. The organizer brief defines the judging requirements. The delivery board overrides conflicting parts of implementation plan v6.

## Run

Use Python 3.10 or later. Configure model access as documented by the provider adapter.

```text
python main.py path/to/messages.txt
```

Use the same command for the initial pack and every update. An existing session receives an update regardless of message count. Archive any submission evidence before moving the generated runtime directory aside to start a new session.

## Integration

The integration branch is `main`. Majid works on `codex/majid`. The extractor calls `budget.reserve_attempt()` immediately before each provider request and records every attempt, including errors, with the recorder. Use the remaining budget for the provider timeout. The planner receives a JSON-compatible ledger and the current extraction. Keep source references stable and preserve accepted facts even when a current plan cannot be verified.

`runtime/session.json` holds the committed session. `runtime/submission.txt` and `runtime/report.html` are regenerated from it. Provider calls use the CLI's actual adapters once both teammate modules are available.

Run the local suite with `python -m unittest discover -s tests`.

For a prediction comparison, record the expected tags on the judging slip first. Optionally put the same whitespace-separated tags in `runtime/predicted_tags.txt` before the update. The report records the expected and actual tags and consumes the file.
