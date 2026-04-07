"""
GastosApp — Control Personal de Gastos
=======================================
Entry point. Run with:
    python main.py

Requirements:
    pip install -r requirements.txt

To build an executable:
    pip install pyinstaller
    pyinstaller --onefile --windowed --name GastosApp main.py
"""

import sys
import os

# Make sure the app directory is on sys.path when running from a frozen .exe
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))

from app import GastosApp


def main():
    app = GastosApp()
    app.mainloop()


if __name__ == '__main__':
    main()
