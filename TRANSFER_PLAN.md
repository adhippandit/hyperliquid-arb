# Transfer Plan: hyperliquid-arb → second machine (via OneDrive)

## Status as of 2026-08-16

Transfer (2026-08-10) is complete and stable. `RUCHI` remains the active
single-writer machine — `gap_log.db` has grown to ~312,998 `gaps` rows and
~31,401 `funding` rows, logging every 5 minutes with no errors. Machine last
rebooted 2026-08-13 04:29 local; `data_logger.py` (PID 8372) has been running
continuously since ~40 min after that boot, started manually.

**New this session: `data_logger.py` now auto-starts at logon on `RUCHI`.**
Added:
- `logger_startup.ps1` — cds into the project, skips launch if
  `data_logger.py` is already running (checked via `Get-CimInstance
  Win32_Process` matching on command line), otherwise starts it with output
  appended to `logger_output.log`.
- `start_logger_hidden.vbs` — runs the PowerShell script with no visible
  window.
- A shortcut in the Startup folder (`shell:startup` →
  `HyperliquidGapLogger.lnk`) that launches the vbs at every logon.

**Windows Task Scheduler was tried first and rejected** — both
`Register-ScheduledTask` and `schtasks /create` returned "Access is denied"
for a plain current-user logon trigger, even though the service was running,
NTFS perms on `C:\Windows\System32\Tasks` looked normal, and `gpresult`
showed no applied GPOs. Root cause not identified (possibly local hardening
or endpoint policy specific to this machine) — the Startup-folder shortcut
was used as a working equivalent instead. Caveat: it only fires on
interactive logon, so it won't help if this machine reboots unattended and
sits at the lock screen (no auto-login configured). If auto-start before
login is ever needed, that Task Scheduler denial needs to be root-caused
first.

**Next session on the source/other machine: do not start `data_logger.py`
there** until it's confirmed stopped on `RUCHI` first — per the
single-writer rule below. This matters more now that `RUCHI` restarts the
logger automatically on every reboot without a manual step to gate it.

Purpose: move this project so `data_logger.py` (and the rest of the project)
can be run from either of two personal machines, switching based on which
one is active, without maintaining two diverging copies of the data.

## How this works

Both code and data travel together as **one OneDrive-synced folder**. No
separate `git clone` or manual USB/cloud copy step is needed once sync is
established — the folder just appears on the other machine. GitHub (`origin`,
already configured) is untouched by this and remains available separately
for history/backup.

This machine has two OneDrive accounts signed in — personal
(`C:\Users\milin\OneDrive`) and University of Edinburgh
(`C:\Users\milin\OneDrive - University of Edinburgh`). This plan uses the
**personal** account — that's the one that needs to be signed in on the
destination machine too.

## Critical rule: only one machine runs `data_logger.py` at a time

`gap_log.db` is a plain SQLite file, not a multi-writer database. If both
machines write to it at the same time, OneDrive will not merge the changes —
it will create a conflicted copy (e.g. `gap_log-DESKTOP2.db`), silently
splitting the dataset in two.

Before starting the logger on one machine:
1. Confirm it's stopped on the other machine (Ctrl+C in its terminal).
2. Confirm OneDrive shows fully synced on **both** machines (tray icon says
   "Up to date," not the spinning-sync icon) before starting.

## Steps on THIS machine (source) — do these first

1. Stop `data_logger.py` if it's currently running (Ctrl+C).
2. Move (not copy) the project folder into the OneDrive-synced folder:
   - From: `C:\Users\milin\Documents\hyperliquid-arb`
   - To: `C:\Users\milin\OneDrive\hyperliquid-arb`
   - This carries `.git`, the GitHub remote, and full history along
     unchanged — it's just a relocation.
3. Wait for the OneDrive tray icon to show "Up to date" (uploading ~30MB,
   mostly `gap_log.db`).
4. Reopen the project in VS Code from the new path.
5. Note for whoever picks this up: `.gitignore` has an uncommitted change
   (added `for_quant_review/`) and `requirements.txt` is a new untracked
   file as of this transfer — not yet pushed to GitHub. Doesn't block
   anything below, just don't be surprised by `git status` showing changes.

## Pre-copy checklist on the SECOND device — run before OneDrive sync starts

