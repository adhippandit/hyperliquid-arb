"""
Shared data loading + event construction for model.py and backtest.py.

A single "event" is one gap dislocation, not one 5-minute observation of it.
Treating every snapshot of the same still-open gap as an independent data
point (a) lets a model overfit to whichever few events happened to stay open
longest, since they dominate the row count, and (b) lets a backtest count one
real trade as a dozen. Collapsing to one row per event, at the moment the gap
first crosses the signal threshold, fixes both at the source.
"""
import sqlite3
import pandas as pd
from risk import STOP_LOSS_MULTIPLIER

DB_FILE = "gap_log.db"

SIGNAL_THRESHOLD = 2.0    # gap_pct below this is too small — fee+spread costs eat the whole edge (confirmed 2026-09-04: raised from 0.5 after backtesting on two independent time periods showed small gaps barely profitable after real costs, while 2%+ gaps showed a large, consistent margin)
CLOSE_THRESHOLD  = 0.30   # gap_pct below this = considered closed
HORIZON_HOURS    = 48     # max hours we'd hold a trade
SANITY_LIMIT     = 20.0   # gap_pct above this almost certainly means a bad price read, not a real weekend dislocation

DAY_MAP = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2,
    "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6
}

TICKERS = [
    "NVDA", "TSLA", "AAPL", "AMZN", "MSFT",
    "GOOGL", "META", "NFLX", "AMD", "INTC",
    "COIN", "MSTR", "PLTR", "ARM", "TSM",
    "GME", "BB", "NOK", "HOOD", "ZM",
    "BABA", "MU", "QCOM", "AVGO", "ORCL",
    "NOW", "RIVN",
]
TICKER_CODES = {t: i for i, t in enumerate(TICKERS)}

FEATURES = [
    "gap_abs", "is_weekend", "day_num", "hour_utc",
    "hours_to_open", "vix", "bid_ask_spread_pct", "ticker_close_rate",
    "funding_rate",
]


def load_data() -> pd.DataFrame:
    con = sqlite3.connect(DB_FILE)
    df = pd.read_sql("SELECT * FROM gaps ORDER BY id", con)
    con.close()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["day_num"]     = df["day_of_week"].map(DAY_MAP)
    df["is_weekend"]  = df["day_num"].isin([5, 6]).astype(int)
    df["gap_abs"]     = df["gap_pct"].abs()
    df["ticker_code"] = df["ticker"].map(TICKER_CODES)

    # Attach whatever funding rate was in effect at (or just before) each
    # snapshot's own timestamp — never a later one, so this can't leak the
    # future into a clue that's supposed to be "known at the time."
    con = sqlite3.connect(DB_FILE)
    funding = pd.read_sql("SELECT ticker, timestamp, funding_rate FROM funding", con)
    con.close()
    funding["timestamp"] = pd.to_datetime(funding["timestamp"])

    df = df.sort_values("timestamp")
    funding = funding.sort_values("timestamp")
    df = pd.merge_asof(df, funding, on="timestamp", by="ticker", direction="backward")
    df["funding_rate"] = df["funding_rate"].fillna(0.0)
    return df


def build_events(df: pd.DataFrame) -> pd.DataFrame:
    """
    One row per gap event: the first eligible snapshot for a ticker once its
    previous event (if any) has resolved. Each event also carries when/how
    it resolved (label, exit_time, exit_gap_abs, outcome), computed once
    here so model.py and backtest.py can't compute it two different ways.

    Exit is whichever of these happens first:
      - the gap closes below CLOSE_THRESHOLD (WIN)
      - the gap widens to STOP_LOSS_MULTIPLIER x the entry size (STOPPED_OUT) —
        a real stop-loss, not just a formula that exists but never runs
      - HORIZON_HOURS passes with neither happening (TIMEOUT)
    Both STOPPED_OUT and TIMEOUT are non-wins (label 0); a capped loss is
    still a loss for training purposes, it's just a smaller one for P&L.
    """
    df = df.sort_values(["ticker", "timestamp"]).reset_index(drop=True)
    df["signal_eligible"] = (df["gap_abs"] >= SIGNAL_THRESHOLD) & (df["gap_abs"] <= SANITY_LIMIT)

    events = []
    for ticker, g in df.groupby("ticker"):
        g = g.sort_values("timestamp")
        next_allowed_time = None
        closes_seen = 0
        total_seen = 0
        for _, row in g.iterrows():
            if not row["signal_eligible"]:
                continue
            # A gap sitting right at SIGNAL_THRESHOLD can flicker above/below
            # it between 5-minute snapshots. Gating on "the previous event
            # for this ticker has actually resolved" instead of "eligible
            # now and wasn't eligible last snapshot" stops that flicker from
            # being fragmented into several fake back-to-back events for
            # what is really one ongoing dislocation.
            if next_allowed_time is not None and row["timestamp"] < next_allowed_time:
                continue

            future = g[
                (g["timestamp"] > row["timestamp"]) &
                (g["timestamp"] <= row["timestamp"] + pd.Timedelta(hours=HORIZON_HOURS))
            ]
            if future.empty:
                continue  # not enough future data to know what happened — drop, don't guess

            stop_level = row["gap_abs"] * STOP_LOSS_MULTIPLIER
            closed  = future[future["gap_abs"] < CLOSE_THRESHOLD]
            stopped = future[future["gap_abs"] >= stop_level]

            candidates = []
            if not closed.empty:
                candidates.append((closed.iloc[0]["timestamp"], closed.iloc[0], 1, "WIN"))
            if not stopped.empty:
                candidates.append((stopped.iloc[0]["timestamp"], stopped.iloc[0], 0, "STOPPED_OUT"))

            if candidates:
                # whichever happens first in time wins — you don't get to wait
                # for the close if the stop-loss triggered hours earlier
                candidates.sort(key=lambda c: c[0])
                _, exit_row, label, outcome = candidates[0]
            else:
                exit_row, label, outcome = future.iloc[-1], 0, "TIMEOUT"

            event = row.to_dict()
            event["label"]        = label
            event["outcome"]      = outcome
            event["exit_time"]    = exit_row["timestamp"]
            event["exit_gap_abs"] = exit_row["gap_abs"]
            event["ticker_close_rate"] = closes_seen / total_seen if total_seen > 0 else 0.5
            closes_seen += label
            total_seen  += 1
            events.append(event)

            next_allowed_time = exit_row["timestamp"]

    return pd.DataFrame(events)


def ticker_close_rates() -> dict:
    """
    Each ticker's historical closing rate using every event collected so
    far — for live scoring only. The training-time ticker_close_rate column
    only looks backward from each past event, to avoid leaking the future
    into a historical test. Live scoring has no future to leak from "now,"
    so using the complete history here is honest, not a shortcut.
    """
    df = load_data()
    df = build_features(df)
    events = build_events(df)
    return events.groupby("ticker")["label"].mean().to_dict()


def time_split(df: pd.DataFrame, train_frac: float = 0.8):
    """Split by time, not randomly — test is strictly the most recent slice."""
    df = df.sort_values("timestamp")
    cutoff = df["timestamp"].quantile(train_frac)
    train = df[df["timestamp"] <= cutoff]
    test  = df[df["timestamp"] >  cutoff]
    return train, test
