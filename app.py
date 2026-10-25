"""Windowed entry point -> CHAMBER.exe (no console)."""
import multiprocessing as mp, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from chamber.gui import main

if __name__ == "__main__":
    mp.freeze_support()
    main()
