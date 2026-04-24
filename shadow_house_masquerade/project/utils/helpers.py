"""
utils/helpers.py
-----------------
Constants, card definitions, setup tables, and small helper
functions for the Shadow House Masquerade digital board game.

Nothing in this module depends on Tkinter or the game state, so it
can be freely imported anywhere.
"""

from __future__ import annotations

import random
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Card type identifiers (used as internal keys throughout the project)
# ---------------------------------------------------------------------------
FIRST_ON_SCENE = "first_on_scene"
CULPRIT = "culprit"
DETECTIVE = "detective"
ACCOMPLICE = "accomplice"
SHERIFF = "sheriff"
ALIBI = "alibi"
TOBY = "toby"
BABY = "baby_of_family"
SHARE = "share"
RUMORS = "rumors"
FRENZY = "frenzy"
SOOTHSAYER = "soothsayer"
WITNESS = "witness"
SERVANT = "servant"
HOUSEKEEPER = "housekeeper"
SWAP = "swap"

# ---------------------------------------------------------------------------
# Display names shown to the user
# ---------------------------------------------------------------------------
CARD_NAMES: Dict[str, str] = {
    FIRST_ON_SCENE: "First on the Scene",
    CULPRIT: "Culprit",
    DETECTIVE: "Detective",
    ACCOMPLICE: "Accomplice",
    SHERIFF: "Sheriff",
    ALIBI: "Alibi",
    TOBY: "Toby",
    BABY: "The Baby of the Family",
    SHARE: "Share",
    RUMORS: "Rumors",
    FRENZY: "Frenzy!!!",
    SOOTHSAYER: "Soothsayer",
    WITNESS: "Witness",
    SERVANT: "The Servant",
    HOUSEKEEPER: "The Housekeeper",
    SWAP: "Swap",
}

# ---------------------------------------------------------------------------
# Short rule reminders displayed alongside each card in the UI
# ---------------------------------------------------------------------------
CARD_DESCRIPTIONS: Dict[str, str] = {
    FIRST_ON_SCENE: "You're the first player. Starts the round.",
    CULPRIT: "Only play/discard when it is the LAST card in your hand to win.",
    DETECTIVE: "Ask a player 'Are you the culprit?' If yes AND no Alibi held, you win.",
    ACCOMPLICE: "You become an accomplice. Force a chosen player to discard a card face up.",
    SHERIFF: "Give the handcuffs token to another player.",
    ALIBI: "Makes the culprit lie to the Detective. No effect when played.",
    TOBY: "Force a player to reveal a card from their hand. If Culprit — you win.",
    BABY: "Everyone closes eyes, culprit opens, everyone reopens.",
    SHARE: "Every player passes one chosen card to the player on their LEFT.",
    RUMORS: "Every player draws a random card from the player on their RIGHT.",
    FRENZY: "Each player gives one card; all are shuffled and re-dealt.",
    SOOTHSAYER: "Share your thoughts (accusations / suspicions) with everyone.",
    WITNESS: "Secretly view a player's hand. If suspicious you MAY swap one card.",
    SERVANT: "The Detective cannot question you until your NEXT turn.",
    HOUSEKEEPER: "Toby and the Sheriff cannot target you until your NEXT turn.",
    SWAP: "Swap a card with a chosen player. They choose which card they give you.",
}

# ---------------------------------------------------------------------------
# Setup table (from the rulebook, page 2)
# Index: player_count -> (first, culprit, detective, accomplice, sheriff, alibi, other)
# ---------------------------------------------------------------------------
SETUP_TABLE: Dict[int, Tuple[int, int, int, int, int, int, int]] = {
    3: (1, 1, 1, 0, 1, 1, 7),
    4: (1, 1, 1, 1, 1, 1, 10),
    5: (1, 1, 1, 1, 1, 2, 13),
    6: (1, 1, 2, 2, 1, 2, 15),
    7: (1, 1, 2, 2, 1, 3, 18),
    8: (1, 1, 2, 2, 1, 3, 22),
}

MIN_PLAYERS = 3
MAX_PLAYERS = 8
HAND_SIZE = 4               # each player gets 4 cards
WIN_THRESHOLD = 5           # total points required to end the whole game

# ---------------------------------------------------------------------------
# Pool of 26 "other" cards (shuffled during setup, then drawn as needed).
# The total physical deck in the real game has 36 cards; with the max of 10
# character cards at 8 players, up to 26 other cards are available (22 are
# dealt, the remaining 4 sit as a face-down draw pile).
# ---------------------------------------------------------------------------
OTHER_CARDS_POOL: List[str] = (
    [TOBY] * 3
    + [BABY] * 2
    + [SHARE] * 3
    + [RUMORS] * 3
    + [FRENZY] * 2
    + [SOOTHSAYER] * 3
    + [WITNESS] * 3
    + [SERVANT] * 3
    + [HOUSEKEEPER] * 2
    + [SWAP] * 2
)  # 26 cards total

# Cards that require a specific target player when played
TARGETED_CARDS = {DETECTIVE, ACCOMPLICE, SHERIFF, TOBY, WITNESS, SWAP}

# Cards that may only legally be played as the last card in the hand
LAST_CARD_ONLY = {CULPRIT}


def build_round_deck(num_players: int) -> List[str]:
    """
    Build the full deck for a round according to the setup table.

    Returns a list of card-type keys (strings). Order is NOT yet shuffled by
    this function — callers should shuffle before dealing.
    """
    if num_players not in SETUP_TABLE:
        raise ValueError(
            f"Number of players must be between {MIN_PLAYERS} and {MAX_PLAYERS}"
        )

    first, culprit, detective, accomplice, sheriff, alibi, other = SETUP_TABLE[
        num_players
    ]

    # Starter deck — fixed character cards
    deck: List[str] = (
        [FIRST_ON_SCENE] * first
        + [CULPRIT] * culprit
        + [DETECTIVE] * detective
        + [ACCOMPLICE] * accomplice
        + [SHERIFF] * sheriff
        + [ALIBI] * alibi
    )

    # Additional deck — sampled at random from the other-cards pool
    pool = OTHER_CARDS_POOL.copy()
    random.shuffle(pool)
    deck.extend(pool[:other])
    return deck


def describe_card(card_type: str) -> str:
    """Return a short human-readable description for any card type."""
    name = CARD_NAMES.get(card_type, card_type)
    desc = CARD_DESCRIPTIONS.get(card_type, "")
    return f"{name} — {desc}"


def format_hand(hand: List[str]) -> str:
    """Return a readable multi-line description of a hand."""
    if not hand:
        return "(empty hand)"
    return "\n".join(f"  • {describe_card(c)}" for c in hand)
