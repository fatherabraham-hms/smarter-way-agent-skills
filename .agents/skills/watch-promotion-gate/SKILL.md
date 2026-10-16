---
name: watch-promotion-gate
description: >-
  Watch a file-backed promotion gate from cron without consuming model or
  market-data tokens. Validate local evidence, persist the last state, and
  emit output only when the gate changes state.
disable-model-invocation: true
metadata:
  requires:
    bins: ["python3"]
---

# Watch a promotion gate

Use this skill when a repository already produces a file-backed promotion or
shadow-evidence report and needs a reusable cron check. The watcher is a local
read-only observer:

- It does not call an LLM, market-data provider, exchange, wallet, or gateway.
- It never enables trading, changes configuration, or resumes execution.
- It writes only its small transition state file and optional stdout.
- The producer remains responsible for creating genuine evidence. A watcher
  cannot turn ordinary scan output into a live shadow window.

## Command

```bash
python3 .agents/skills/watch-promotion-gate/scripts/watch_promotion_gate.py \
  --evidence /path/to/promotion-evidence.json \
  --state /path/to/promotion-watch-state.json \
  --transition-only \
  --json
```

The command exits zero for `ready`, `pending`, and `invalid` states so a cron
job can continue watching. With `--transition-only`, unchanged state produces
no stdout; a cron wrapper can send only transitions to its existing notifier.

## Default evidence contract

The default contract is intentionally narrow and suited to an asset-regime
shadow gate. A report is `ready` only when all are true:

- `gate.promotion_allowed` is `true`;
- `gate.operational_shadow_status` is `validated`;
- `operational_evidence.hourly_cycles.completed >= 24`;
- `operational_evidence.market_day_boundary.completed` is `true`;
- stock coverage names benchmark `SPY` and has observations;
- crypto coverage names benchmark `BTC` and has observations;
- queue safety is `validated` and independently verified.

Anything missing, malformed, or contradictory is `pending` or `invalid`, never
ready. The watcher does not infer success from a single boolean.

## Cron integration

Run it hourly after the cycle producer, using the host's existing cron wrapper
and notification path. Keep the state file outside the repository's source
tree, for example:

```cron
5 * * * * /path/to/cron-wrapper run promotion-gate-watch
```

The wrapper should pass the evidence and state paths and forward non-empty
stdout to the repository's established notifier. Do not add a second Telegram
poller or put credentials in the watcher.

## State and transitions

The state file stores the last status and evidence digest. A transition occurs
when status or evidence digest changes. This means a corrected evidence report
can notify after an earlier invalid or pending result, while repeated hourly
checks remain quiet.

Inspect a result manually with `--json` without `--transition-only` when an
operator needs the current explanation.
