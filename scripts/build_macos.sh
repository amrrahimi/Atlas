#!/usr/bin/env bash
# Run on macOS; native macOS builds cannot be created from Linux.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pip install -e .
pyinstaller --noconfirm --windowed --name AtlasTrader --collect-all pyqtgraph --collect-all ccxt --paths src launcher.py
echo 'Output: dist/AtlasTrader.app'
