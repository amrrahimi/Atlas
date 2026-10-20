import math
import numpy as np
from atlas_trader.indicators import ema, atr, rsi, bollinger, adx, all_indicators
from atlas_trader.market import Candle, demo_candles
from atlas_trader.paper import PaperAccount
from atlas_trader.strategies import Signal, evaluate, STRATEGIES


def test_indicators_warmup_and_sanity():
    c = np.arange(1, 251, dtype=float)
    assert np.isnan(ema(c, 20)[0])
    assert math.isclose(ema(c, 20)[19], 10.5)
    assert rsi(c)[-1] == 100
    mid, hi, lo = bollinger(c)
    assert lo[-1] < mid[-1] < hi[-1]
    high = c + 2
    low = c - 2
    assert np.isfinite(atr(high, low, c)[-1])
    assert 0 <= adx(high, low, c)[-1] <= 100


def test_demo_candles_are_identical_when_polled_in_same_bar():
    a = demo_candles('BTC/USD', '1h', now=1_900_001_234)
    b = demo_candles('BTC/USD', '1h', now=1_900_001_250)
    assert a == b
    # Rolling into the next bar does NOT rewrite previous-bar prices.
    after = demo_candles('BTC/USD', '1h', now=1_900_001_234 + 3600)
    assert a[1:] == after[:-1]
    assert len(a) == 285
    assert all(x.high >= max(x.open, x.close) and x.low <= min(x.open, x.close) for x in a)


def test_strategies_run_on_completed_data_only():
    bars = demo_candles('ETH/USD', '5m', now=1_900_001_000)
    for strategy in STRATEGIES:
        signal, indicators = evaluate('ETH/USD', bars, strategy)
        assert len(indicators['close']) == len(bars)
        if signal:
            assert signal.ts == bars[-2].ts
            assert signal.stop < signal.entry_ref < signal.target


def make_signal(stop=95, price=100):
    return Signal('BTC/USD', 1, 'BUY', price, stop, 110, 'Trend Confluence', 'test')


def test_account_cash_profit_and_reset():
    a = PaperAccount()
    assert a.cash == 10000
    assert a.unique_signal('BTC/USD', '5m', 'T', 1)
    assert not a.unique_signal('BTC/USD', '5m', 'T', 1)
    position = a.open(make_signal(), 100, 10)
    assert position is not None
    assert position.sl == 95
    assert position.tp > position.entry
    assert len(a.positions()) == 1
    assert a.cash < 10000
    assert a.equity({'BTC/USD': 100}) < 10000
    assert a.open(make_signal(), 100, 10) is None
    pnl = a.close(position.id, 115, 'Take profit')
    assert pnl > 0
    assert a.cash > 10000
    assert len(a.history()) == 1
    a.reset()
    assert a.cash == 10000
    assert len(a.history()) == 0


def test_stop_loss_is_checked_after_entry_and_stop_first():
    a = PaperAccount()
    p = a.open(make_signal(), 100, 60)
    # Same bar cannot be replayed from its pre-entry low.
    bars = [Candle(60, 100, 120, 80, 100, 10)]
    assert not a.check_exits('BTC/USD', bars)
    # Following completed bar touches both TP and SL. SL wins.
    bars = [Candle(60, 100, 101, 99, 100, 10),
            Candle(120, 100, 150, 90, 105, 10),
            Candle(180, 105, 110, 100, 105, 10)]
    results = a.check_exits('BTC/USD', bars)
    assert len(results) == 1
    assert results[0][2] == 'Stop loss'
    assert a.history()[0]['pnl'] < 0


def test_no_open_on_stale_prices_and_position_risk_limit():
    a = PaperAccount()
    assert a.open(make_signal(), 106, 1) is None
    p = a.open(make_signal(), 100, 1)
    assert p.qty * p.entry <= 2000.01
    assert (p.entry - p.sl) * p.qty <= 100.01