Run these before the project folder shows up via sync, so any problem is
caught while nothing depends on this machine yet.

1. **OneDrive account** — confirm the personal account is signed in, not a
   work/school one:
   `Get-Content "$env:LOCALAPPDATA\Microsoft\OneDrive\settings\Personal\*.dat" -ErrorAction SilentlyContinue`
   is unreliable to parse; simplest is to open the OneDrive tray icon →
   Settings → Account tab and visually confirm the email matches the
   personal account used on the source machine, not a different Microsoft
   account.
2. **No pre-existing conflicting folder** — check
   `C:\Users\<user>\OneDrive\hyperliquid-arb` doesn't already exist on this
   device from an old attempt. If it does, sync will merge into it (fine) or
   OneDrive will rename the incoming one to `hyperliquid-arb-<PCname>`
   (not fine — silently forks the project). Rename or remove any leftover
   folder first.
3. **Free disk space** — the project itself is small (~35MB), but check
   overall free space isn't near zero, since low disk space is the most
   common reason OneDrive silently stalls mid-sync:
   `Get-PSDrive C | Select-Object Used,Free`
4. **Files On-Demand won't strand the DB as a placeholder** — once the
   folder appears, right-click it in Explorer → "Always keep on this
   device." `data_logger.py` runs unattended in a loop; if `gap_log.db` is
   an online-only placeholder, the first read can stall or fail instead of
   transparently downloading.
5. **Python present** — `python --version`, need 3.13+. Install from
   python.org or the Microsoft Store if missing. Also confirm pip works:
   `python -m pip --version`.
6. **Git present** (optional, only needed to interact with the GitHub
   remote directly rather than through the synced folder) — `git --version`.
7. **Outbound network access isn't firewalled** — this machine needs HTTPS
   to `api.hyperliquid.xyz` and Yahoo Finance's endpoints. If it's on a
   campus/corporate network with an egress allowlist, both can be silently
   blocked. Quick check:
   `Invoke-WebRequest https://api.hyperliquid.xyz/info -Method Post -Body '{"type":"meta"}' -ContentType "application/json" -UseBasicParsing`
   should return JSON, not a timeout or connection error.
8. **System clock is correct** — `data_logger.py` timestamps rows in UTC and
   `market_hours.py` depends on wall-clock time for
   `America/New_York` market-open checks; a wrong clock silently corrupts
   both. Check Settings → Time & Language → "Set time automatically" is on,
   or `w32tm /query /status`.

## Steps on the OTHER machine (destination), after the checklist passes

1. Wait for initial sync, then verify before doing anything else:
   - `C:\Users\<user>\OneDrive\hyperliquid-arb` exists
   - `gap_log.db` is present and roughly matches the source size (~30MB) —
     if it's 0 bytes, missing, or much smaller, sync isn't finished; don't
     proceed until it settles.
   - `.git` folder is present (confirms a full sync, not a partial one).
2. From inside the project folder: `pip install -r requirements.txt`
3. Smoke test:
   - Run `python data_logger.py`
   - Let it complete one cycle — it should print
     `Logged N rows, M funding entries` with no `[ERROR]` line
   - Stop it with Ctrl+C
4. Only leave it running if this machine is meant to be the "active" one
   right now (see the critical rule above) — otherwise stop it after the
   smoke test.

## Not needed for this transfer

- No `.env` or API keys — Hyperliquid's `/info` endpoint and `yfinance` are
  both unauthenticated public APIs.
- `model.pkl`, `backtest_results.xlsx`, `scorer.html`,
  `gap_log_formatted.xlsx` are only used by `backtest.py` / `scorer_web.py`,
  not by data collection — they'll sync along automatically with the folder,
  no extra action needed either way.
- `for_quant_review/` is a one-off external data share, unrelated to data
  collection — safe to ignore.

## Quick reference: what `data_logger.py` actually needs

- Local files in the same folder: `market_hours.py`, `gap_log.db` (created
  automatically if missing, but copy the existing one to preserve history)
- Packages: `requests`, `yfinance`, `tzdata` (installed via
  `requirements.txt`, which also covers the rest of the project)
- Network: outbound HTTPS to `api.hyperliquid.xyz` and Yahoo Finance, no
  auth required
