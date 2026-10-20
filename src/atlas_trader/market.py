"""Market data adapter: no credentials or private API usage."""
from __future__ import annotations
from dataclasses import dataclass
import datetime as dt
import math
import random
import time

@dataclass(frozen=True)
class Candle:
    ts: int            # UTC open time, seconds
    open: float
    high: float
    low: float
    close: float
    volume: float

TIMEFRAME_SECONDS = {'1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400}

POPULAR = ['BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD', 'ADA/USD',
           'DOGE/USD', 'LINK/USD', 'AVAX/USD', 'LTC/USD', 'DOT/USD']


def fetch_kraken(symbol: str, timeframe: str, limit=290):
    """Fetch OHLCV with public CCXT Kraken API (never uses private credentials)."""
    try:
        import ccxt
    except ImportError as exc:
        raise RuntimeError('ccxt not installed; install requirements.txt') from exc
    exchange = ccxt.kraken({'enableRateLimit': True, 'timeout': 12000})
    try:
        rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    finally:
        exchange.close() if hasattr(exchange, 'close') else None
    data = [Candle(int(ts // 1000), float(o), float(h), float(l), float(c), float(v))
            for ts, o, h, l, c, v in rows]
    if len(data) < 220:
        raise ValueError(f'{symbol} returned only {len(data)} candles (need 220+)')
    return data


def demo_candles(symbol: str, timeframe: str, limit=285, now=None):
    """Deterministic illustrative candles. A timestamp retains its price forever.

    This is a synthetic oscillating series for GUI/risk-flow testing only,
    NOT a replay, market prediction or meaningful strategy backtest.
    """
    seconds = TIMEFRAME_SECONDS[timeframe]
    now = int(now if now is not None else time.time())
    latest_step = now // seconds
    first_step = latest_step - limit + 1
    seed = sum((i + 1) * ord(ch) for i, ch in enumerate(symbol))
    baseline = {'BTC': 63000, 'ETH': 2800, 'SOL': 150, 'XRP': 1.8, 'ADA': .7,
                'DOGE': .19, 'LINK': 17, 'AVAX': 33, 'LTC': 100, 'DOT': 6}.get(symbol.split('/')[0], 25)

    def close_for_step(step):
        rng = random.Random(seed * 100003 + step)
        # Stable smooth cycle + deterministic noise, indexed by absolute time.
        phase = step * 0.065 + seed
        log_offset = (0.07 * math.sin(phase / 2.3)
                      + 0.04 * math.sin(phase / 0.72)
                      + 0.012 * rng.gauss(0, 1))
        return baseline * math.exp(log_offset)

    out = []
    opening = close_for_step(first_step - 1)
    for step in range(first_step, latest_step + 1):
        rng = random.Random(seed * 89111 + step)
        closing = close_for_step(step)
        high = max(opening, closing) * (1 + rng.uniform(.0002, .0035))
        low = min(opening, closing) * (1 - rng.uniform(.0002, .0035))
        out.append(Candle(step * seconds, opening, high, low, closing,
                          200 + rng.random() * 1000))
        opening = closing
    return out
