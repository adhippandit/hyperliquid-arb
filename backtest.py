import sqlite3
import pandas as pd
import pickle
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from risk import MIN_CONFIDENCE
from events import load_data, build_features, build_events, time_split, FEATURES, DB_FILE

MODEL_FILE    = "model.pkl"
POSITION_SIZE = 1000   # dollars per trade


def funding_income(con, ticker, direction, entry_time, exit_time, position_size):
    """
    Hyperliquid pays funding hourly between longs and shorts (see funding
    table, backfilled by backfill_funding.py). Positive funding_rate means
    longs pay shorts; we're short whenever the gap is a premium, which is
    exactly the side that gets paid — so this is usually a real tailwind,
    not just noise, but it's summed from the actual recorded rate per hour
    rather than assumed.
    """
    rows = con.execute(
        "SELECT funding_rate FROM funding WHERE ticker = ? AND timestamp > ? AND timestamp <= ?",
        (ticker, entry_time.strftime("%Y-%m-%d %H:%M:%S"), exit_time.strftime("%Y-%m-%d %H:%M:%S")),
    ).fetchall()
    sign = 1 if direction == "SHORT" else -1
    return sum(sign * r[0] * position_size for r in rows)


def run_backtest(test_events: pd.DataFrame, model) -> pd.DataFrame:
    test_events = test_events.dropna(subset=FEATURES).copy()
    test_events["confidence"] = model.predict_proba(test_events[FEATURES])[:, 1]

    # Each row here is already one distinct gap event (see events.py) — no
    # need to dedupe further, unlike the old row-per-5-minutes version.
    signals = test_events[test_events["confidence"] >= MIN_CONFIDENCE].copy()
    print(f"  {len(signals):,} of {len(test_events):,} test events meet the {MIN_CONFIDENCE*100:.0f}% confidence threshold", flush=True)

    con = sqlite3.connect(DB_FILE)
    has_funding_table = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='funding'"
    ).fetchone() is not None

    trades = []
    for _, row in signals.iterrows():
        direction    = "SHORT" if row["gap_pct"] > 0 else "LONG"
        spread       = row["bid_ask_spread_pct"] or 0.1
        gap_captured = row["gap_abs"] - row["exit_gap_abs"]
        spread_cost  = spread * POSITION_SIZE / 100
        funding      = (
            funding_income(con, row["ticker"], direction, row["timestamp"], row["exit_time"], POSITION_SIZE)
            if has_funding_table else 0.0
        )
        pnl          = round((gap_captured / 100) * POSITION_SIZE - spread_cost + funding, 4)
        hours_held   = round((row["exit_time"] - row["timestamp"]).total_seconds() / 3600, 1)

        trades.append({
            "ticker":        row["ticker"],
            "entry_time":    row["timestamp"].strftime("%Y-%m-%d %H:%M"),
            "exit_time":     row["exit_time"].strftime("%Y-%m-%d %H:%M"),
            "direction":     direction,
            "entry_gap_pct": round(row["gap_pct"], 3),
            "exit_gap_pct":  round(row["exit_gap_abs"] if row["gap_pct"] > 0 else -row["exit_gap_abs"], 3),
            "spread_pct":    round(spread, 4),
            "confidence":    f"{row['confidence']*100:.1f}%",
            "funding_usd":   round(funding, 4),
            "hours_held":    hours_held,
            "outcome":       row["outcome"],
            "pnl_usd":       pnl,
        })

    con.close()
    return pd.DataFrame(trades)


def print_summary(trades_df):
    if trades_df.empty:
        print(f"No trades were generated. Try lowering MIN_CONFIDENCE in risk.py (currently {MIN_CONFIDENCE*100:.0f}%).")
        return

    total       = len(trades_df)
    wins        = (trades_df["outcome"] == "WIN").sum()
    losses      = (trades_df["outcome"] == "LOSS").sum()
    win_rate    = wins / total * 100
    total_pnl   = trades_df["pnl_usd"].sum()
    avg_pnl     = trades_df["pnl_usd"].mean()
    best_trade  = trades_df["pnl_usd"].max()
    worst_trade = trades_df["pnl_usd"].min()
    total_funding = trades_df["funding_usd"].sum()

    print("\n" + "="*50)
    print("  BACKTEST RESULTS")
    print("="*50)
    print(f"  Position size:   ${POSITION_SIZE:,} per trade")
    print(f"  Total trades:    {total}")
    print(f"  Wins:            {wins}  ({win_rate:.1f}%)")
    print(f"  Losses:          {losses}  ({100-win_rate:.1f}%)")
    print(f"  Total P&L:       ${total_pnl:+.2f}   (of which funding: ${total_funding:+.2f})")
    print(f"  Avg P&L / trade: ${avg_pnl:+.2f}")
    print(f"  Best trade:      ${best_trade:+.2f}")
    print(f"  Worst trade:     ${worst_trade:+.2f}")
    print("="*50)
    print()


