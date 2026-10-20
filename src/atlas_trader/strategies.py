"""Rule-based educational signals. No AI/ML profitability claims."""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
from .indicators import all_indicators

STRATEGIES = {
    'Trend Confluence': 'EMA 20/50, RSI, ADX, ATR',
    'Breakout + Volume': 'Donchian 20, volume, ADX, ATR',
    'Mean Reversion': 'Bollinger 20, RSI, ADX, ATR',
    'MACD Momentum': 'MACD, RSI, EMA 50, ATR',
}

@dataclass(frozen=True)
class Signal:
    symbol: str
    ts: int
    side: str
    entry_ref: float
    stop: float
    target: float
    strategy: str
    reason: str


def evaluate(symbol: str, candles, strategy: str, *, index=None):
    """Only evaluate a COMPLETED candle (default penultimate/current bar excluded)."""
    a = all_indicators(candles)
    i = len(candles) - 2 if index is None else index
    if i < 205 or i >= len(candles):
        return None, a
    c = a['close'][i]
    rsi, adx, atr = a['rsi'][i], a['adx'][i], a['atr'][i]
    if not all(map(math.isfinite, [c, rsi, adx, atr, a['ema50'][i]])) or atr <= 0:
        return None, a
    long, reason = False, ''
    if strategy == 'Trend Confluence':
        long = (a['ema20'][i] > a['ema50'][i] > a['ema200'][i]
                and c > a['ema20'][i] and 51 < rsi < 69 and adx > 21)
        reason = f'Uptrend EMA20>50>200; RSI {rsi:.1f}; ADX {adx:.1f}'
    elif strategy == 'Breakout + Volume':
        past_high = float(np.max(a['high'][i-20:i]))
        prev_avg = a['volume_avg'][i-1]
        long = (c > past_high and a['volume'][i] > 1.3 * prev_avg
                and adx > 18 and c > a['ema50'][i])
        reason = f'20-bar breakout; volume spike; ADX {adx:.1f}'
    elif strategy == 'Mean Reversion':
        long = (a['close'][i-1] < a['bb_lower'][i-1]
                and c > a['bb_lower'][i] and 25 < rsi < 46 and adx < 24)
        reason = f'Re-entry into Bollinger channel; RSI {rsi:.1f}; ADX {adx:.1f}'
    elif strategy == 'MACD Momentum':
        long = (a['macd_hist'][i-1] <= 0 < a['macd_hist'][i]
                and c > a['ema50'][i] and 46 < rsi < 73)
        reason = f'MACD bullish cross; RSI {rsi:.1f}; above EMA50'
    if not long:
        return None, a
    recent_low = float(np.min(a['low'][max(0, i-9):i+1]))
    stop = min(c - atr * 1.6, recent_low - atr * .25)
    distance = c - stop
    if distance <= 0 or distance / c > .12:
        return None, a
    target = c + 2.0 * distance
    return Signal(symbol, candles[i].ts, 'BUY', c, stop, target, strategy, reason), a
