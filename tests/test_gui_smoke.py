"""Optional smoke test, exercised on macOS/Windows CI after Qt is installed."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('pyqtgraph')
from PySide6.QtWidgets import QApplication
from atlas_trader.app import AtlasWindow


def test_qt_window_creation():
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName('AtlasTraderTests')
    app.setApplicationName('AtlasTraderSmoke')
    win = AtlasWindow()
    assert win.watchlist.count() >= 10
    assert len(win.chart_cards) == 2
    assert win.paper.cash >= 0
    assert win.auto_enabled is False
    assert win.source.currentText() == 'Simulated (offline)'
    win.close()
