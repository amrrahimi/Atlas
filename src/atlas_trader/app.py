"""Native Windows/macOS GUI for Atlas Trader (paper trading only)."""
from __future__ import annotations
import datetime as dt
import os
import time
from pathlib import Path
import sys
import traceback
from PySide6.QtCore import QStandardPaths, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)
from .charts import ChartCard, DOWN, UP
from .market import POPULAR, TIMEFRAME_SECONDS, demo_candles, fetch_kraken
from .paper import PaperAccount
from .strategies import STRATEGIES, evaluate

APP_STYLE = '''
QWidget { background: #0b1120; color: #dce6f5; font-family: "Arial", "Inter", sans-serif; font-size: 12px; }
QMainWindow { background: #0b1120; }
QFrame#sidebar, QFrame#rightPanel { background: #101828; border: 1px solid #243145; border-radius: 12px; }
QFrame#topBar { background: #101828; border-bottom: 1px solid #243145; }
QFrame#metric { background: #172238; border: 1px solid #25364d; border-radius: 10px; }
QFrame#chartCard { background: #121a2a; border: 1px solid #27354b; border-radius: 12px; }
QLabel#logo { color: #f5f7fc; font-size: 23px; font-weight: 800; }
QLabel#sectionTitle { color: #879ab6; font-size: 10px; font-weight: 750; letter-spacing: 1px; }
QLabel#metricValue { color: #f2f6fc; font-size: 22px; font-weight: 750; }
QLabel#metricLabel { color: #8ea2be; font-size: 11px; }
QLabel#chartName { color: #f0f6ff; font-size: 14px; font-weight: 700; }
QLabel#chartPrice { color: #28d4a0; font-size: 14px; font-weight: 700; }
QLineEdit, QComboBox, QListWidget, QTextEdit { background: #172238; border: 1px solid #2d3b55; border-radius: 7px; padding: 8px; selection-background-color: #255eb7; }
QComboBox QAbstractItemView { background: #172238; color: #eef4fc; selection-background-color: #2855a1; }
QPushButton { background: #223754; border: 1px solid #385072; border-radius: 7px; padding: 9px 12px; font-weight: 650; }
QPushButton:hover { background: #2b4a73; }
QPushButton#primary { background: #1e9d80; color: #fff; border: none; }
QPushButton#primary:hover { background: #17b894; }
QPushButton#stop { background: #683b47; color: #f6d4db; }
QPushButton#stop:hover { background: #8b4758; }
QTabWidget::pane { border: 1px solid #27354b; background: #121a2a; border-radius: 7px; }
QTabBar::tab { padding: 9px 19px; color: #8ea2be; background: #111a2b; }
QTabBar::tab:selected { color: #e7f2ff; background: #243753; }
QTableWidget { background: #101828; alternate-background-color: #152035; border: none; gridline-color: #26354a; }
QHeaderView::section { background: #172238; padding: 7px; border: none; color: #a6b8d0; }
QScrollBar:vertical { background: #101828; width: 9px; }
QScrollBar::handle:vertical { background: #354b69; border-radius: 4px; }
QStatusBar { background: #0e1726; color: #a8b9d1; }
'''


class FetchWorker(QThread):
    ready = Signal(object)

    def __init__(self, symbols, timeframe, source):
        super().__init__()
        self.symbols, self.timeframe, self.source = symbols[:], timeframe, source

    def run(self):
        results, errors = {}, {}
        for sym in self.symbols:
            if self.isInterruptionRequested():
                break
            try:
                results[sym] = (fetch_kraken(sym, self.timeframe)
                                if self.source == 'Kraken live' else demo_candles(sym, self.timeframe))
            except Exception as exc:
                errors[sym] = str(exc)
        self.ready.emit((self.timeframe, self.source, results, errors))


class AtlasWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Atlas Trader | Research & Paper Trading')
        self.resize(1580, 960)
        self.setMinimumSize(980, 650)
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        os.makedirs(folder, exist_ok=True)
        self.demo_account = PaperAccount(Path(folder) / 'atlas_trader_demo.sqlite3')
        self.kraken_account = PaperAccount(Path(folder) / 'atlas_trader_kraken_paper.sqlite3')
        self.paper = self.demo_account
        self.worker = None
        self.auto_enabled = False
        self.bars = {}
        self.indicators = {}
        self.signals = {}
        self.chart_cards = {}
        self.last_prices = {}
        self.log_lines = []
        self.construct_ui()
        self.build_chart_grid()
        self.show_balance()
        self.load_tables()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.scan)
        self.timer.start(30_000)
        QTimer.singleShot(350, self.scan)

    def label(self, text, cls='sectionTitle'):
        l = QLabel(text)
        l.setObjectName(cls)
        return l

    def construct_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QFrame()
        top.setObjectName('topBar')
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(20, 12, 20, 12)
        logo = self.label('◈  ATLAS TRADER', 'logo')
        top_l.addWidget(logo)
        top_l.addSpacing(18)
        top_l.addWidget(self.label('Native crypto research terminal  •  v0.1'))
        top_l.addStretch()
        self.market_state = QLabel('●  SIMULATED MARKET DATA')
        self.market_state.setStyleSheet('color: #e3ba76; font-weight: bold;')
        top_l.addWidget(self.market_state)
        top_l.addSpacing(16)
        self.robot_state = QLabel('ROBOT IDLE')
        self.robot_state.setStyleSheet('color: #a2b4cf; font-weight: bold;')
        top_l.addWidget(self.robot_state)
        outer.addWidget(top)

        metrics = QFrame()
        ml = QHBoxLayout(metrics)
        ml.setContentsMargins(15, 10, 15, 9)
        self.cash_metric = self.metric(ml, 'AVAILABLE CASH', '$10,000.00')
        self.equity_metric = self.metric(ml, 'PAPER EQUITY', '$10,000.00')
        self.positions_metric = self.metric(ml, 'OPEN POSITIONS', '0')
        self.pnl_metric = self.metric(ml, 'REALIZED P&L', '$0.00')
        outer.addWidget(metrics)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)
        outer.addWidget(splitter, 1)

        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setMinimumWidth(215)
        s = QVBoxLayout(sidebar)
        s.setContentsMargins(15, 18, 15, 16)
        s.setSpacing(9)
        s.addWidget(self.label('TRADING HORIZON'))
        self.horizon = QComboBox()
        self.horizon.addItems(['Scalping', 'Day trading', 'Swing / long-term'])
        self.horizon.currentTextChanged.connect(self.change_horizon)
        s.addWidget(self.horizon)
        s.addWidget(self.label('TIMEFRAME'))
        self.timeframe = QComboBox()
        self.timeframe.addItems(list(TIMEFRAME_SECONDS.keys()))
        self.timeframe.setCurrentText('5m')
        self.timeframe.currentTextChanged.connect(self.change_timeframe)
        s.addWidget(self.timeframe)
        s.addWidget(self.label('STRATEGY'))
        self.strategy = QComboBox()
        self.strategy.addItems(STRATEGIES)
        self.strategy.currentTextChanged.connect(self.strategy_changed)
        s.addWidget(self.strategy)
        self.strategy_info = QLabel(STRATEGIES[self.strategy.currentText()])
        self.strategy_info.setWordWrap(True)
        self.strategy_info.setStyleSheet('color: #93a9c4;')
        s.addWidget(self.strategy_info)
        s.addWidget(self.label('MARKET FEED'))
        self.source = QComboBox()
        self.source.addItems(['Simulated (offline)', 'Kraken live'])
        self.source.currentTextChanged.connect(self.source_changed)
        s.addWidget(self.source)
        s.addWidget(self.label('WATCHLIST  •  SELECT MULTIPLE'))
        self.watchlist = QListWidget()
        self.watchlist.setMinimumHeight(170)
        self.watchlist.itemChanged.connect(self.build_chart_grid)
        for i, sym in enumerate(POPULAR):
            self.add_watch_item(sym, i < 2)
        s.addWidget(self.watchlist, 1)
        self.watchlist.itemChanged.connect(lambda _: QTimer.singleShot(0, self.scan))
        add_row = QHBoxLayout()
        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText('e.g. TRX/USD')
        self.symbol_input.returnPressed.connect(self.add_custom)
        add_button = QPushButton('+')
        add_button.setToolTip('Add a pair (Kraken availability checked during fetch)')
        add_button.clicked.connect(self.add_custom)
        add_row.addWidget(self.symbol_input, 1)
        add_row.addWidget(add_button)
        s.addLayout(add_row)
        self.alerts = QCheckBox('Sound alerts')
        self.alerts.setChecked(True)
        s.addWidget(self.alerts)
        self.scan_button = QPushButton('↻  Refresh charts')
        self.scan_button.clicked.connect(self.scan)
        s.addWidget(self.scan_button)
        self.auto_button = QPushButton('▶  Start paper robot')
        self.auto_button.setObjectName('primary')
        self.auto_button.clicked.connect(self.toggle_robot)
        s.addWidget(self.auto_button)
        self.exchange_button = QPushButton('🔒  Exchange connection (planned)')
        self.exchange_button.clicked.connect(self.show_exchange_info)
        s.addWidget(self.exchange_button)
        self.reset_button = QPushButton('Reset paper account')
        self.reset_button.clicked.connect(self.reset_paper)
        s.addWidget(self.reset_button)
        splitter.addWidget(sidebar)

        middle = QSplitter(Qt.Orientation.Vertical)
        middle.setHandleWidth(7)
        charts_wrapper = QFrame()
        cw_l = QVBoxLayout(charts_wrapper)
        cw_l.setContentsMargins(7, 5, 7, 0)
        banner = QLabel('  CHART WORKSPACE   •   Mouse wheel to zoom   •   Drag to pan   •   All prices are illustrative until Kraken live is selected')
        banner.setStyleSheet('color: #8fa2bc;')
        cw_l.addWidget(banner)
        self.chart_scroll = QScrollArea()
        self.chart_scroll.setWidgetResizable(True)
        self.chart_scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Every row and column uses draggable Qt splitter handles.
        self.chart_splitter = QSplitter(Qt.Orientation.Vertical)
        self.chart_splitter.setHandleWidth(8)
        self.chart_splitter.setChildrenCollapsible(False)
        self.chart_scroll.setWidget(self.chart_splitter)
        cw_l.addWidget(self.chart_scroll, 1)
        middle.addWidget(charts_wrapper)
        tabs = QTabWidget()
        self.position_table = self.table(['Pair', 'Entry', 'Last', 'Quantity', 'SL', 'TP', 'Unrealized P&L'])
        self.history_table = self.table(['Closed (UTC)', 'Pair', 'Strategy', 'Entry', 'Exit', 'Quantity', 'Realized P&L', 'Reason'])
        self.activity = QTextEdit()
        self.activity.setReadOnly(True)
        tabs.addTab(self.position_table, 'Open positions')
        tabs.addTab(self.history_table, 'Trade history')
        tabs.addTab(self.activity, 'Robot activity')
        tabs.setMinimumHeight(220)
        middle.addWidget(tabs)
        middle.setSizes([600, 260])
        splitter.addWidget(middle)
        right = QFrame()
        right.setObjectName('rightPanel')
        right.setMinimumWidth(210)
        r = QVBoxLayout(right)
        r.setContentsMargins(15, 18, 15, 12)
        r.addWidget(self.label('PAPER RISK CONTROLS'))
        limits = QLabel('1% approximate risk per trade\n20% max allocation / position\n0.10% fee each way\n0.05% adverse slippage\nLong-only spot simulation\nNo leverage / no real orders')
        limits.setWordWrap(True)
        limits.setStyleSheet('color: #b4c4d9; line-height: 1.5;')
        r.addWidget(limits)
        r.addSpacing(20)
        r.addWidget(self.label('AUTOMATED STOPS / TARGETS'))
        hint = QLabel('• SL: ATR + recent swing low\n• TP: 2× defined stop distance\n• Stops shown on each chart\n• Conservative stop-first tie\n• Checked while app runs')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #a7bad3;')
        r.addWidget(hint)
        r.addSpacing(20)
        r.addWidget(self.label('MOST RECENT SIGNAL'))
        self.recent_signal = QLabel('No qualifying signal yet.\nIndicators do not guarantee accuracy.')
        self.recent_signal.setWordWrap(True)
        self.recent_signal.setStyleSheet('color: #e8c58e;')
        r.addWidget(self.recent_signal)
        r.addStretch()
        close_button = QPushButton('Close all paper positions')
        close_button.setObjectName('stop')
        close_button.clicked.connect(self.close_all)
        r.addWidget(close_button)
        caution = QLabel('RESEARCH SOFTWARE · PAPER ONLY\nA running application and continuous network access are required. Not a financial recommendation.')
        caution.setWordWrap(True)
        caution.setStyleSheet('color: #8499b5; font-size: 10px;')
        r.addWidget(caution)
        splitter.addWidget(right)
        splitter.setSizes([265, 1000, 260])
        self.statusBar().showMessage('Ready • automatic order placement is disabled by default')

    def metric(self, row, name, value):
        frame = QFrame()
        frame.setObjectName('metric')
        v = QVBoxLayout(frame)
        v.setContentsMargins(15, 8, 15, 8)
        l = self.label(name, 'metricLabel')
        val = self.label(value, 'metricValue')
        v.addWidget(l)
        v.addWidget(val)
        row.addWidget(frame, 1)
        return val

    def table(self, columns):
        t = QTableWidget(0, len(columns))
        t.setHorizontalHeaderLabels(columns)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return t

    def add_watch_item(self, symbol, checked=False):
        item = QListWidgetItem(symbol)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.watchlist.addItem(item)

    def selected(self):
        return [self.watchlist.item(i).text() for i in range(self.watchlist.count())
                if self.watchlist.item(i).checkState() == Qt.CheckState.Checked]

    def add_custom(self):
        text = self.symbol_input.text().upper().strip().replace(' ', '')
        if '/' not in text or len(text.split('/')) != 2:
            QMessageBox.information(self, 'Pair format', 'Use BASE/QUOTE, for example TRX/USD.')
            return
        if any(self.watchlist.item(i).text() == text for i in range(self.watchlist.count())):
            QMessageBox.information(self, 'Already added', 'This pair is already on the watchlist.')
            return
        self.add_watch_item(text, True)
        self.symbol_input.clear()
        self.build_chart_grid()
        self.scan()

    def build_chart_grid(self, *args):
        if not hasattr(self, 'chart_splitter'):
            return
        while self.chart_splitter.count():
            old = self.chart_splitter.widget(0)
            old.setParent(None)
            old.deleteLater()
        self.chart_cards.clear()
        symbols = self.selected()
        if not symbols:
            placeholder = QLabel('Check one or more crypto pairs to display charts.')
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setMinimumHeight(300)
            self.chart_splitter.addWidget(placeholder)
            return
        for n in range(0, len(symbols), 2):
            row = QSplitter(Qt.Orientation.Horizontal)
            row.setHandleWidth(8)
            row.setChildrenCollapsible(False)
            row.setMinimumHeight(310)
            for sym in symbols[n:n+2]:
                card = ChartCard(sym)
                self.chart_cards[sym] = card
                row.addWidget(card)
                if sym in self.bars:
                    card.update_chart(self.bars[sym], self.timeframe.currentText(),
                                      self.indicators.get(sym),
                                      self.position_for(sym), self.signals.get(sym))
            self.chart_splitter.addWidget(row)
        self.chart_splitter.setSizes([400] * ((len(symbols) + 1) // 2))

    def position_for(self, symbol):
        return next((p for p in self.paper.positions() if p.symbol == symbol), None)

    def change_horizon(self, text):
        self.timeframe.setCurrentText({'Scalping': '5m', 'Day trading': '1h',
                                       'Swing / long-term': '1d'}[text])

    def change_timeframe(self, *_):
        self.bars.clear()
        self.indicators.clear()
        self.signals.clear()
        self.build_chart_grid()
        self.scan()

    def strategy_changed(self, text):
        self.strategy_info.setText(STRATEGIES[text])
        self.signals.clear()
        self.scan()

    def source_changed(self, *_):
        # Isolate synthetic paper funds from Kraken-priced paper funds.
        self.paper = self.kraken_account if self.source.currentIndex() == 1 else self.demo_account
        if self.auto_enabled:
            self.auto_enabled = False
            self.auto_button.setText('▶  Start paper robot')
            self.auto_button.setObjectName('primary')
            self.auto_button.style().unpolish(self.auto_button)
            self.auto_button.style().polish(self.auto_button)
            self.robot_state.setText('ROBOT IDLE')
            self.robot_state.setStyleSheet('color: #a2b4cf; font-weight: bold;')
        self.last_prices.clear()
        self.load_tables()
        self.show_balance()
        self.bars.clear()
        self.indicators.clear()
        self.signals.clear()
        self.build_chart_grid()
        self.scan()

    def toggle_robot(self):
        if not self.selected():
            QMessageBox.warning(self, 'Select markets', 'Select at least one trading pair.')
            return
        self.auto_enabled = not self.auto_enabled
        self.auto_button.setText('■  Pause paper robot' if self.auto_enabled else '▶  Start paper robot')
        self.auto_button.setObjectName('stop' if self.auto_enabled else 'primary')
        self.auto_button.style().unpolish(self.auto_button)
        self.auto_button.style().polish(self.auto_button)
        self.robot_state.setText('●  PAPER ROBOT ON' if self.auto_enabled else 'ROBOT IDLE')
        self.robot_state.setStyleSheet(f'color: {UP if self.auto_enabled else "#a2b4cf"}; font-weight: bold;')
        self.log('Paper robot started: signals execute on NEW completed candles only.'
                 if self.auto_enabled else 'Paper robot paused: automatic entries stopped; stop/target checks continue.')
        self.scan()

    def scan(self):
        if self.worker is not None and self.worker.isRunning():
            return
        # Active paper positions must keep being monitored even if unchecked
        # in the visible chart watchlist.
        symbols = list(dict.fromkeys(self.selected() + [p.symbol for p in self.paper.positions()]))
        if not symbols:
            return
        self.scan_button.setEnabled(False)
        self.statusBar().showMessage('Loading candles / analyzing watchlist ...')
        self.worker = FetchWorker(symbols, self.timeframe.currentText(),
                                  'Kraken live' if self.source.currentIndex() == 1 else 'Simulated')
        self.worker.ready.connect(self.apply_market)
        self.worker.finished.connect(lambda: self.scan_button.setEnabled(True))
        self.worker.start()

    def apply_market(self, payload):
        timeframe, source, results, errors = payload
        wanted_source = 'Kraken live' if self.source.currentIndex() == 1 else 'Simulated'
        if timeframe != self.timeframe.currentText() or source != wanted_source:
            return
        for sym, candles in results.items():
            if source == 'Kraken live' and time.time() - candles[-1].ts > (TIMEFRAME_SECONDS[timeframe] * 2 + 30):
                errors[sym] = 'Stale market candles; paper robot entry/exit skipped for safety.'
                continue
            self.bars[sym] = candles
            self.last_prices[sym] = candles[-1].close
            for p, pnl, reason in self.paper.check_exits(sym, candles):
                self.log(f'PAPER EXIT {sym}: {reason} · net P&L ${pnl:,.2f}', beep=True)
            try:
                idea, indicators = evaluate(sym, candles, self.strategy.currentText())
            except Exception as e:
                errors[sym] = f'Indicator error: {e}'
                continue
            self.indicators[sym] = indicators
            self.signals[sym] = idea
            if idea is not None:
                # First sight of a qualifying CLOSED bar is eligible; no retroactive
                # execution when toggling the robot later in that same bar.
                first = self.paper.unique_signal(sym, timeframe, idea.strategy, idea.ts)
                if first:
                    self.recent_signal.setText(f'{sym}   BUY idea\n{idea.reason}\nEntry reference: ${idea.entry_ref:,.4f}\nSL: ${idea.stop:,.4f}   TP: ${idea.target:,.4f}')
                    self.log(f'BUY idea {sym} [{timeframe} / {idea.strategy}]: {idea.reason}', beep=True)
                    if self.auto_enabled:
                        p = self.paper.open(idea, candles[-1].close, candles[-1].ts, self.last_prices)
                        if p:
                            self.log(f'PAPER BUY {sym}: {p.qty:.6g} @ ${p.entry:,.5f}; SL ${p.sl:,.5f}; TP ${p.tp:,.5f}', beep=True)
                        else:
                            self.log(f'{sym} paper entry skipped (risk, cash, existing position or stale price).')
            if sym in self.chart_cards:
                self.chart_cards[sym].update_chart(candles, timeframe, indicators,
                                                    self.position_for(sym), idea)
        for sym, error in errors.items():
            self.log(f'Data unavailable for {sym}: {error}')
        if source == 'Kraken live':
            healthy = bool(results) and not errors
            self.market_state.setText('●  LIVE KRAKEN PUBLIC DATA' if healthy else '●  MARKET DATA ERROR')
            self.market_state.setStyleSheet(f'color: {UP if healthy else DOWN}; font-weight: bold;')
        else:
            self.market_state.setText('●  SIMULATED MARKET DATA')
            self.market_state.setStyleSheet('color: #e3ba76; font-weight: bold;')
        self.load_tables()
        self.show_balance()
        self.statusBar().showMessage(f'{len(results)} market(s) refreshed · {len(errors)} error(s) · {dt.datetime.now(dt.timezone.utc):%H:%M:%S} UTC')

    def show_balance(self):
        self.cash_metric.setText(f'${self.paper.cash:,.2f}')
        self.equity_metric.setText(f'${self.paper.equity(self.last_prices):,.2f}')
        self.positions_metric.setText(str(len(self.paper.positions())))
        pnl = sum(h['pnl'] for h in self.paper.history(100000))
        self.pnl_metric.setText(f'{pnl:+,.2f} USD')
        self.pnl_metric.setStyleSheet(f'color: {UP if pnl >= 0 else DOWN}; font-size:22px; font-weight:750;')

    def load_tables(self):
        positions = self.paper.positions()
        self.position_table.setRowCount(len(positions))
        for row, p in enumerate(positions):
            last = self.last_prices.get(p.symbol, p.entry)
            unrealized = (last - p.entry) * p.qty - p.entry_fee - last * p.qty * 0.001
            items = [p.symbol, f'{p.entry:,.5f}', f'{last:,.5f}', f'{p.qty:.6g}',
                     f'{p.sl:,.5f}', f'{p.tp:,.5f}', f'{unrealized:+,.2f}']
            for col, txt in enumerate(items):
                cell = QTableWidgetItem(txt)
                if col == 6:
                    cell.setForeground(QColor(UP if unrealized >= 0 else DOWN))
                self.position_table.setItem(row, col, cell)
        history = self.paper.history()
        self.history_table.setRowCount(len(history))
        for row, h in enumerate(history):
            items = [dt.datetime.fromtimestamp(h['closed'], dt.timezone.utc).strftime('%Y-%m-%d %H:%M'),
                     h['symbol'], h['strategy'], f'{h["entry"]:,.5f}',
                     f'{h["exit"]:,.5f}', f'{h["qty"]:.6g}', f'{h["pnl"]:+,.2f}', h['reason']]
            for col, txt in enumerate(items):
                cell = QTableWidgetItem(txt)
                if col == 6:
                    cell.setForeground(QColor(UP if h['pnl'] >= 0 else DOWN))
                self.history_table.setItem(row, col, cell)

    def log(self, message, beep=False):
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        self.log_lines.append(f'[{stamp}]  {message}')
        self.log_lines = self.log_lines[-350:]
        self.activity.setPlainText('\n'.join(self.log_lines))
        self.activity.moveCursor(QTextCursor.MoveOperation.End)
        if beep and self.alerts.isChecked():
            QApplication.beep()

    def close_all(self):
        positions = self.paper.positions()
        if not positions:
            QMessageBox.information(self, 'No positions', 'There are no open paper positions.')
            return
        answer = QMessageBox.question(self, 'Close paper positions', f'Simulate closing all {len(positions)} open positions at their latest displayed prices?')
        if answer != QMessageBox.StandardButton.Yes:
            return
        for p in positions:
            if p.symbol not in self.last_prices:
                self.log(f'Skipped {p.symbol}: no current price available.')
                continue
            pnl = self.paper.close(p.id, self.last_prices[p.symbol], 'Manual close all')
            self.log(f'MANUAL PAPER EXIT {p.symbol}: net P&L ${pnl:,.2f}')
        self.load_tables()
        self.show_balance()
        for sym, card in self.chart_cards.items():
            if sym in self.bars:
                card.update_chart(self.bars[sym], self.timeframe.currentText(),
                                  self.indicators.get(sym), self.position_for(sym), self.signals.get(sym))

    def reset_paper(self):
        if QMessageBox.warning(self, 'Reset paper account',
                               'Delete ALL paper positions, signals and trade history? Starting virtual cash will be reset to $10,000.',
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                               QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        self.auto_enabled = False
        self.auto_button.setText('▶  Start paper robot')
        self.auto_button.setObjectName('primary')
        self.auto_button.style().unpolish(self.auto_button)
        self.auto_button.style().polish(self.auto_button)
        self.robot_state.setText('ROBOT IDLE')
        self.robot_state.setStyleSheet('color: #a2b4cf; font-weight: bold;')
        self.paper.reset()
        self.load_tables()
        self.show_balance()
        self.log('Paper account reset to $10,000. All historical signals and trades cleared.')
        for sym, card in self.chart_cards.items():
            if sym in self.bars:
                card.update_chart(self.bars[sym], self.timeframe.currentText(),
                                  self.indicators.get(sym), None, self.signals.get(sym))

    def show_exchange_info(self):
        QMessageBox.information(self, 'Live exchange execution is not yet implemented',
                                'Current version: Kraken public market prices + paper trades only.\n\n'
                                'Exchange API keys, sandbox orders, real-money orders, and exchange-side SL/TP are NOT enabled.\n\n'
                                'Before live activation we need exchange selection, keychain storage, permission checks, sandbox reconciliation, hard risk limits, emergency-stop controls and extensive testing.\n\n'
                                'Never paste API secrets into an unverified application.')

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait()  # Don't destroy an active QThread.
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName('Atlas')
    app.setApplicationName('AtlasTrader')
    app.setStyle('Fusion')
    app.setStyleSheet(APP_STYLE)
    window = AtlasWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
