# Destination Machine Setup: running `data_logger.py` here

## Status as of 2026-08-10

Already done on `RUCHI` — pre-flight checklist passed, deps installed,
smoke test passed, and `data_logger.py` is currently running there. See
the status block at the top of `TRANSFER_PLAN.md` for details. The
remaining sections below are the reference procedure, kept for the next
machine that needs onboarding.

You're reading this because the `hyperliquid-arb` folder just synced to this
machine via OneDrive (personal account). This doc is the destination-machine
half of `TRANSFER_PLAN.md` — read that file too if you want the full
picture, including why this setup exists.

## Before you touch anything: is the logger running elsewhere?

`gap_log.db` is a single-writer SQLite file. If `data_logger.py` is running
on the other machine right now, **do not start it here** — OneDrive can't
merge concurrent writes to the same `.db` file; it will silently fork it
into a conflicted copy (e.g. `gap_log-<PCNAME>.db`) and split the dataset.

Confirm with whoever last used this project that it's stopped on the other
machine (Ctrl+C in its terminal) before proceeding.

## Pre-flight checklist

Run through these before relying on anything in this folder — catching a
problem now is easier than debugging a stalled logger later.

1. **OneDrive account** — Settings (tray icon) → Account tab → confirm the
   signed-in email is the personal account, not a work/school one.
2. **No leftover folder from a prior attempt** — if
   `C:\Users\<user>\OneDrive\hyperliquid-arb` already existed here before
   this sync, OneDrive may have renamed the incoming folder to
   `hyperliquid-arb-<PCNAME>` instead of merging. Check the folder name is
   exactly `hyperliquid-arb`, not a suffixed variant.
3. **Free disk space** — project is small (~35MB) but low free space is the
   most common reason OneDrive silently stalls mid-sync:
   `Get-PSDrive C | Select-Object Used,Free`
4. **Force `gap_log.db` to actually download** — Files On-Demand can leave
   large files as online-only placeholders. Right-click the `hyperliquid-arb`
   folder → "Always keep on this device." `data_logger.py` runs unattended
   in a loop; a placeholder file stalls or fails on first read instead of
   downloading transparently.
5. **Python 3.13+** — `python --version`. Install from python.org or the
   Microsoft Store if missing. Confirm pip too: `python -m pip --version`.
6. **Git (optional)** — only needed if you want to interact with the GitHub
   remote directly rather than through the synced folder: `git --version`.
7. **Outbound network isn't firewalled** — needs HTTPS to
   `api.hyperliquid.xyz` and Yahoo Finance. Campus/corporate networks with
   an egress allowlist can silently block both. Quick check:
   ```
   Invoke-WebRequest https://api.hyperliquid.xyz/info -Method Post -Body '{"type":"meta"}' -ContentType "application/json" -UseBasicParsing
   ```
   should return JSON, not a timeout or connection error.
8. **System clock is correct** — `data_logger.py` timestamps in UTC and
   `market_hours.py` relies on wall-clock time for `America/New_York`
   market-open checks; a wrong clock silently corrupts both. Check
   Settings → Time & Language → "Set time automatically" is on, or
   `w32tm /query /status`.

## Verify the sync actually finished

Don't proceed on a partial sync — check all three:

- `C:\Users\<user>\OneDrive\hyperliquid-arb` exists
- `gap_log.db` is present and roughly matches the source size (~30MB) — if
  it's 0 bytes, missing, or much smaller, sync isn't done yet
- `.git` folder is present (confirms a full sync, not a partial one)

## Install and smoke-test

1. From inside the project folder:
   ```
   pip install -r requirements.txt
   ```
2. Run `python data_logger.py` and let it complete one cycle. Expect:
   ```
   Logged N rows, M funding entries
   ```
   with no `[ERROR]` line.
3. Stop it with Ctrl+C once the smoke test passes.
4. Only leave it running if **this** machine is meant to be the active one
   right now — otherwise stop it after the smoke test (see the
   single-writer rule above).

## What `data_logger.py` actually needs

- Local files in the same folder: `market_hours.py`, `gap_log.db` (created
  automatically if missing, but the synced copy preserves history — don't
  delete it)
- Packages: `requests`, `yfinance`, `tzdata` — all covered by
  `requirements.txt`
- Network: outbound HTTPS to `api.hyperliquid.xyz` and Yahoo Finance, no
  auth required. No `.env` or API keys needed — both are public endpoints.

## Not relevant to running the logger

`model.pkl`, `backtest_results.xlsx`, `scorer.html`, `gap_log_formatted.xlsx`
are used by `backtest.py` / `scorer_web.py`, not data collection — they
synced along with the folder but need no action. `for_quant_review/` is an
unrelated one-off data share — ignore it.
