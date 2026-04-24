# Shadow House Masquerade — Digital Board Game

A Python / Tkinter digital recreation of **Shadow House Masquerade**
(Blue Orange / EmperorS4, 2024), a 3-8 player social-deduction card
game.

> *"The night sky is bathed in moonlight, and you have been invited to
> dinner with aristocrats at a lavish manor house. Suddenly, an
> anguished cry rings out: **Aaaaahhh! Viscount Shadow is dead!!!**"*

## Quick start

```bash
# 1. Create & activate a virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 2. (No pip install required — this project uses only the stdlib.)
pip install -r requirements.txt

# 3. Run the game (from the project root)
python main.py
```

On Debian/Ubuntu, if Tkinter is missing:

```bash
sudo apt-get install python3-tk
```

## Project structure

```
project/
├── main.py                 # Application entry point
├── requirements.txt        # Dependency list (stdlib only)
├── README.md               # This file
│
├── game/                   # Rules engine (no GUI, no I/O)
│   ├── __init__.py
│   ├── logic.py            # Card effects, scoring, round end
│   ├── player.py           # Player model
│   └── board.py            # Shared round state
│
├── gui/                    # Tkinter UI (all screens)
│   ├── __init__.py
│   └── ui.py
│
├── data/                   # JSON persistence layer
│   ├── __init__.py
│   └── storage.py
│
└── utils/                  # Constants, card table, helpers
    ├── __init__.py
    └── helpers.py
```

## How the game plays on one device

Shadow House Masquerade is a hidden-information game, so this digital
adaptation uses a **pass-and-play** flow:

1. The app announces whose turn it is (`"Pass the device to Alice"`).
2. Alice confirms she is the only one looking.
3. Alice sees her hand and picks a card. Targeted effects (Detective
   questioning, Toby revealing, Accomplice forcing a discard, etc.)
   prompt her for a target via a modal dialog.
4. Alice plays, the effect resolves, and the app tells her to pass the
   device to the next player.

Private information (a player's hand, a Witness peek, the Culprit's
reveal under "Baby of the Family") is always shown on a dismissable
modal tagged with the viewer's name, never printed on the shared
turn screen.

## Card roster implemented

All 16 card types from the physical game are implemented:

| Character cards | "Other" cards (drawn randomly) |
|---|---|
| First on the Scene | Toby |
| Culprit            | The Baby of the Family |
| Detective          | Share |
| Accomplice         | Rumors |
| Sheriff            | Frenzy!!! |
| Alibi              | Soothsayer, Witness, The Servant, The Housekeeper, Swap |

Setup counts per player count follow the rulebook table exactly
(see `utils/helpers.py :: SETUP_TABLE`).

## End-of-round scenarios

| # | Trigger | Rewards |
|---|---|---|
| 1 | Detective correctly names the Culprit | Detective +2; other non-accomplices +1 |
| 2 | Toby exposes the Culprit | Toby +3; other non-accomplices +1 |
| 3 | Culprit plays / is forced to discard their last card | Culprit + accomplices +2 each |
| 4 | Handcuffs holder reveals and it's the Culprit | Everyone except Culprit/accomplices +1 |

First player to **5 points** wins the whole game. Ties share victory.

## Persistence (JSON file storage)

All data lives under `~/.shadow_house_masquerade/` (created on first
run). Three files:

- `stats.json` — per-player aggregate statistics (games / wins /
  total points)
- `history.json` — last 50 completed rounds, with timestamps and reasons
- `save.json` — a single slot for a suspended game (created by the
  "Save & exit to menu" button, consumed by "Resume Saved Game")

No third-party databases, no SQL. Clean file-based storage.

## Design notes

- **Layer separation.** `game/` never imports anything from `gui/` or
  `data/`. The logic engine communicates with the GUI via the
  `EffectCallbacks` protocol (see `game/logic.py`), so the rules are
  unit-testable without a Tk display.
- **No globals / singletons.** Every class takes its dependencies via
  its constructor.
- **Defensive I/O.** Any read from a JSON file returns a sensible
  default on corruption so the app never crashes over a bad save.
- **Exception safety.** Illegal plays raise a typed `IllegalPlay`
  exception that the GUI turns into a friendly dialog.

## Credits

Game design: *Pesu Nabeno* · Illustrations: *EmperorS4* ·
©2024 Blue Orange Edition · ©2023 EmperorS4.
This digital adaptation is for an academic course project (CS Python
coursework). All trademarks belong to their respective owners.
