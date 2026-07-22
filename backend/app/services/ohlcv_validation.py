from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Iterable


@dataclass(frozen=True)
class OHLCVIssue:
    index: int
    code: str
    severity: str
    message: str


def validate_bar(bar, index: int = 0) -> list[OHLCVIssue]:
    issues: list[OHLCVIssue] = []
    values = {name: float(getattr(bar, name)) for name in ("open", "high", "low", "close", "volume")}
    if any(not isfinite(v) for v in values.values()):
        return [OHLCVIssue(index, "non_finite", "critical", "OHLCV contains NaN or infinity")]
    if min(values[n] for n in ("open", "high", "low", "close")) <= 0:
        issues.append(OHLCVIssue(index, "non_positive_price", "critical", "Price must be positive"))
    if values["volume"] < 0:
        issues.append(OHLCVIssue(index, "negative_volume", "critical", "Volume cannot be negative"))
    if values["high"] < max(values["open"], values["close"], values["low"]):
        issues.append(OHLCVIssue(index, "invalid_high", "critical", "High is below OHLC values"))
    if values["low"] > min(values["open"], values["close"], values["high"]):
        issues.append(OHLCVIssue(index, "invalid_low", "critical", "Low is above OHLC values"))
    return issues


def validate_series(bars: Iterable, max_return_pct: float = 50.0) -> dict:
    rows = list(bars)
    issues: list[OHLCVIssue] = []
    seen = set()
    previous_close = None
    for idx, bar in enumerate(rows):
        issues.extend(validate_bar(bar, idx))
        timestamp = getattr(bar, "timestamp", None)
        key = timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)
        if key in seen:
            issues.append(OHLCVIssue(idx, "duplicate_timestamp", "critical", f"Duplicate timestamp: {key}"))
        seen.add(key)
        close = float(getattr(bar, "close"))
        if previous_close and previous_close > 0:
            change = abs(close / previous_close - 1) * 100
            if change > max_return_pct:
                issues.append(OHLCVIssue(idx, "extreme_return", "warning", f"One-bar return {change:.1f}%"))
        previous_close = close
    critical = sum(i.severity == "critical" for i in issues)
    warnings = len(issues) - critical
    score = max(0.0, 100.0 - critical * 25.0 - warnings * 5.0)
    return {
        "bars_count": len(rows), "valid": critical == 0, "score": round(score, 1),
        "critical_count": critical, "warning_count": warnings,
        "issues": [asdict(i) for i in issues[:200]],
    }
