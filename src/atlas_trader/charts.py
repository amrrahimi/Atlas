"""Resizable interactive Qt/pyqtgraph candlesticks and annotated positions."""
from __future__ import annotations
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPicture
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QHBoxLayout
import pyqtgraph as pg
from .market import TIMEFRAME_SECONDS

UP = '#28d4a0'
DOWN = '#f16f7f'


class Candles(pg.GraphicsObject):
    def __init__(self, bars, bar_seconds):
        super().__init__()
        self.picture = QPicture()
        width = bar_seconds * .30
        painter = QPainter(self.picture)
        for b in bars:
            color = UP if b.close >= b.open else DOWN
            painter.setPen(pg.mkPen(color, width=1))
            painter.drawLine(QPointF(b.ts, b.low), QPointF(b.ts, b.high))
            painter.setBrush(pg.mkBrush(color))
            painter.setPen(pg.mkPen(color, width=1))
            rect = QRectF(b.ts - width, min(b.open, b.close),
                          2 * width, max(abs(b.close - b.open), b.close * .000035))
            painter.drawRect(rect)
        painter.end()

    def paint(self, painter, option, widget=None):
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QRectF(self.picture.boundingRect())


class ChartCard(QFrame):
    def __init__(self, symbol):
        super().__init__()
        self.symbol = symbol
        self.setObjectName('chartCard')
        self.setMinimumSize(300, 310)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 12, 13, 10)
        header = QHBoxLayout()
        self.name = QLabel(symbol)
        self.name.setObjectName('chartName')
        self.price = QLabel('Waiting for candles...')
        self.price.setObjectName('chartPrice')
        header.addWidget(self.name)
        header.addStretch()
        header.addWidget(self.price)
        layout.addLayout(header)
        self.plot = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})
        self.plot.setBackground('#121a2a')
        self.plot.showGrid(x=True, y=True, alpha=.15)
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot.getPlotItem().hideButtons()
        self.plot.getAxis('left').setPen(pg.mkPen('#39465e'))
        self.plot.getAxis('bottom').setPen(pg.mkPen('#39465e'))
        self.plot.getAxis('left').setTextPen(pg.mkPen('#aab7ca'))
        self.plot.getAxis('bottom').setTextPen(pg.mkPen('#aab7ca'))
        self.plot.setMenuEnabled(False)
        layout.addWidget(self.plot, 1)
        self.initialized = False

    def update_chart(self, bars, timeframe, indicator_values=None, position=None, signal=None):
        if not bars:
            return
        sec = TIMEFRAME_SECONDS[timeframe]
        self.price.setText(f'${bars[-1].close:,.6f}' if bars[-1].close < 10 else f'${bars[-1].close:,.2f}')
        previous_range = None
        if self.initialized:
            previous_range = self.plot.getViewBox().viewRange()[0]
        self.plot.clear()
        self.plot.addItem(Candles(bars, sec))
        if indicator_values:
            times = [x.ts for x in bars]
            for key, color in [('ema20', '#d0a6ff'), ('ema50', '#48b8f5')]:
                self.plot.plot(times, indicator_values[key], pen=pg.mkPen(color, width=1.5), connect='finite')
        last = bars[-1]
        marker = pg.InfiniteLine(pos=last.close, angle=0, pen=pg.mkPen('#8c9cb8', width=1, style=Qt.PenStyle.DashLine))
        self.plot.addItem(marker)
        if position is not None:
            self._level(position.entry, '#e1edf8', 'ENTRY')
            self._level(position.sl, DOWN, 'SL')
            self._level(position.tp, UP, 'TP')
            self.plot.plot([position.bar_ts], [position.entry], pen=None,
                           symbol='t1', symbolSize=16, symbolBrush=pg.mkBrush(UP))
        elif signal is not None:
            self._level(signal.stop, DOWN, 'IDEA SL')
            self._level(signal.target, UP, 'IDEA TP')
            self.plot.plot([signal.ts], [signal.entry_ref], pen=None,
                           symbol='t1', symbolSize=12, symbolBrush=pg.mkBrush('#eecb72'))
        if previous_range:
            self.plot.setXRange(*previous_range, padding=0)
        else:
            self.plot.setXRange(bars[max(0, len(bars) - 85)].ts,
                                last.ts + 5 * sec, padding=0)
            self.initialized = True
        self.plot.enableAutoRange(axis='y', enable=True)

    def _level(self, value, color, name):
        line = pg.InfiniteLine(pos=value, angle=0,
                               pen=pg.mkPen(color, width=1.7, style=Qt.PenStyle.DashLine),
                               label=f' {name} {value:.5g} ',
                               labelOpts={'position': .91, 'color': color,
                                          'fill': pg.mkBrush('#121a2a')})
        self.plot.addItem(line)
