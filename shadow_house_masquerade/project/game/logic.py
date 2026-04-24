"""
game/logic.py
--------------
Core game rules for Shadow House Masquerade.

``GameLogic`` is the single source of truth for:
    * legality checks (can this player play this card right now?)
    * card-effect resolution (which typically requires input from the GUI
      layer — hence the use of a small callback interface)
    * detecting end-of-round and computing scores
    * detecting end-of-game

The GUI layer (``gui/ui.py``) supplies a callbacks object implementing
the :class:`EffectCallbacks` protocol so that questions such as "pick a
target player" or "pick a card to discard" can be answered by the user
without this module ever touching Tkinter.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, List, Optional, Protocol

from game.board import Board
from game.player import Player
from utils.helpers import (
    ACCOMPLICE,
    ALIBI,
    BABY,
    CARD_NAMES,
    CULPRIT,
    DETECTIVE,
    FIRST_ON_SCENE,
    FRENZY,
    HOUSEKEEPER,
    RUMORS,
    SERVANT,
    SHARE,
    SHERIFF,
    SOOTHSAYER,
    SWAP,
    TOBY,
    WITNESS,
    WIN_THRESHOLD,
    describe_card,
)


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------
@dataclass
class RoundResult:
    """Describes how a round ended and who scored what."""

    reason: str                         # human-readable summary
    scenario: int                       # 1, 2, 3 or 4 per rulebook
    winners: List[str]                  # names of players who "won" the round
    scores: dict                        # name -> points awarded this round
    culprit_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Callback interface (implemented by the GUI)
# ---------------------------------------------------------------------------
class EffectCallbacks(Protocol):
    """GUI must implement these so the logic layer can ask for input."""

    def choose_player(
        self, actor: Player, prompt: str, eligible: List[Player]
    ) -> Player:
        """Ask *actor* to pick one other player."""

    def choose_card_from_hand(
        self, actor: Player, prompt: str, hand_owner: Player, hand: List[str]
    ) -> str:
        """Ask *actor* to pick one card from *hand_owner*'s hand (by index)."""

    def ask_yes_no(self, actor: Player, prompt: str) -> bool:
        """Simple yes/no question."""

    def show_message(self, title: str, message: str) -> None:
        """Inform all players of something."""

    def show_private_message(self, viewer: Player, title: str, message: str) -> None:
        """Show a message only to *viewer* (pass-device privacy)."""

    def prompt_soothsayer_message(self, actor: Player) -> str:
        """Get free-text accusation from the Soothsayer player."""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class IllegalPlay(Exception):
    """Raised when a player tries to play a card that is not currently legal."""