def save_excel(trades_df):
    OUTPUT = "backtest_results.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Backtest Results"

    headers = list(trades_df.columns)

    # Styles
    navy        = "1E3A5F"
    white       = "FFFFFF"
    win_green   = "DEFFDE"
    loss_red    = "FFDEDE"
    alt_blue    = "F5F8FF"
    thin        = Side(style="thin", color="CCCCCC")
    border      = Border(left=thin, right=thin, top=thin, bottom=thin)

    header_fill = PatternFill("solid", fgColor=navy)
    header_font = Font(bold=True, color=white, size=10)

    for col_idx, col_name in enumerate(headers, 1):
        cell           = ws.cell(row=1, column=col_idx, value=col_name)
        cell.fill      = header_fill
        cell.font      = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border    = border

    for row_idx, (_, row) in enumerate(trades_df.iterrows(), 2):
        is_win = row["outcome"] == "WIN"
        for col_idx, col_name in enumerate(headers, 1):
            val            = row[col_name]
            cell           = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.alignment = Alignment(horizontal="center")
            cell.font      = Font(size=10)
            cell.border    = border
            if is_win:
                cell.fill = PatternFill("solid", fgColor=win_green)
            elif row_idx % 2 == 0:
                cell.fill = PatternFill("solid", fgColor=alt_blue)

    col_widths = {
        "ticker": 8, "entry_time": 18, "exit_time": 18, "direction": 10,
        "entry_gap_pct": 14, "exit_gap_pct": 13, "spread_pct": 11,
        "confidence": 12, "funding_usd": 12, "hours_held": 12, "outcome": 10, "pnl_usd": 12,
    }
    for col_idx, col_name in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = col_widths.get(col_name, 14)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

    # Summary sheet
    ws2 = wb.create_sheet("Summary")
    total         = len(trades_df)
    wins          = (trades_df["outcome"] == "WIN").sum()
    total_pnl     = trades_df["pnl_usd"].sum()
    avg_pnl       = trades_df["pnl_usd"].mean()
    total_funding = trades_df["funding_usd"].sum()

    summary_rows = [
        ("Position size per trade", f"${POSITION_SIZE:,}"),
        ("Total trades",            total),
        ("Wins",                    wins),
        ("Losses",                  total - wins),
        ("Win rate",                f"{wins/total*100:.1f}%"),
        ("Total P&L",               f"${total_pnl:+.2f}"),
        ("  of which funding",      f"${total_funding:+.2f}"),
        ("Avg P&L per trade",       f"${avg_pnl:+.2f}"),
        ("Best trade",              f"${trades_df['pnl_usd'].max():+.2f}"),
        ("Worst trade",             f"${trades_df['pnl_usd'].min():+.2f}"),
    ]

    for r_idx, (label, value) in enumerate(summary_rows, 2):
        ws2.cell(row=r_idx, column=1, value=label).font  = Font(bold=True, size=11)
        ws2.cell(row=r_idx, column=2, value=value).font  = Font(size=11)
    ws2.column_dimensions["A"].width = 28
    ws2.column_dimensions["B"].width = 16

    wb.save(OUTPUT)
    print(f"  Full trade log saved to '{OUTPUT}'")
    print("  Open that file in Excel to see every trade.\n")


if __name__ == "__main__":
    print("Loading data...", flush=True)
    df = load_data()
    print(f"  {len(df):,} rows loaded", flush=True)

    df = build_features(df)

    print("Collapsing into distinct gap events...", flush=True)
    events = build_events(df)
    print(f"  {len(events):,} distinct events", flush=True)

    print("Splitting by time (same cutoff model.py used for training)...", flush=True)
    train_events, test_events = time_split(events)
    print(f"  Train events: {len(train_events):,}  |  Test events: {len(test_events):,} (never trained on)", flush=True)

    print("Loading model...", flush=True)
    with open(MODEL_FILE, "rb") as f:
        model = pickle.load(f)

    print("Running backtest on unseen test events only...", flush=True)
    trades_df = run_backtest(test_events, model)

    print_summary(trades_df)
    save_excel(trades_df)
