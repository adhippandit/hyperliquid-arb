# ── Risk parameters ─────────────────────────────────────────────────────────
TOTAL_CAPITAL        = 10_000   # your total trading capital in dollars
MAX_POSITION_PCT     = 0.10     # never more than 10% of capital in one trade
DAILY_LOSS_LIMIT_PCT = 0.02     # stop trading for the day if down 2%
MIN_CONFIDENCE       = 0.70     # minimum model confidence to trade
MAX_OPEN_TRADES      = 5        # never hold more than 5 positions at once
STOP_LOSS_MULTIPLIER = 2.0      # exit if gap doubles from entry (e.g. 2% gap → exit at 4%)
VIX_CIRCUIT_BREAKER  = 30.0     # do not trade at all if VIX is above this level
# ────────────────────────────────────────────────────────────────────────────


def position_size(confidence: float) -> float:
    """
    Scale position size with confidence score.
    70% confidence → 5% of capital (smallest bet)
    100% confidence → 10% of capital (largest bet)
    """
    if confidence < MIN_CONFIDENCE:
        return 0.0
    scale = (confidence - MIN_CONFIDENCE) / (1.0 - MIN_CONFIDENCE)
    pct   = 0.05 + scale * (MAX_POSITION_PCT - 0.05)
    return round(min(pct, MAX_POSITION_PCT) * TOTAL_CAPITAL, 2)

def daily_loss_limit() -> float:
    return round(TOTAL_CAPITAL * DAILY_LOSS_LIMIT_PCT, 2)

def stop_loss_level(entry_gap_pct: float) -> float:
    """
    Returns the gap level at which you exit a losing trade.
    If gap doubles from entry, get out.
    e.g. entered at 2% gap → stop loss triggers at 4% gap.
    """
    return round(abs(entry_gap_pct) * STOP_LOSS_MULTIPLIER, 3)

def vix_allowed(vix: float) -> bool:
    """Returns False if VIX is too high to trade safely."""
    return vix < VIX_CIRCUIT_BREAKER

def check_all_rules(confidence: float, vix: float, daily_pnl: float) -> tuple:
    """
    Run all risk checks before entering a trade.
    Returns (allowed: bool, reason: str)
    """
    if not vix_allowed(vix):
        return False, f"VIX too high ({vix} > {VIX_CIRCUIT_BREAKER}) — circuit breaker active"
    if confidence < MIN_CONFIDENCE:
        return False, f"Confidence too low ({confidence*100:.1f}% < {MIN_CONFIDENCE*100:.0f}%)"
    if daily_pnl <= -daily_loss_limit():
        return False, f"Daily loss limit hit (${daily_pnl:+.0f}) — no more trades today"
    return True, "OK"

def risk_summary(signals: list) -> dict:
    tradeable      = [s for s in signals if s.get("confidence", 0) >= MIN_CONFIDENCE]
    total_exposure = sum(position_size(s["confidence"]) for s in tradeable)

    return {
        "total_signals":    len(tradeable),
        "capped_signals":   min(len(tradeable), MAX_OPEN_TRADES),
        "total_exposure":   round(total_exposure, 2),
        "exposure_pct":     round(total_exposure / TOTAL_CAPITAL * 100, 1),
        "daily_loss_limit": daily_loss_limit(),
        "max_per_trade":    round(TOTAL_CAPITAL * MAX_POSITION_PCT, 2),
    }


if __name__ == "__main__":
    print("Risk Parameters")
    print("=" * 45)
    print(f"  Total capital:        ${TOTAL_CAPITAL:,}")
    print(f"  Max per trade:        ${TOTAL_CAPITAL * MAX_POSITION_PCT:,.0f}  ({MAX_POSITION_PCT*100:.0f}% of capital)")
    print(f"  Daily loss limit:     ${daily_loss_limit():,.0f}  ({DAILY_LOSS_LIMIT_PCT*100:.0f}% of capital)")
    print(f"  Max open trades:      {MAX_OPEN_TRADES}")
    print(f"  Min confidence:       {MIN_CONFIDENCE*100:.0f}%")
    print(f"  Stop loss:            gap doubles from entry")
    print(f"  VIX circuit breaker:  do not trade if VIX > {VIX_CIRCUIT_BREAKER}")
    print()
    print("Position sizing by confidence:")
    for conf in [0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00]:
        size      = position_size(conf)
        stop_loss = round(size * 0.10, 2)
        print(f"  {conf*100:.0f}% confidence  →  ${size:,.0f} position  |  max loss on this trade: ${stop_loss:,.0f}")
    print()
    print("VIX circuit breaker:")
    for vix in [15, 20, 25, 30, 35]:
        status = "TRADE" if vix_allowed(vix) else "STOP — too risky"
        print(f"  VIX {vix}  →  {status}")
    print()
    print("Stop loss examples:")
    for gap in [0.5, 1.0, 2.0, 5.0, 10.0]:
        print(f"  Entered at {gap:.1f}% gap  →  exit if gap reaches {stop_loss_level(gap):.1f}%")
