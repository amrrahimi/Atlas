"""Paper trading ledger, fee+slippage, cash accounting, local SQLite persistence."""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3
import time
from pathlib import Path

FEE_RATE = 0.001             # illustrative 0.10% per side
SLIPPAGE = 0.0005           # illustrative 0.05% adverse price each side
MAX_RISK = 0.01             # 1% of marked-to-market equity (approximate)
MAX_ALLOC = 0.20            # 20% of equity in any one new position

@dataclass(frozen=True)
class Position:
    id: int
    symbol: str
    entry: float
    qty: float
    sl: float
    tp: float
    opened: int
    bar_ts: int
    strategy: str
    entry_fee: float


class PaperAccount:
    def __init__(self, path: str | Path = ':memory:'):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')
        with self.conn:
            self.conn.executescript('''
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS positions (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL,
                  entry REAL NOT NULL, qty REAL NOT NULL, sl REAL NOT NULL,
                  tp REAL NOT NULL, opened INTEGER NOT NULL, bar_ts INTEGER NOT NULL,
                  strategy TEXT NOT NULL, entry_fee REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS history (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, strategy TEXT,
                  entry REAL, exit REAL, qty REAL, sl REAL, tp REAL,
                  pnl REAL, reason TEXT, opened INTEGER, closed INTEGER);
                CREATE TABLE IF NOT EXISTS signals (
                  symbol TEXT, timeframe TEXT, strategy TEXT, bar_ts INTEGER,
                  PRIMARY KEY (symbol, timeframe, strategy, bar_ts));
            ''')
            self.conn.execute("INSERT OR IGNORE INTO settings VALUES ('cash','10000.0')")

    @property
    def cash(self):
        return float(self.conn.execute("SELECT value FROM settings WHERE key='cash'").fetchone()[0])

    def _cash(self, amount):
        self.conn.execute("UPDATE settings SET value=? WHERE key='cash'", (repr(amount),))

    def positions(self):
        rows = self.conn.execute('SELECT * FROM positions ORDER BY opened DESC').fetchall()
        return [Position(**dict(row)) for row in rows]

    def history(self, limit=200):
        return [dict(row) for row in self.conn.execute('SELECT * FROM history ORDER BY id DESC LIMIT ?', (limit,))]

    def equity(self, prices=None):
        prices = prices or {}
        return self.cash + sum(p.qty * prices.get(p.symbol, p.entry) for p in self.positions())

    def unique_signal(self, symbol, timeframe, strategy, bar_ts):
        with self.conn:
            cur = self.conn.execute('INSERT OR IGNORE INTO signals VALUES (?,?,?,?)',
                                    (symbol, timeframe, strategy, bar_ts))
        return cur.rowcount == 1

    def open(self, signal, market_price, bar_ts, prices=None):
        if any(p.symbol == signal.symbol for p in self.positions()):
            return None
        if market_price <= 0:
            return None
        entry = market_price * (1 + SLIPPAGE)
        # Only act if stop remains below actual fill; don't open on stale signals
        # where live market has moved too far from the analyzed candle.
        if signal.stop >= entry or abs(market_price / signal.entry_ref - 1) > .015:
            return None
        stop_distance = entry - signal.stop
        equity = self.equity(prices)
        qty = min(equity * MAX_RISK / stop_distance,
                  equity * MAX_ALLOC / entry,
                  self.cash / (entry * (1 + FEE_RATE)))
        if qty * entry < 10:
            return None
        entry_fee = qty * entry * FEE_RATE
        if qty <= 0 or qty * entry + entry_fee > self.cash + 1e-6:
            return None
        # TP is recomputed from current fill to preserve target risk-reward.
        target = entry + 2 * (entry - signal.stop)
        with self.conn:
            self._cash(self.cash - qty * entry - entry_fee)
            cur = self.conn.execute('''INSERT INTO positions
                (symbol,entry,qty,sl,tp,opened,bar_ts,strategy,entry_fee)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (signal.symbol, entry, qty, signal.stop, target, int(time.time()),
                 bar_ts, signal.strategy, entry_fee))
        return next((p for p in self.positions() if p.id == cur.lastrowid), None)

    def close(self, position_id, exit_price, reason='Manual'):
        p = next((p for p in self.positions() if p.id == position_id), None)
        if p is None:
            return None
        fill = exit_price * (1 - SLIPPAGE)
        proceeds = p.qty * fill
        exit_fee = proceeds * FEE_RATE
        pnl = proceeds - exit_fee - p.qty * p.entry - p.entry_fee
        with self.conn:
            self._cash(self.cash + proceeds - exit_fee)
            self.conn.execute('''INSERT INTO history
                (symbol,strategy,entry,exit,qty,sl,tp,pnl,reason,opened,closed)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (p.symbol, p.strategy, p.entry, fill, p.qty, p.sl, p.tp, pnl,
                 reason, p.opened, int(time.time())))
            self.conn.execute('DELETE FROM positions WHERE id=?', (p.id,))
        return pnl

    def check_exits(self, symbol, candles):
        """Conservative SL-first order if a completed bar touches both SL and TP.

        The current forming candle's past high/low are NOT replayed as if they
        occurred after the entry. For an open bar check the last seen price only.
        """
        exits = []
        if not candles:
            return exits
        for p in list(self.positions()):
            if p.symbol != symbol:
                continue
            hit = None
            for candle in candles[:-1]:
                if candle.ts <= p.bar_ts:
                    continue
                if candle.low <= p.sl:
                    hit = (min(candle.open, p.sl), 'Stop loss')
                    break
                if candle.high >= p.tp:
                    hit = (p.tp, 'Take profit')
                    break
            if hit is None:
                last = candles[-1].close
                if last <= p.sl:
                    hit = (last, 'Stop loss (last price)')
                elif last >= p.tp:
                    hit = (p.tp, 'Take profit (last price)')
            if hit:
                pnl = self.close(p.id, *hit)
                exits.append((p, pnl, hit[1]))
        return exits

    def reset(self, balance=10000.0):
        with self.conn:
            self.conn.execute('DELETE FROM positions')
            self.conn.execute('DELETE FROM history')
            self.conn.execute('DELETE FROM signals')
            self._cash(float(balance))
