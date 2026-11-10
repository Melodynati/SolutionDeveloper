"""Pure scoring + forecasting math (no AWS calls, fully unit-testable).

Signal per item  = source_weight x (1 + ln(1 + engagement))
Hourly signal    = sum of item signals per technology per hour
Daily series     = hourly signal rolled up to 14 UTC days
Momentum (z)     = (last day - mean of previous 6 days) / (std + 10% of mean + 1)
Forecast         = Holt's damped-trend exponential smoothing, 7 days ahead
Radar score      = 0.45*volume_norm + 0.35*momentum_norm + 0.20*diversity
Stage            = Breakout / Rising / Emerging (pioneer signal) / Mainstream / Cooling / Stable
"""
import math
import statistics

SOURCE_WEIGHTS = {
    "arxiv": 1.0,        # research: earliest, weakest commercial signal
    "huggingface": 1.3,  # open-model momentum
    "github": 1.5,       # builders adopting
    "hackernews": 1.2,   # developer attention
}


def item_signal(source, engagement):
    return SOURCE_WEIGHTS.get(source, 1.0) * (1.0 + math.log1p(max(0.0, float(engagement))))


def holt_forecast(series, horizon=7, alpha=0.4, beta=0.2, phi=0.85):
    """Holt's damped-trend method (Gardner & McKenzie).

    Damping (phi < 1) stops a single-day spike being extrapolated into an
    exponential line - the classic failure of plain Holt on news-driven data.
    Returns (forecast list, slope per day).
    """
    if not series:
        return [0.0] * horizon, 0.0
    if len(series) == 1:
        return [max(0.0, series[0])] * horizon, 0.0
    level, trend = series[0], series[1] - series[0]
    for y in series[1:]:
        prev_level = level
        level = alpha * y + (1 - alpha) * (level + phi * trend)
        trend = beta * (level - prev_level) + (1 - beta) * phi * trend
    out, damp = [], 0.0
    for h in range(1, horizon + 1):
        damp += phi ** h
        out.append(max(0.0, level + damp * trend))
    return out, trend


def momentum_z(daily):
    """daily: oldest..newest. Compare last day vs the 6 days before it."""
    if len(daily) < 2:
        return 0.0
    last, prev = daily[-1], daily[-7:-1]
    mu = statistics.fmean(prev)
    sd = statistics.pstdev(prev) if len(prev) > 1 else 0.0
    # Scale-aware floor (10% of the mean + 1) keeps very steady series from producing
    # absurd z values while still letting genuine spikes stand out.
    return (last - mu) / (sd + 0.1 * mu + 1.0)


def classify(total_7d, z, slope, volume_pct):
    """volume_pct: this tech's percentile (0..1) of 7-day volume across all techs."""
    if z >= 2.0 and volume_pct >= 0.5:
        return "Breakout"
    if z >= 2.0 and volume_pct < 0.5:
        return "Emerging"       # small but accelerating = the pioneer signal
    if z >= 0.75 or slope > 0.5:
        return "Rising"
    if z <= -1.0 or slope < -0.5:
        return "Cooling"
    if volume_pct >= 0.8:
        return "Mainstream"
    return "Stable"


def _pct_rank(values):
    s = sorted(values)
    n = len(s)
    return {v: (s.index(v) / (n - 1) if n > 1 else 1.0) for v in values}


def rank(tech_series, tech_sources, tech_meta=None):
    """
    tech_series:  {tech: [daily signal, oldest..newest]} (same length for all, e.g. 14)
    tech_sources: {tech: set of sources seen in last 7 days}
    tech_meta:    {tech: {"category": str, "is_new": bool}}
    Returns ranked list of dicts.
    """
    tech_meta = tech_meta or {}
    rows = []
    for tech, daily in tech_series.items():
        total7 = sum(daily[-7:])
        if total7 <= 0:
            continue
        z = momentum_z(daily)
        fc, slope = holt_forecast(daily)
        rows.append({"tech": tech, "daily": [round(x, 3) for x in daily], "total_7d": total7,
                     "z": z, "slope": slope, "forecast_7d": [round(x, 3) for x in fc],
                     "diversity": len(tech_sources.get(tech, ())) / len(SOURCE_WEIGHTS)})
    if not rows:
        return []
    vol_pct = _pct_rank([r["total_7d"] for r in rows])
    max_log_vol = max(math.log1p(r["total_7d"]) for r in rows) or 1.0
    for r in rows:
        vnorm = math.log1p(r["total_7d"]) / max_log_vol
        mnorm = 1 / (1 + math.exp(-r["z"]))      # squash z into 0..1
        r["score"] = round(100 * (0.45 * vnorm + 0.35 * mnorm + 0.20 * r["diversity"]), 2)
        r["volume_pct"] = round(vol_pct[r["total_7d"]], 3)
        r["stage"] = classify(r["total_7d"], r["z"], r["slope"], r["volume_pct"])
        fc_sum, last7 = sum(r["forecast_7d"]), r["total_7d"]
        r["predicted_change_pct"] = round(100 * (fc_sum - last7) / last7, 1) if last7 else 0.0
        meta = tech_meta.get(r["tech"], {})
        r["category"] = meta.get("category", "Emerging / Uncategorised")
        r["is_new"] = bool(meta.get("is_new", False))
        r["z"] = round(r["z"], 3)
        r["slope"] = round(r["slope"], 3)
        r["total_7d"] = round(r["total_7d"], 2)
        r["diversity"] = round(r["diversity"], 2)
    rows.sort(key=lambda r: r["score"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows
