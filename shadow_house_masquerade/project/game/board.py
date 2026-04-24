"""
game/board.py
--------------
The Board holds all shared state for a round:
    * the ordered list of Players
    * the draw pile (remaining cards not yet dealt)
    * the index of whose turn it is
    * who currently holds the handcuffs token
    * the round number (purely cosmetic)

It does NOT resolve card effects — that responsibility lives in
``game.logic.GameLogic``. The Board only tracks positions and provides
the low-level primitives (draw a card, advance the turn, etc.).
"""

from __future__ import annotations

import random
from typing import List, Optional

from game.player import Player
from utils.helpers import HAND_SIZE, build_round_deck


class Board:
    """Shared state container for a single round."""

    def __init__(self, players: List[Player]) -> None:
        if not players:
            raise ValueError("Board requires at least one player")
        self.players: List[Player] = players
        self.draw_pile: List[str] = []
        self.current_turn_index: int = 0
        self.handcuffs_holder: Optional[int] = None  # index into self.players
        self.round_number: int = 0
        self.round_started: bool = False

    # ------------------------------------------------------------------
    # Round setup
    # ------------------------------------------------------------------
    def setup_new_round(self) -> None:
        """Prepare a fresh deck, deal hands, reset per-round flags."""
        self.round_number += 1
        self.round_started = False
        self.handcuffs_holder = None

        for p in self.players:
            p.reset_for_new_round()

        # Build and shuffle deck
        deck = build_round_deck(len(self.players))
        random.shuffle(deck)

        # Deal HAND_SIZE cards to each player
        for _ in range(HAND_SIZE):
            for p in self.players:
                if deck:
                    p.add_card(deck.pop())

        # Remaining cards become the face-down draw pile
        self.draw_pile = deck

        # First on the Scene always plays first — find the holder.
        from utils.helpers import FIRST_ON_SCENE
        self.current_turn_index = 0
        for i, p in enumerate(self.players):
            if FIRST_ON_SCENE in p.hand:
                self.current_turn_index = i
                break

    # ------------------------------------------------------------------
    # Turn management
    # ------------------------------------------------------------------
    def current_player(self) -> Player:
        return self.players[self.current_turn_index]

    def advance_turn(self) -> Player:
        """Move to the next player in clockwise order and return them."""
        self.current_turn_index = (self.current_turn_index + 1) % len(self.players)
        # Expiring protections: they only apply UNTIL the protected player's
        # next turn, so when play comes back round, clear them.
        cur = self.current_player()
        cur.servant_protection = False
        cur.housekeeper_protection = False
        return cur

    def player_to_left_of(self, player: Player) -> Player:
        i = self.players.index(player)
        return self.players[(i + 1) % len(self.players)]

    def player_to_right_of(self, player: Player) -> Player:
        i = self.players.index(player)
        return self.players[(i - 1) % len(self.players)]

    # ------------------------------------------------------------------
    # Draw pile
    # ------------------------------------------------------------------
    def draw_card(self) -> Optional[str]:
        """Return the top card of the draw pile, or None if empty."""
        if not self.draw_pile:
            return None
        return self.draw_pile.pop()

    def discard_to_pile(self, card_type: str) -> None:
        """Return a card to the draw pile (placed at the bottom, shuffled)."""
        self.draw_pile.insert(0, card_type)
        # Light shuffle so position isn't predictable
        random.shuffle(self.draw_pile)

    # ------------------------------------------------------------------
    # Handcuffs token
    # ------------------------------------------------------------------
    def give_handcuffs_to(self, target: Player) -> None:
        # Remove from previous holder
        if self.handcuffs_holder is not None:
            self.players[self.handcuffs_holder].has_handcuffs = False
        idx = self.players.index(target)
        self.handcuffs_holder = idx
        target.has_handcuffs = True

    def handcuffs_on_player(self) -> Optional[Player]:
        if self.handcuffs_holder is None:
            return None
        return self.players[self.handcuffs_holder]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "players": [p.to_dict() for p in self.players],
            "draw_pile": list(self.draw_pile),
            "current_turn_index": self.current_turn_index,
            "handcuffs_holder": self.handcuffs_holder,
            "round_number": self.round_number,
            "round_started": self.round_started,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Board":
        players = [Player.from_dict(p) for p in data["players"]]
        board = cls(players)
        board.draw_pile = list(data.get("draw_pile", []))
        board.current_turn_index = int(data.get("current_turn_index", 0))
        holder = data.get("handcuffs_holder")
        board.handcuffs_holder = None if holder is None else int(holder)
        if board.handcuffs_holder is not None:
            board.players[board.handcuffs_holder].has_handcuffs = True
        board.round_number = int(data.get("round_number", 0))
        board.round_started = bool(data.get("round_started", False))
        return board
