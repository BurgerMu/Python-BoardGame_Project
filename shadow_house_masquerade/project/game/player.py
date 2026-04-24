"""
game/player.py
---------------
Player model for Shadow House Masquerade.

A Player knows:
    * their name
    * the cards currently in their hand (private)
    * the cards they have already played (public, face-up in front of them)
    * their total points (tokens in front of them)
    * transient per-round flags such as `is_accomplice`, `servant_protection`,
      `housekeeper_protection` and whether they hold the handcuffs token.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from utils.helpers import (
    ACCOMPLICE,
    CULPRIT,
    SERVANT,
    HOUSEKEEPER,
    ALIBI,
    CARD_NAMES,
)


@dataclass
class Player:
    """A single participant in a game round."""

    name: str
    hand: List[str] = field(default_factory=list)
    played: List[str] = field(default_factory=list)
    points: int = 0

    # Per-round flags -------------------------------------------------
    is_accomplice: bool = False         # set once they play an Accomplice card
    has_handcuffs: bool = False         # receives handcuffs token from Sheriff
    servant_protection: bool = False    # immune to Detective this round only
    housekeeper_protection: bool = False  # immune to Toby/Sheriff this round

    # ----- Hand helpers ---------------------------------------------
    def hand_size(self) -> int:
        return len(self.hand)

    def has_card(self, card_type: str) -> bool:
        return card_type in self.hand

    def add_card(self, card_type: str) -> None:
        self.hand.append(card_type)

    def remove_card(self, card_type: str) -> str:
        """Remove ``card_type`` from the hand and return it."""
        if card_type not in self.hand:
            raise ValueError(f"{self.name} does not have card '{card_type}'")
        self.hand.remove(card_type)
        return card_type

    # ----- Play / discard -------------------------------------------
    def play_card(self, card_type: str) -> str:
        """Move a card from ``hand`` to ``played`` (face-up)."""
        self.remove_card(card_type)
        self.played.append(card_type)
        # Becoming an accomplice is permanent for the round
        if card_type == ACCOMPLICE:
            self.is_accomplice = True
        return card_type

    # ----- State inspection -----------------------------------------
    def is_culprit(self) -> bool:
        """Return True if the Culprit card is currently in this player's hand."""
        return CULPRIT in self.hand

    def has_alibi(self) -> bool:
        return ALIBI in self.hand

    def reset_for_new_round(self) -> None:
        """Clear hand / played cards / per-round flags, keep total points."""
        self.hand.clear()
        self.played.clear()
        self.is_accomplice = False
        self.has_handcuffs = False
        self.servant_protection = False
        self.housekeeper_protection = False

    def add_points(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Points awarded cannot be negative")
        self.points += amount

    # ----- Serialization for save files -----------------------------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "hand": list(self.hand),
            "played": list(self.played),
            "points": self.points,
            "is_accomplice": self.is_accomplice,
            "has_handcuffs": self.has_handcuffs,
            "servant_protection": self.servant_protection,
            "housekeeper_protection": self.housekeeper_protection,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        return cls(
            name=data["name"],
            hand=list(data.get("hand", [])),
            played=list(data.get("played", [])),
            points=int(data.get("points", 0)),
            is_accomplice=bool(data.get("is_accomplice", False)),
            has_handcuffs=bool(data.get("has_handcuffs", False)),
            servant_protection=bool(data.get("servant_protection", False)),
            housekeeper_protection=bool(data.get("housekeeper_protection", False)),
        )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"Player(name={self.name!r}, points={self.points}, "
            f"hand={[CARD_NAMES.get(c, c) for c in self.hand]}, "
            f"played={[CARD_NAMES.get(c, c) for c in self.played]})"
        )
