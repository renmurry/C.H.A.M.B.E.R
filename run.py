"""Entry point for PyInstaller / direct execution (python run.py ...)."""
import multiprocessing as mp
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from chamber.cli import main

if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
