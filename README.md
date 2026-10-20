# ATLAS TRADER · v0.1

**Native Windows/macOS crypto chart analysis and automated PAPER trading.**

Atlas Trader is a working first-stage desktop project. It is **not** a deployed profitable trading bot, brokerage or regulated investment service. No real orders are sent and no exchange credentials are accepted.

## What currently works

- Native **PySide6 / Qt** interface (no browser), resizable windows, draggable pane splitters, adjustable sidebars and workspace, zoom/pan charts using **pyqtgraph**.
- Multiple pair candlestick charts and a watchlist, popular pairs plus add-another-pair field. Kraken must support a custom pair for live prices.
- Trading horizons: **Scalp** (defaults 5m), **Day** (1h), **Swing/long-term** (1d); manual 1m/5m/15m/1h/4h/1d timeframes.
- Four rule-based strategies with indicator overlays: **Trend Confluence (EMA20/50/200, RSI, ADX)**; **Breakout + Volume**; **Bollinger Mean Reversion**; **MACD Momentum**. Indicators also include ATR, volatility and rolling volume.
- Market data toggle: **explicitly simulated** offline candles or **Kraken live public OHLCV** via `ccxt` (public, no credentials).
- Robot: paper-only automated BUY when a qualifying **completed candle** is first discovered *while enabled*, with a paper trade filled near the latest seen price. It doesn't enter historical signals when starting later on the same bar. Spot **long only** and no leverage.
- Price SL derived from recent lows / ATR; TP set to 2× the risk distance, recomputed at simulated fill. SL/TP/entry levels appear on charts.
- Approximate 1% paper equity risk budget per trade, 20% equity allocation per new position, 0.1% fee each side and 0.05% adverse simulated slippage. Total portfolio exposure can exceed 20% across multiple positions.
- Local **SQLite** simulated account starts at **$10,000 virtual USD**, survives restarts, history of closed trades, open positions, mark-to-market paper equity, alerts and activity log.
- Close all paper positions manually (uses last received prices), or reset paper account.
- Editable Python source, basic unit tests, GitHub Actions jobs to build a Windows app folder or macOS DMG.

## Important limitations (read before using)

1. This version **does not** send exchange orders, connect your exchange API, use futures, short, margin, place exchange-side stop losses or run a background/remote 24/7 service. The app must remain open for monitoring.
2. Machine learning is **not implemented** yet. The four strategies are mechanical technical-signal rules, not learned neural networks. No win rate or accuracy is claimed. More indicators do **not** guarantee better predictions.
3. Open paper-position symbols continue being polled even if their chart is unchecked in the watchlist. Paper prices/fills are simplified. Chart polling is every 30 seconds, not websocket tick-by-tick. Stops are checked when data arrives, not as exchange-hosted orders, and fills could be missed after outages or app shutdown.
4. New trades are sized based on local paper funds, not exchange balances. No real-time exchange trading spread/order book, funding, network interruptions or taxation is modeled.
5. Kraken OHLCV includes the current, **incomplete** bar. Strategies use the penultimate (completed) bar; historical stop/target scans use closed bars after the entry bar and the current bar's latest price only. If both SL and TP are touched in one closed bar, the model assumes SL first.
6. Switching market feeds pauses auto-entry and swaps to a separate paper ledger to avoid mixing synthetic-price and real-price trades. Stale Kraken candles do not trigger new paper entries or exits. Simulated prices are invented demonstration series and are never investment data. Public Kraken data may be unavailable, rate-limited, unsupported for some pairs or delayed.
7. These are **research examples**, not validated professional-grade strategies. Before using real money: out-of-sample backtesting, walk-forward analysis, fee/liquidity modeling, forward paper testing, time synchronization, risk limits, duplicate-order prevention and order reconciliation are required.

## Run on Windows or macOS from source

Requires Python 3.11–3.13 (64-bit) and an internet connection for installing packages. No terminal interface is shown when using the app; a terminal is only needed once for setup/build.

```
python -m venv .venv
```

Activate on **Windows**: `.venv\\Scripts\\activate`

Activate on **macOS**: `source .venv/bin/activate`

```
python -m pip install -r requirements.txt
python -m pip install -e .
python -m atlas_trader
```

From the project folder. Offline demo mode is on by default; choose **Kraken live** for real market chart candles. Starting the paper robot is optional and does not place real exchange orders.

## Create a graphical Windows `.exe` or macOS `.app` / `.dmg`

- On Windows, run `scripts\\build_windows.bat` or run PyInstaller yourself. The deliverable is a **folder** in `dist\\AtlasTrader` containing the `AtlasTrader.exe` executable and its required files.
- On macOS, run `bash scripts/build_macos.sh`; the result is `dist/AtlasTrader.app`. You can package it as a DMG with `hdiutil`.
- **You must build separately on Windows and macOS**; PyInstaller is not a cross-compiler. The included `.github/workflows/build.yml` makes both in GitHub Actions: upload this folder to a repo, choose **Actions → Build native Windows and macOS apps → Run workflow**, then download build artifacts (Windows ZIP or macOS DMG).
- Generated apps are **unsigned**. Public distribution requires Apple Developer ID signing/notarization and appropriate Windows signing; security prompts may appear otherwise.

## Run tests

```
python -m pip install -r requirements-dev.txt
python -m pip install -e .
python -m pytest -q
```

## Proposed stages towards fully automated exchange execution

**Stage 2 (research):** repeatable OHLCV backtester with walk-forward splits, latency assumptions, fees/slippage, benchmarks, Sharpe/drawdown, per-strategy sensitivity and a filter for regime/volatility changes. Genuine ML models trained on strictly past data, with leakage checks and out-of-sample evaluation. Additional filters can increase selectivity, but will not guarantee returns.

**Stage 3 (exchange sandbox):** authorized exchange selection, read-only testing, API secrets stored in OS keychain (never in logs or source), minimum order size/precision rules, risk circuit breakers, no-withdrawal keys, idempotent order IDs, open-order/position reconciliation, cancel/replace protections, server-side TP/SL where supported, API retries and audit trail. All functionality validated on specific exchange/testnet.

**Stage 4 (optional real trading):** separately enabled live mode with confirmations, conservative caps, kill switch, heartbeat/downtime rules, watchdog worker or hosted agent and cross-exchange specifics. Start small after extensive paper/sandbox testing; no profit guarantees.

## Technical overview

`src/atlas_trader/market.py` — market data / demo feed  
`src/atlas_trader/indicators.py` — technical indicators  
`src/atlas_trader/strategies.py` — signal calculations on completed bars  
`src/atlas_trader/paper.py` — cash/risk/trade history SQLite ledger  
`src/atlas_trader/charts.py` — interactive candle/SL/TP charts  
`src/atlas_trader/app.py` — Qt desktop app and polling worker

**Market risk warning:** Cryptocurrency prices are volatile. Auto trading can lose all money allocated to trading, and is never a guaranteed earning method.
