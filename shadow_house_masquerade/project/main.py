"""
main.py
--------
Entry point for the Shadow House Masquerade digital board game.

Run with::

    python main.py

The program launches a Tkinter window. From the main menu you can start
a new game (3-8 players, pass-and-play), resume a saved game, view
statistics, or consult the 'How to Play' summary.

Project layout::

    project/
    ├── main.py              <- you are here
    ├── requirements.txt
    ├── game/
    │   ├── logic.py         rules engine / card effects / scoring
    │   ├── player.py        Player data model
    │   └── board.py         shared round state (deck, turn, handcuffs)
    ├── gui/
    │   └── ui.py            Tkinter user interface
    ├── data/
    │   └── storage.py       JSON persistence (stats / history / save)
    └── utils/
        └── helpers.py       card constants, setup table, helpers
"""

from __future__ import annotations

import sys
import traceback


def main() -> int:
    try:
        # Imported here so import-time errors show nicely in a console instead
        # of crashing at module load.
        from gui.ui import launch
    except ImportError as exc:  # pragma: no cover
        print(
            "Failed to import GUI module. "
            "Make sure you run this from the project root and that Tkinter "
            "is available in your Python environment.\n",
            exc,
            file=sys.stderr,
        )
        return 2

    try:
        launch()
    except Exception:  # pragma: no cover - unexpected runtime error
        print("An unexpected error occurred:", file=sys.stderr)
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