# ---------------------------------------------------------------------------
# The main engine
# ---------------------------------------------------------------------------
class GameLogic:
    """
    Round / game orchestrator.

    Typical usage by the GUI:

        logic = GameLogic(player_names)
        logic.start_new_round()
        while not logic.round_over:
            cur = logic.current_player()
            chosen = <GUI asks cur to pick a card>
            result = logic.play_card(cur, chosen, callbacks)
            if result is not None:
                <show round-end screen>; break
            logic.advance_turn_if_possible()
    """

    def __init__(self, player_names: List[str]) -> None:
        if len(player_names) < 3 or len(player_names) > 8:
            raise ValueError("Shadow House Masquerade requires 3-8 players.")
        self.players: List[Player] = [Player(name=n) for n in player_names]
        self.board: Board = Board(self.players)
        self.round_over: bool = False
        self.last_result: Optional[RoundResult] = None

    # ------------------------------------------------------------------
    # Round / game lifecycle
    # ------------------------------------------------------------------
    def start_new_round(self) -> None:
        self.board.setup_new_round()
        self.round_over = False
        self.last_result = None

    def current_player(self) -> Player:
        return self.board.current_player()

    def advance_turn(self) -> Player:
        return self.board.advance_turn()

    def game_over(self) -> bool:
        return any(p.points >= WIN_THRESHOLD for p in self.players)

    def leaderboard(self) -> List[Player]:
        return sorted(self.players, key=lambda p: p.points, reverse=True)

    # ------------------------------------------------------------------
    # Public entry point: "play this card"
    # ------------------------------------------------------------------
    def play_card(
        self,
        player: Player,
        card_type: str,
        cb: EffectCallbacks,
    ) -> Optional[RoundResult]:
        """
        Validate and resolve playing *card_type* from *player*'s hand.

        Returns a :class:`RoundResult` if the round ends as a consequence,
        otherwise ``None``.
        """
        self._validate_play(player, card_type)

        # The Culprit card is different: playing it when it's your last card
        # ends the round immediately (scenario 3).
        if card_type == CULPRIT:
            player.play_card(card_type)
            return self._end_round_culprit_won(player)

        player.play_card(card_type)
        self._log(cb, f"{player.name} plays [{CARD_NAMES[card_type]}].")

        # Dispatch to the correct effect handler
        handler = self._effect_handlers().get(card_type, self._effect_noop)
        result = handler(player, cb)
        return result

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate_play(self, player: Player, card_type: str) -> None:
        if card_type not in player.hand:
            raise IllegalPlay(f"{player.name} does not hold {CARD_NAMES.get(card_type, card_type)}.")

        if card_type == CULPRIT and player.hand_size() != 1:
            raise IllegalPlay(
                "The Culprit card can only be played when it is your LAST card."
            )

        # First on the Scene is auto-played at the start of the round; it's
        # legal only on the very first turn and only if the round has not yet
        # started.
        if card_type == FIRST_ON_SCENE and self.board.round_started:
            raise IllegalPlay("First on the Scene has already been played this round.")

    # ------------------------------------------------------------------
    # Effect handler table
    # ------------------------------------------------------------------
    def _effect_handlers(self):
        return {
            FIRST_ON_SCENE: self._effect_first_on_scene,
            DETECTIVE: self._effect_detective,
            ACCOMPLICE: self._effect_accomplice,
            SHERIFF: self._effect_sheriff,
            TOBY: self._effect_toby,
            BABY: self._effect_baby,
            SHARE: self._effect_share,
            RUMORS: self._effect_rumors,
            FRENZY: self._effect_frenzy,
            SOOTHSAYER: self._effect_soothsayer,
            WITNESS: self._effect_witness,
            SERVANT: self._effect_servant,
            HOUSEKEEPER: self._effect_housekeeper,
            SWAP: self._effect_swap,
            ALIBI: self._effect_noop,        # alibi has no on-play effect
        }

    # ------------------------------------------------------------------
    # Individual card effects
    # ------------------------------------------------------------------
    def _effect_noop(self, actor: Player, cb: EffectCallbacks):
        return None

    def _effect_first_on_scene(self, actor: Player, cb: EffectCallbacks):
        self.board.round_started = True
        cb.show_message(
            "Viscount Shadow is dead!!!",
            f"{actor.name} discovers the body. The game begins!",
        )
        return None

    # -- Detective ---------------------------------------------------
    def _effect_detective(self, actor: Player, cb: EffectCallbacks):
        eligible = [
            p for p in self.players
            if p is not actor and not p.servant_protection
        ]
        if not eligible:
            cb.show_message("Detective", "Nobody can be questioned right now!")
            return None

        target = cb.choose_player(
            actor,
            "Detective: who would you like to question?",
            eligible,
        )

        # The target must answer truthfully UNLESS they hold an Alibi card.
        if target.is_culprit() and not target.has_alibi():
            cb.show_message(
                "Culprit unmasked!",
                f"{target.name} is the culprit! {actor.name} solved the case.",
            )
            return self._end_round_detective_wins(actor, target)
        else:
            answer = "No, I'm not the culprit!"
            cb.show_message(
                f"{target.name} answers…",
                answer,
            )
            return None

    # -- Accomplice ---------------------------------------------------
    def _effect_accomplice(self, actor: Player, cb: EffectCallbacks):
        # actor.is_accomplice was set inside play_card()
        eligible = [p for p in self.players if p is not actor and p.hand_size() > 0]
        if not eligible:
            cb.show_message("Accomplice", "No valid target (nobody has any cards).")
            return None

        target = cb.choose_player(
            actor,
            "Accomplice: choose a player who must discard one card face up.",
            eligible,
        )
        card = cb.choose_card_from_hand(
            target,
            "Choose ONE card from your hand to discard face up.",
            target,
            list(target.hand),
        )
        # If they discard their last card AND it is the Culprit → culprit wins
        if card == CULPRIT and target.hand_size() == 1:
            target.remove_card(card)
            target.played.append(card)
            cb.show_message(
                "Culprit cornered — escapes!",
                f"{target.name} was forced to discard their last card… the Culprit! "
                "They win the round along with their accomplices.",
            )
            return self._end_round_culprit_won(target)

        # Normal discard — remove card, reveal it, draw a new one
        target.remove_card(card)
        target.played.append(card)  # discarded face up
        new_card = self.board.draw_card()
        if new_card is not None:
            target.add_card(new_card)

        cb.show_message(
            "Accomplice effect",
            f"{target.name} discarded {CARD_NAMES[card]} and drew a new card.",
        )
        return None

    # -- Sheriff ------------------------------------------------------
    def _effect_sheriff(self, actor: Player, cb: EffectCallbacks):
        eligible = [
            p for p in self.players
            if p is not actor and not p.housekeeper_protection
        ]
        if not eligible:
            cb.show_message("Sheriff", "No valid target for the handcuffs!")
            return None
        target = cb.choose_player(
            actor, "Sheriff: give the handcuffs token to…", eligible
        )
        self.board.give_handcuffs_to(target)
        cb.show_message(
            "Handcuffs!",
            f"{actor.name} places the handcuffs on {target.name}.",
        )
        return None

    # -- Toby ---------------------------------------------------------
    def _effect_toby(self, actor: Player, cb: EffectCallbacks):
        eligible = [
            p for p in self.players
            if p is not actor and p.hand_size() > 0 and not p.housekeeper_protection
        ]
        if not eligible:
            cb.show_message("Toby", "Nobody to investigate!")
            return None

        target = cb.choose_player(
            actor, "Toby: whose card would you like to see?", eligible
        )
        card = cb.choose_card_from_hand(
            actor,
            f"Pick one card from {target.name}'s hand to reveal.",
            target,
            list(target.hand),
        )
        cb.show_message(
            "Toby reveals…",
            f"{target.name} was holding: {CARD_NAMES[card]}.",
        )
        if card == CULPRIT:
            return self._end_round_toby_wins(actor, target)
        return None

    # -- Baby of the Family ------------------------------------------
    def _effect_baby(self, actor: Player, cb: EffectCallbacks):
        culprit = self._find_culprit_holder()
        if culprit is None:
            cb.show_message(
                "The Baby of the Family",
                "Odd… nobody seems to hold the Culprit card right now.",
            )
            return None
        # Show a private message ONLY to the culprit (simulates 'culprit opens eyes')
        cb.show_private_message(
            culprit,
            "Shhh… the culprit opens their eyes",
            "Only YOU see this. You are currently the Culprit.\n\n"
            "Everyone else had their eyes closed.",
        )
        cb.show_message(
            "The Baby of the Family",
            "Everyone has opened their eyes again. The Culprit knows who they are.",
        )
        return None

    # -- Share --------------------------------------------------------
    def _effect_share(self, actor: Player, cb: EffectCallbacks):
        """Every player picks a card → passes to the player on their LEFT."""
        gifts: List[Optional[str]] = []
        for p in self.players:
            if p.hand_size() == 0:
                gifts.append(None)
                continue
            card = cb.choose_card_from_hand(
                p,
                "Share: choose ONE card to pass to your left neighbour.",
                p,
                list(p.hand),
            )
            p.remove_card(card)
            gifts.append(card)

        # Pass to the left (next index)
        for i, p in enumerate(self.players):
            target_idx = (i + 1) % len(self.players)
            gift = gifts[i]
            if gift is not None:
                self.players[target_idx].add_card(gift)

        cb.show_message("Share", "All players have passed a card to their left.")
        return None

    # -- Rumors -------------------------------------------------------
    def _effect_rumors(self, actor: Player, cb: EffectCallbacks):
        """Every player draws a random card from the player on their RIGHT."""
        # Collect stolen cards first so removals don't affect ongoing loop
        takings: List[Optional[str]] = []
        for i, p in enumerate(self.players):
            right_idx = (i - 1) % len(self.players)
            donor = self.players[right_idx]
            if donor.hand_size() == 0:
                takings.append(None)
            else:
                stolen = random.choice(donor.hand)
                donor.remove_card(stolen)
                takings.append(stolen)

        for i, p in enumerate(self.players):
            gift = takings[i]
            if gift is not None:
                p.add_card(gift)

        cb.show_message(
            "Rumors",
            "Each player has stolen a random card from the player on their right.",
        )
        return None

    # -- Frenzy -------------------------------------------------------
    def _effect_frenzy(self, actor: Player, cb: EffectCallbacks):
        """
        Each player contributes one card → shuffled → re-dealt one at random.

        If this is the last card in *actor*'s hand, the rule says it has no
        effect (handled here by a hand_size check).
        """
        # actor.played already has FRENZY because play_card removed it first.
        if actor.hand_size() == 0 and all(p is actor or p.hand_size() == 0 for p in self.players):
            cb.show_message("Frenzy!!!", "Played too late — no effect.")
            return None

        contributions: List[str] = []
        donors: List[Player] = []
        for p in self.players:
            if p.hand_size() == 0:
                continue
            card = cb.choose_card_from_hand(
                p,
                "Frenzy!!!: choose ONE card to throw into the melee.",
                p,
                list(p.hand),
            )
            p.remove_card(card)
            contributions.append(card)
            donors.append(p)

        random.shuffle(contributions)
        for p, c in zip(donors, contributions):
            p.add_card(c)
        cb.show_message("Frenzy!!!", "Chaos! Cards have been shuffled and re-dealt.")
        return None

    # -- Soothsayer ---------------------------------------------------
    def _effect_soothsayer(self, actor: Player, cb: EffectCallbacks):
        msg = cb.prompt_soothsayer_message(actor)
        cb.show_message(
            f"{actor.name} pronounces…",
            msg or "(the soothsayer remains silent)",
        )
        return None

    # -- Witness ------------------------------------------------------
    def _effect_witness(self, actor: Player, cb: EffectCallbacks):
        eligible = [p for p in self.players if p is not actor and p.hand_size() > 0]
        if not eligible:
            cb.show_message("Witness", "No valid target to investigate.")
            return None
        target = cb.choose_player(
            actor, "Witness: secretly look at whose hand?", eligible
        )

        # Show the hand privately to the actor
        hand_text = "\n".join(f"  • {CARD_NAMES[c]}" for c in target.hand)
        cb.show_private_message(
            actor,
            f"{target.name}'s hand (secret)",
            hand_text,
        )

        suspicious = target.is_culprit() or ACCOMPLICE in target.hand
        if suspicious and actor.hand_size() > 0:
            if cb.ask_yes_no(actor, "Swap one of your cards with theirs?"):
                my_card = cb.choose_card_from_hand(
                    actor, "Pick ONE of your cards to give away.",
                    actor, list(actor.hand),
                )
                their_card = cb.choose_card_from_hand(
                    actor,
                    f"Pick ONE of {target.name}'s cards to take.",
                    target, list(target.hand),
                )
                actor.remove_card(my_card)
                target.remove_card(their_card)
                actor.add_card(their_card)
                target.add_card(my_card)
                cb.show_message(
                    "Witness",
                    f"{actor.name} and {target.name} swapped a card in secret.",
                )
                return None

        cb.show_message(
            "Witness",
            f"{actor.name} looked at {target.name}'s hand and said nothing.",
        )
        return None

    # -- Servant / Housekeeper (protections) -------------------------
    def _effect_servant(self, actor: Player, cb: EffectCallbacks):
        actor.servant_protection = True
        cb.show_message(
            "The Servant",
            f"{actor.name} is protected from the Detective until their next turn.",
        )
        return None

    def _effect_housekeeper(self, actor: Player, cb: EffectCallbacks):
        actor.housekeeper_protection = True
        cb.show_message(
            "The Housekeeper",
            f"{actor.name} is protected from Toby and the Sheriff until their next turn.",
        )
        return None

    # -- Swap ---------------------------------------------------------
    def _effect_swap(self, actor: Player, cb: EffectCallbacks):
        if actor.hand_size() == 0:
            cb.show_message("Swap", "You have no card to give — effect ignored.")
            return None
        eligible = [p for p in self.players if p is not actor and p.hand_size() > 0]
        if not eligible:
            cb.show_message("Swap", "Nobody to swap with.")
            return None
        target = cb.choose_player(
            actor, "Swap: pick a player to swap cards with.", eligible
        )
        my_card = cb.choose_card_from_hand(
            actor, "Pick YOUR card to give away.", actor, list(actor.hand)
        )
        their_card = cb.choose_card_from_hand(
            target,
            f"{target.name}: pick ONE of your cards to give to {actor.name}.",
            target, list(target.hand),
        )
        actor.remove_card(my_card)
        target.remove_card(their_card)
        actor.add_card(their_card)
        target.add_card(my_card)
        cb.show_message("Swap", f"{actor.name} and {target.name} swapped a card.")
        return None

    # ------------------------------------------------------------------
    # Round-end resolution (4 scenarios in the rulebook)
    # ------------------------------------------------------------------
    def _find_culprit_holder(self) -> Optional[Player]:
        for p in self.players:
            if p.is_culprit():
                return p
        return None

    def _accomplice_players(self) -> List[Player]:
        return [p for p in self.players if p.is_accomplice]

    # Scenario 1 — Detective wins
    def _end_round_detective_wins(self, detective: Player, culprit: Player) -> RoundResult:
        scores: dict = {}
        # Detective gets 2 points UNLESS they played accomplice
        if not detective.is_accomplice:
            scores[detective.name] = 2
            detective.add_points(2)
        else:
            scores[detective.name] = 0
        # Culprit + accomplices = 0
        scores[culprit.name] = 0
        for acc in self._accomplice_players():
            if acc.name not in scores:
                scores[acc.name] = 0
        # Everyone else (not culprit, not accomplice) gets 1 point
        for p in self.players:
            if p is culprit or p.is_accomplice or p is detective:
                continue
            scores[p.name] = 1
            p.add_points(1)
        winners = [detective.name] if not detective.is_accomplice else []
        self.round_over = True
        result = RoundResult(
            reason=f"{detective.name} (Detective) unmasked {culprit.name} — the Culprit.",
            scenario=1,
            winners=winners,
            scores=scores,
            culprit_name=culprit.name,
        )
        self.last_result = result
        return result

    # Scenario 2 — Toby wins
    def _end_round_toby_wins(self, toby_player: Player, culprit: Player) -> RoundResult:
        scores: dict = {}
        if not toby_player.is_accomplice:
            scores[toby_player.name] = 3
            toby_player.add_points(3)
        else:
            scores[toby_player.name] = 0
        scores[culprit.name] = 0
        for acc in self._accomplice_players():
            if acc.name not in scores:
                scores[acc.name] = 0
        for p in self.players:
            if p is culprit or p.is_accomplice or p is toby_player:
                continue
            scores[p.name] = 1
            p.add_points(1)
        winners = [toby_player.name] if not toby_player.is_accomplice else []
        self.round_over = True
        result = RoundResult(
            reason=f"{toby_player.name} (Toby) exposed {culprit.name} — the Culprit.",
            scenario=2,
            winners=winners,
            scores=scores,
            culprit_name=culprit.name,
        )
        self.last_result = result
        return result

    # Scenario 3 — Culprit wins (last card played or discarded by accomplice)
    def _end_round_culprit_won(self, culprit: Player) -> RoundResult:
        scores: dict = {culprit.name: 2}
        culprit.add_points(2)
        for p in self.players:
            if p is culprit:
                continue
            if p.is_accomplice:
                scores[p.name] = 2
                p.add_points(2)
            else:
                scores[p.name] = 0
        winners = [p.name for p in self.players if p is culprit or p.is_accomplice]
        self.round_over = True
        result = RoundResult(
            reason=f"{culprit.name} (the Culprit) escaped justice!",
            scenario=3,
            winners=winners,
            scores=scores,
            culprit_name=culprit.name,
        )
        self.last_result = result
        return result

    # Scenario 4 — Handcuffed player reveals culprit at round end.
    # This is triggered by the GUI at the very end of a "stalled" round
    # (e.g. everyone passed without anyone winning).
    def resolve_handcuffs_reveal(self) -> RoundResult:
        holder = self.board.handcuffs_on_player()
        culprit = self._find_culprit_holder()
        if holder is None or culprit is None:
            self.round_over = True
            # Nobody had handcuffs — no points.
            result = RoundResult(
                reason="The round fizzled out with no arrest.",
                scenario=4,
                winners=[],
                scores={p.name: 0 for p in self.players},
                culprit_name=culprit.name if culprit else None,
            )
            self.last_result = result
            return result

        scores: dict = {}
        if holder is culprit:
            # Scenario 4 success: everyone except culprit/accomplices gets 1
            scores[culprit.name] = 0
            for p in self.players:
                if p is culprit:
                    continue
                if p.is_accomplice:
                    scores[p.name] = 0
                else:
                    scores[p.name] = 1
                    p.add_points(1)
            winners = [p.name for p in self.players if not p.is_accomplice and p is not culprit]
            reason = (
                f"The handcuffs token was on {culprit.name} — the Culprit is caught!"
            )
        else:
            # Handcuffs were on the wrong person → culprit escapes, nobody scores
            scores = {p.name: 0 for p in self.players}
            winners = [culprit.name] + [p.name for p in self._accomplice_players()]
            reason = (
                f"The handcuffs were on {holder.name}, but the real Culprit was "
                f"{culprit.name}. They escape!"
            )

        self.round_over = True
        result = RoundResult(
            reason=reason,
            scenario=4,
            winners=winners,
            scores=scores,
            culprit_name=culprit.name,
        )
        self.last_result = result
        return result

    # ------------------------------------------------------------------
    # Logging helper
    # ------------------------------------------------------------------
    def _log(self, cb: EffectCallbacks, msg: str) -> None:
        # In the current implementation, each effect calls `show_message`
        # itself for user-visible events; this is a hook for future logging.
        pass

    # ------------------------------------------------------------------
    # Serialization (save/resume)
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "board": self.board.to_dict(),
            "round_over": self.round_over,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameLogic":
        board = Board.from_dict(data["board"])
        logic = cls.__new__(cls)
        logic.players = board.players
        logic.board = board
        logic.round_over = bool(data.get("round_over", False))
        logic.last_result = None
        return logic
