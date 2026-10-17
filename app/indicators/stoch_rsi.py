from __future__ import annotations


def _sma(values: list[float], period: int) -> list[float]:
    if period <= 0 or len(values) < period:
        return []
    return [sum(values[i - period + 1:i + 1]) / period for i in range(period - 1, len(values))]


def _rsi(closes: list[float], period: int) -> list[float]:
    if len(closes) < period + 1:
        return []
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    values: list[float] = []
    for i in range(period, len(deltas) + 1):
        if i > period:
            avg_gain = ((avg_gain * (period - 1)) + gains[i - 1]) / period
            avg_loss = ((avg_loss * (period - 1)) + losses[i - 1]) / period
        if avg_loss == 0:
            values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            values.append(100.0 - (100.0 / (1.0 + rs)))
    return values


def stochastic_rsi(closes: list[float], rsi_period: int = 14, stoch_period: int = 14, k_period: int = 3, d_period: int = 3) -> dict[str, float] | None:
    rsi_values = _rsi(closes, rsi_period)
    if len(rsi_values) < stoch_period + k_period + d_period - 2:
        return None
    raw: list[float] = []
    for i in range(stoch_period - 1, len(rsi_values)):
        window = rsi_values[i - stoch_period + 1:i + 1]
        low, high = min(window), max(window)
        raw.append(0.0 if high == low else 100.0 * (rsi_values[i] - low) / (high - low))
    k_values = _sma(raw, k_period)
    d_values = _sma(k_values, d_period)
    if not k_values or not d_values:
        return None
    return {"k": k_values[-1], "d": d_values[-1]}
