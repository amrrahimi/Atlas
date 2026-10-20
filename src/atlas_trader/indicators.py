"""Dependency-light technical indicators, returning NaN during warmup."""
from __future__ import annotations
import numpy as np


def ema(values, length: int):
    a = np.asarray(values, dtype=float)
    out = np.full(len(a), np.nan)
    if len(a) < length or length < 1:
        return out
    out[length - 1] = np.mean(a[:length])
    alpha = 2.0 / (length + 1)
    for i in range(length, len(a)):
        out[i] = alpha * a[i] + (1 - alpha) * out[i - 1]
    return out


def rma(values, length: int):
    a = np.asarray(values, dtype=float)
    out = np.full(len(a), np.nan)
    if len(a) < length or length < 1:
        return out
    out[length - 1] = np.mean(a[:length])
    for i in range(length, len(a)):
        out[i] = (out[i - 1] * (length - 1) + a[i]) / length
    return out


def rsi(close, length=14):
    close = np.asarray(close, dtype=float)
    delta = np.diff(close, prepend=close[0])
    avg_gain = rma(np.maximum(delta, 0), length)
    avg_loss = rma(np.maximum(-delta, 0), length)
    out = np.full(len(close), np.nan)
    both_zero = (avg_gain == 0) & (avg_loss == 0)
    out[both_zero] = 50.
    no_loss = (avg_loss == 0) & (avg_gain > 0)
    out[no_loss] = 100.
    valid = (avg_loss > 0) & np.isfinite(avg_gain)
    out[valid] = 100 - 100 / (1 + avg_gain[valid] / avg_loss[valid])
    return out


def atr(high, low, close, length=14):
    h, l, c = map(lambda x: np.asarray(x, dtype=float), (high, low, close))
    previous = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - previous), np.abs(l - previous)))
    return rma(tr, length)


def adx(high, low, close, length=14):
    h, l, c = map(lambda x: np.asarray(x, dtype=float), (high, low, close))
    up = np.diff(h, prepend=h[0])
    down = -np.diff(l, prepend=l[0])
    plus_dm = np.where((up > down) & (up > 0), up, 0.)
    minus_dm = np.where((down > up) & (down > 0), down, 0.)
    volatility = atr(h, l, c, length)
    plus_smoothed, minus_smoothed = rma(plus_dm, length), rma(minus_dm, length)
    plus_di = np.divide(100 * plus_smoothed, volatility, out=np.zeros_like(volatility), where=volatility > 0)
    minus_di = np.divide(100 * minus_smoothed, volatility, out=np.zeros_like(volatility), where=volatility > 0)
    denom = plus_di + minus_di
    dx = np.divide(100 * np.abs(plus_di - minus_di), denom, out=np.zeros_like(denom), where=denom > 0)
    # ADX seeded after DI warmup, not from uninitialized DX.
    result = np.full(len(h), np.nan)
    first = length - 1
    if len(h) >= first + length:
        result[first + length - 1] = np.mean(dx[first:first + length])
        for i in range(first + length, len(h)):
            result[i] = (result[i - 1] * (length - 1) + dx[i]) / length
    return result


def macd(close):
    close = np.asarray(close, dtype=float)
    fast, slow = ema(close, 12), ema(close, 26)
    line = fast - slow
    signal = np.full(len(close), np.nan)
    idx = np.where(np.isfinite(line))[0]
    if len(idx) >= 9:
        signal[idx] = ema(line[idx], 9)
    return line, signal, line - signal


def bollinger(close, length=20, multiple=2.0):
    arr = np.asarray(close, dtype=float)
    mid, upper, lower = [np.full(len(arr), np.nan) for _ in range(3)]
    for i in range(length - 1, len(arr)):
        window = arr[i - length + 1:i + 1]
        mid[i] = np.mean(window)
        sigma = np.std(window, ddof=0)
        upper[i], lower[i] = mid[i] + multiple * sigma, mid[i] - multiple * sigma
    return mid, upper, lower


def all_indicators(candles):
    c = np.array([x.close for x in candles])
    h = np.array([x.high for x in candles])
    l = np.array([x.low for x in candles])
    v = np.array([x.volume for x in candles])
    macd_line, macd_signal, macd_hist = macd(c)
    bb_mid, bb_upper, bb_lower = bollinger(c)
    vol_avg = np.full(len(v), np.nan)
    for i in range(19, len(v)):
        vol_avg[i] = np.mean(v[i - 19:i + 1])
    return dict(close=c, high=h, low=l, volume=v, ema20=ema(c, 20),
                ema50=ema(c, 50), ema200=ema(c, 200), rsi=rsi(c), atr=atr(h, l, c),
                adx=adx(h, l, c), macd=macd_line, macd_signal=macd_signal,
                macd_hist=macd_hist, bb_mid=bb_mid, bb_upper=bb_upper,
                bb_lower=bb_lower, volume_avg=vol_avg)
