# Synthetic judge-style test packs

These are ORIGINAL fictional messages for local testing, not organizer-issued packs or official answers. Do not paste any test-specific facts into source code, prompts, or validation rules.

## Files
- `m1_easy_pack.txt` then `m1_update.txt`: straightforward planning, ignore greeting, replace committed printing cost.
- `m2_medium_pack.txt` then `m2_update.txt`: hard generator requirement, break/activity, preferred food tier, Roman Urdu, venue capacity change requiring replanning.
- `m3_hard_pack.txt` then `m3_update.txt`: time/availability, vegetarian percentage, category cap, stale claim, unauthorized judge instruction, prompt injection, and changed supplier price.

## How to run
For each scenario, start with an empty generated runtime state, then run the pack followed by its matching update using the SAME command. Example:

```bash
python main.py m1_easy_pack.txt
python main.py m1_update.txt
```

Reset only generated state between scenarios (not between a pack and its update). If your implementation stores state in `runtime/`, remove that directory before starting the next scenario. The messages use `From:` headers and explicit dates to exercise parsing.

## Judge rubric
Compare your output against `JUDGE_EXPECTATIONS.md`. Treat it as a manual oracle, not a source for your extractor. Check complete numbered model traces, provider-reported tokens, accepted/rejected/ignored messages, unchanged state after rejected directives, and one-command behavior.

