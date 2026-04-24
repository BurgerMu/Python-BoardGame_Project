"""
gui/ui.py
----------
Tkinter GUI for Shadow House Masquerade.

The GUI follows a "screen stack" pattern: ``GameApp`` owns one root
window and swaps frames in/out depending on state (main menu → setup →
pass-device → turn → end-of-round → end-of-game).

Because Shadow House Masquerade is a hidden-information game played on
a single shared device, the flow enforces "pass the device" transitions
where all sensitive data is blanked out until the next player confirms
they are alone with the screen.

The GUI implements the ``EffectCallbacks`` protocol from
``game.logic`` so the logic layer can ask the current player questions
(choose target, choose card, yes/no) via modal dialogs.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, List, Optional

from data.storage import Storage
from game.logic import EffectCallbacks, GameLogic, RoundResult, IllegalPlay
from game.player import Player
from utils.helpers import (
    ALIBI,
    CARD_DESCRIPTIONS,
    CARD_NAMES,
    CULPRIT,
    FIRST_ON_SCENE,
    HAND_SIZE,
    MAX_PLAYERS,
    MIN_PLAYERS,
    WIN_THRESHOLD,
    describe_card,
)


# ---------------------------------------------------------------------------
# Colour palette (a moody manor-at-night feel)
# ---------------------------------------------------------------------------
BG_DARK = "#1d1a2a"
BG_MID = "#2b2640"
BG_PANEL = "#3a3456"
ACCENT = "#d4a93c"   # warm gold
ACCENT_RED = "#a9423a"
TEXT_LIGHT = "#f2ecd9"
TEXT_DIM = "#a9a3b9"
BTN_BG = "#5a4f7a"
BTN_HOVER = "#74679a"


# =============================================================================
# Helper: generic modal dialog
# =============================================================================
class _ListDialog(tk.Toplevel):
    """Centered modal dialog listing options as buttons. Returns chosen index."""

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        prompt: str,
        options: List[str],
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.configure(bg=BG_MID)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.result: Optional[int] = None

        tk.Label(
            self, text=prompt, bg=BG_MID, fg=TEXT_LIGHT,
            font=("Georgia", 12, "bold"), wraplength=420, justify="left",
        ).pack(padx=20, pady=(20, 12), anchor="w")

        frame = tk.Frame(self, bg=BG_MID)
        frame.pack(padx=20, pady=(0, 20))

        for i, opt in enumerate(options):
            b = tk.Button(
                frame, text=opt, width=36, anchor="w",
                bg=BTN_BG, fg=TEXT_LIGHT, activebackground=BTN_HOVER,
                activeforeground=TEXT_LIGHT, relief="flat",
                font=("Georgia", 11), padx=10, pady=6,
                command=lambda idx=i: self._choose(idx),
            )
            b.pack(fill="x", pady=3)

        self.update_idletasks()
        self._center(parent)
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # block close
        self.wait_window(self)

    def _choose(self, index: int) -> None:
        self.result = index
        self.destroy()

    def _center(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        px = parent.winfo_rootx() + parent.winfo_width() // 2 - w // 2
        py = parent.winfo_rooty() + parent.winfo_height() // 2 - h // 2
        self.geometry(f"+{max(0, px)}+{max(0, py)}")


# =============================================================================
# Main application
# =============================================================================
class GameApp(EffectCallbacks):
    """Root Tkinter application + implementation of EffectCallbacks."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Shadow House Masquerade")
        self.root.geometry("960x700")
        self.root.configure(bg=BG_DARK)
        self.root.minsize(820, 620)

        self.storage = Storage()
        self.logic: Optional[GameLogic] = None
        self.current_frame: Optional[tk.Frame] = None

        # Per-round: which players have taken a turn already this cycle
        # (used to decide when to offer the "handcuffs reveal" end-of-round).
        self._turn_counter: int = 0

        self._show_main_menu()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(self) -> None:
        self.root.mainloop()

    # ------------------------------------------------------------------
    # Screen management
    # ------------------------------------------------------------------
    def _swap_frame(self, build: Callable[[tk.Frame], None]) -> None:
        if self.current_frame is not None:
            self.current_frame.destroy()
        frame = tk.Frame(self.root, bg=BG_DARK)
        frame.pack(fill="both", expand=True)
        build(frame)
        self.current_frame = frame

    # ------------------------------------------------------------------
    # Main Menu
    # ------------------------------------------------------------------
    def _show_main_menu(self) -> None:
        def build(f: tk.Frame) -> None:
            tk.Label(
                f, text="Shadow House", bg=BG_DARK, fg=ACCENT,
                font=("Georgia", 36, "bold"),
            ).pack(pady=(80, 0))
            tk.Label(
                f, text="— Masquerade —", bg=BG_DARK, fg=ACCENT_RED,
                font=("Georgia", 22, "italic"),
            ).pack(pady=(0, 10))
            tk.Label(
                f, text='"Aaaaahhh! Viscount Shadow is dead!!!"',
                bg=BG_DARK, fg=TEXT_DIM, font=("Georgia", 12, "italic"),
            ).pack(pady=(0, 40))

            btn_frame = tk.Frame(f, bg=BG_DARK)
            btn_frame.pack()

            self._menu_button(btn_frame, "New Game",        self._show_setup).pack(pady=4)
            if self.storage.has_save():
                self._menu_button(btn_frame, "Resume Saved Game", self._resume_saved).pack(pady=4)
            self._menu_button(btn_frame, "Statistics",      self._show_stats).pack(pady=4)
            self._menu_button(btn_frame, "Recent Games",    self._show_history).pack(pady=4)
            self._menu_button(btn_frame, "How to Play",     self._show_how_to).pack(pady=4)
            self._menu_button(btn_frame, "Quit",            self.root.destroy).pack(pady=4)

        self._swap_frame(build)

    def _menu_button(self, parent: tk.Misc, text: str, cmd: Callable) -> tk.Button:
        return tk.Button(
            parent, text=text, width=24, font=("Georgia", 13),
            bg=BTN_BG, fg=TEXT_LIGHT, activebackground=BTN_HOVER,
            activeforeground=TEXT_LIGHT, relief="flat",
            padx=10, pady=8, command=cmd,
        )

    # ------------------------------------------------------------------
    # Setup screen
    # ------------------------------------------------------------------
    def _show_setup(self) -> None:
        def build(f: tk.Frame) -> None:
            tk.Label(
                f, text="Game Setup", bg=BG_DARK, fg=ACCENT,
                font=("Georgia", 22, "bold"),
            ).pack(pady=(30, 6))
            tk.Label(
                f,
                text=f"Shadow House Masquerade supports {MIN_PLAYERS} to {MAX_PLAYERS} players.",
                bg=BG_DARK, fg=TEXT_DIM, font=("Georgia", 11),
            ).pack(pady=(0, 20))

            panel = tk.Frame(f, bg=BG_MID, padx=24, pady=24)
            panel.pack(padx=40, pady=10, fill="x")

            tk.Label(panel, text="Number of players:", bg=BG_MID, fg=TEXT_LIGHT,
                     font=("Georgia", 12)).grid(row=0, column=0, sticky="w", pady=4)
            count_var = tk.IntVar(value=4)
            count_spin = tk.Spinbox(
                panel, from_=MIN_PLAYERS, to=MAX_PLAYERS, width=5,
                textvariable=count_var, font=("Georgia", 12),
                command=lambda: refresh_names(),
            )
            count_spin.grid(row=0, column=1, sticky="w", padx=(10, 0), pady=4)

            names_frame = tk.Frame(panel, bg=BG_MID)
            names_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 4))

            name_entries: List[tk.Entry] = []

            def refresh_names() -> None:
                for w in names_frame.winfo_children():
                    w.destroy()
                name_entries.clear()
                for i in range(count_var.get()):
                    row = tk.Frame(names_frame, bg=BG_MID)
                    row.pack(fill="x", pady=2)
                    tk.Label(row, text=f"Player {i + 1}:", bg=BG_MID, fg=TEXT_LIGHT,
                             font=("Georgia", 11), width=10, anchor="w").pack(side="left")
                    e = tk.Entry(row, font=("Georgia", 11), width=30)
                    e.insert(0, f"Player {i + 1}")
                    e.pack(side="left", padx=(5, 0))
                    name_entries.append(e)

            refresh_names()

            def start_game() -> None:
                raw_names = [e.get().strip() for e in name_entries]
                names: List[str] = []
                seen = set()
                for i, n in enumerate(raw_names):
                    if not n:
                        messagebox.showwarning("Missing name",
                                               f"Please enter a name for Player {i + 1}.")
                        return
                    if n in seen:
                        messagebox.showwarning("Duplicate name",
                                               f"Name '{n}' is used twice.")
                        return
                    seen.add(n)
                    names.append(n)
                try:
                    self.logic = GameLogic(names)
                except ValueError as exc:
                    messagebox.showerror("Invalid setup", str(exc))
                    return
                self.logic.start_new_round()
                self._turn_counter = 0
                self._show_pass_device()

            btn_row = tk.Frame(f, bg=BG_DARK)
            btn_row.pack(pady=20)
            self._menu_button(btn_row, "Start Game", start_game).pack(side="left", padx=8)
            self._menu_button(btn_row, "Back", self._show_main_menu).pack(side="left", padx=8)

        self._swap_frame(build)

    # ------------------------------------------------------------------
    # Pass-device screen — blanks everything until the current player confirms
    # ------------------------------------------------------------------
    def _show_pass_device(self) -> None:
        assert self.logic is not None
        cur = self.logic.current_player()

        def build(f: tk.Frame) -> None:
            tk.Label(
                f, text=f"Pass the device to {cur.name}",
                bg=BG_DARK, fg=ACCENT, font=("Georgia", 22, "bold"),
            ).pack(pady=(140, 20))
            tk.Label(
                f,
                text=("Only " + cur.name + " should look at this screen.\n"
                      "When you are ready, tap below to view your hand."),
                bg=BG_DARK, fg=TEXT_LIGHT, font=("Georgia", 13), justify="center",
            ).pack(pady=(0, 30))
            tk.Label(
                f, text=f"Round {self.logic.board.round_number} · "
                        f"turn #{self._turn_counter + 1}",
                bg=BG_DARK, fg=TEXT_DIM, font=("Georgia", 11, "italic"),
            ).pack()
            self._menu_button(f, f"I am {cur.name} — start turn",
                              self._show_turn_screen).pack(pady=30)
            # Save game option
            tk.Button(
                f, text="Save & exit to menu", bg=BG_DARK, fg=TEXT_DIM,
                activebackground=BG_DARK, relief="flat", bd=0,
                font=("Georgia", 10, "underline"),
                command=self._save_and_menu,
            ).pack()

        self._swap_frame(build)

    def _save_and_menu(self) -> None:
        if self.logic is None:
            self._show_main_menu()
            return
        if messagebox.askyesno("Save & Exit",
                               "Save current game and return to main menu?"):
            self.storage.save_game(self.logic.to_dict())
            messagebox.showinfo("Saved", "Game saved. You can resume from the main menu.")
            self._show_main_menu()

    def _resume_saved(self) -> None:
        data = self.storage.load_save()
        if not data:
            messagebox.showinfo("No save", "There is no saved game to resume.")
            return
        try:
            self.logic = GameLogic.from_dict(data)
        except Exception as exc:  # pragma: no cover - corrupted save
            messagebox.showerror("Resume failed", f"Could not load save: {exc}")
            return
        self.storage.delete_save()
        self._turn_counter = 0
        self._show_pass_device()

    # ------------------------------------------------------------------
    # Turn screen — the current player sees their hand and picks a card
    # ------------------------------------------------------------------
    def _show_turn_screen(self) -> None:
        assert self.logic is not None
        player = self.logic.current_player()
        board = self.logic.board

        # Auto-play First on the Scene on the very first turn of the round
        if not board.round_started and FIRST_ON_SCENE in player.hand:
            try:
                result = self.logic.play_card(player, FIRST_ON_SCENE, self)
            except IllegalPlay as exc:
                messagebox.showerror("Error", str(exc))
                return
            if result is not None:
                self._show_round_result(result)
                return
            # After the opener, fall through to a normal hand display

        def build(f: tk.Frame) -> None:
            # Top bar: scoreboard + handcuffs indicator
            top = tk.Frame(f, bg=BG_MID)
            top.pack(fill="x")
            self._render_scoreboard(top)

            # Middle: played cards on the table (all players, public)
            mid = tk.Frame(f, bg=BG_DARK)
            mid.pack(fill="x", padx=10, pady=8)
            self._render_played_summary(mid)

            # Hand panel
            body = tk.Frame(f, bg=BG_DARK)
            body.pack(fill="both", expand=True, padx=10, pady=(0, 8))

            tk.Label(
                body, text=f"{player.name} — your hand",
                bg=BG_DARK, fg=ACCENT, font=("Georgia", 16, "bold"),
            ).pack(anchor="w", pady=(6, 4))
            tk.Label(
                body, text="Click a card to play it.",
                bg=BG_DARK, fg=TEXT_DIM, font=("Georgia", 10, "italic"),
            ).pack(anchor="w")

            hand_frame = tk.Frame(body, bg=BG_DARK)
            hand_frame.pack(pady=8, anchor="w", fill="x")

            # If only the culprit card is held, it's mandatory but enforces last-card
            only_culprit = player.hand == [CULPRIT]

            for card in list(player.hand):
                self._render_card_button(hand_frame, card, player, only_culprit)

            # Bottom bar: handcuffs-reveal ability
            bottom = tk.Frame(f, bg=BG_DARK)
            bottom.pack(fill="x", pady=6)
            if player.has_handcuffs and self._turn_counter >= len(self.logic.players):
                tk.Button(
                    bottom,
                    text="🔒 Reveal! (I think the culprit is caught)",
                    bg=ACCENT_RED, fg=TEXT_LIGHT, relief="flat",
                    font=("Georgia", 11, "bold"), padx=14, pady=8,
                    command=self._trigger_handcuffs_reveal,
                ).pack(side="right", padx=10)

        self._swap_frame(build)

    def _render_scoreboard(self, parent: tk.Frame) -> None:
        assert self.logic is not None
        inner = tk.Frame(parent, bg=BG_MID, padx=10, pady=8)
        inner.pack(fill="x")
        for p in self.logic.players:
            ind = "🔒 " if p.has_handcuffs else ""
            active = " ← turn" if p is self.logic.current_player() else ""
            lbl = tk.Label(
                inner,
                text=f"{ind}{p.name}: {p.points} pts{active}",
                bg=BG_MID,
                fg=ACCENT if p is self.logic.current_player() else TEXT_LIGHT,
                font=("Georgia", 11, "bold" if p is self.logic.current_player() else "normal"),
                padx=10,
            )
            lbl.pack(side="left")

    def _render_played_summary(self, parent: tk.Frame) -> None:
        assert self.logic is not None
        canvas_outer = tk.Frame(parent, bg=BG_DARK)
        canvas_outer.pack(fill="x")
        tk.Label(
            canvas_outer, text="Cards played so far this round:",
            bg=BG_DARK, fg=TEXT_DIM, font=("Georgia", 10, "italic"),
        ).pack(anchor="w")
        table = tk.Frame(canvas_outer, bg=BG_DARK)
        table.pack(fill="x", pady=(4, 0))
        for p in self.logic.players:
            row = tk.Frame(table, bg=BG_PANEL)
            row.pack(fill="x", pady=1)
            tk.Label(
                row, text=f"  {p.name}: ", bg=BG_PANEL, fg=TEXT_LIGHT,
                font=("Georgia", 10, "bold"), width=16, anchor="w",
            ).pack(side="left")
            played_str = ", ".join(CARD_NAMES[c] for c in p.played) or "—"
            tk.Label(
                row, text=played_str, bg=BG_PANEL, fg=TEXT_DIM,
                font=("Georgia", 10), anchor="w",
            ).pack(side="left", fill="x", expand=True)

    def _render_card_button(
        self, parent: tk.Frame, card: str, player: Player, only_culprit: bool
    ) -> None:
        name = CARD_NAMES[card]
        desc = CARD_DESCRIPTIONS[card]

        # A culprit card can only be played when it's the last card in hand
        playable = True
        reason = ""
        if card == CULPRIT and player.hand_size() != 1:
            playable = False
            reason = "(Culprit can only be played as your LAST card)"

        color = ACCENT_RED if card == CULPRIT else BTN_BG
        frame = tk.Frame(parent, bg=color, padx=10, pady=8, cursor="hand2" if playable else "arrow")
        frame.pack(side="left", padx=4, pady=4, anchor="n")

        tk.Label(frame, text=name, bg=color, fg=TEXT_LIGHT,
                 font=("Georgia", 12, "bold")).pack(anchor="w")
        tk.Label(frame, text=desc, bg=color, fg=TEXT_LIGHT,
                 font=("Georgia", 9), wraplength=170, justify="left").pack(anchor="w", pady=(4, 0))
        if not playable:
            tk.Label(frame, text=reason, bg=color, fg=ACCENT,
                     font=("Georgia", 9, "italic"), wraplength=170).pack(anchor="w", pady=(4, 0))

        if playable:
            def on_click(_e=None, c=card) -> None:
                self._on_play_card(c)
            for widget in (frame, *frame.winfo_children()):
                widget.bind("<Button-1>", on_click)

    def _on_play_card(self, card: str) -> None:
        assert self.logic is not None
        player = self.logic.current_player()
        try:
            result = self.logic.play_card(player, card, self)
        except IllegalPlay as exc:
            messagebox.showwarning("Illegal play", str(exc))
            return

        if result is not None:
            self._show_round_result(result)
            return

        # Advance turn — but first check if the deck is exhausted / no moves
        self._turn_counter += 1
        self.logic.advance_turn()

        # If the next player has an empty hand, skip them (shouldn't happen often)
        if self.logic.current_player().hand_size() == 0 and self._turn_counter < 1000:
            self.logic.advance_turn()

        self._show_pass_device()

    # ------------------------------------------------------------------
    # Handcuffs reveal — lets the player with handcuffs end the round
    # ------------------------------------------------------------------
    def _trigger_handcuffs_reveal(self) -> None:
        assert self.logic is not None
        if not messagebox.askyesno(
            "Handcuffs reveal",
            "Declare the round over and reveal the culprit?\n\n"
            "(If the handcuffs token is on the culprit, everyone except "
            "the culprit and accomplices scores 1 point. Otherwise the "
            "culprit escapes and only they + accomplices 'win' the round.)",
        ):
            return
        result = self.logic.resolve_handcuffs_reveal()
        self._show_round_result(result)

    # ------------------------------------------------------------------
    # Round result / new round / game over
    # ------------------------------------------------------------------
    def _show_round_result(self, result: RoundResult) -> None:
        assert self.logic is not None

        # Record to history
        self.storage.append_history({
            "round_number": self.logic.board.round_number,
            "reason": result.reason,
            "winners": result.winners,
            "scores": result.scores,
            "culprit": result.culprit_name,
            "players": [p.name for p in self.logic.players],
        })

        def build(f: tk.Frame) -> None:
            tk.Label(
                f, text=f"Round {self.logic.board.round_number} — Results",
                bg=BG_DARK, fg=ACCENT, font=("Georgia", 22, "bold"),
            ).pack(pady=(30, 10))
            tk.Label(
                f, text=result.reason, bg=BG_DARK, fg=TEXT_LIGHT,
                font=("Georgia", 13, "italic"), wraplength=700, justify="center",
            ).pack(pady=(0, 20))

            table = tk.Frame(f, bg=BG_MID, padx=20, pady=16)
            table.pack(padx=40, pady=10)

            tk.Label(table, text="Player", bg=BG_MID, fg=ACCENT,
                     font=("Georgia", 12, "bold"), width=18, anchor="w").grid(row=0, column=0, sticky="w")
            tk.Label(table, text="+Round", bg=BG_MID, fg=ACCENT,
                     font=("Georgia", 12, "bold"), width=10).grid(row=0, column=1)
            tk.Label(table, text="Total", bg=BG_MID, fg=ACCENT,
                     font=("Georgia", 12, "bold"), width=10).grid(row=0, column=2)

            for i, p in enumerate(self.logic.leaderboard()):
                gained = result.scores.get(p.name, 0)
                tk.Label(table, text=p.name, bg=BG_MID, fg=TEXT_LIGHT,
                         font=("Georgia", 11), width=18, anchor="w").grid(
                    row=i + 1, column=0, sticky="w", pady=2)
                tk.Label(table, text=f"+{gained}", bg=BG_MID,
                         fg=ACCENT if gained > 0 else TEXT_DIM,
                         font=("Georgia", 11, "bold" if gained > 0 else "normal"),
                         width=10).grid(row=i + 1, column=1, pady=2)
                tk.Label(table, text=str(p.points), bg=BG_MID, fg=TEXT_LIGHT,
                         font=("Georgia", 11), width=10).grid(row=i + 1, column=2, pady=2)

            # Either continue or end the game
            btn_row = tk.Frame(f, bg=BG_DARK)
            btn_row.pack(pady=20)
            if self.logic.game_over():
                self._menu_button(btn_row, "See Final Winner", self._show_game_over).pack()
            else:
                self._menu_button(btn_row, "Next Round", self._start_next_round).pack(side="left", padx=6)
                self._menu_button(btn_row, "Quit to Menu", self._confirm_quit).pack(side="left", padx=6)

        self._swap_frame(build)

    def _confirm_quit(self) -> None:
        if messagebox.askyesno("Quit to menu",
                               "Return to the main menu? (Current game will be lost.)"):
            self.logic = None
            self._show_main_menu()

    def _start_next_round(self) -> None:
        assert self.logic is not None
        self.logic.start_new_round()
        self._turn_counter = 0
        self._show_pass_device()

    def _show_game_over(self) -> None:
        assert self.logic is not None
        leaderboard = self.logic.leaderboard()
        top_score = leaderboard[0].points
        winners = [p for p in leaderboard if p.points == top_score]

        # Persist stats
        winning_names = {p.name for p in winners}
        for p in self.logic.players:
            self.storage.update_player_stats(
                p.name, won_game=p.name in winning_names, round_points=p.points
            )
        self.storage.delete_save()

        def build(f: tk.Frame) -> None:
            tk.Label(
                f, text="🏆 Game Over!", bg=BG_DARK, fg=ACCENT,
                font=("Georgia", 30, "bold"),
            ).pack(pady=(40, 10))

            if len(winners) == 1:
                msg = f"{winners[0].name} wins with {top_score} points!"
            else:
                names = ", ".join(w.name for w in winners)
                msg = f"Tie game! {names} share the victory at {top_score} points."
            tk.Label(
                f, text=msg, bg=BG_DARK, fg=ACCENT_RED,
                font=("Georgia", 16, "italic"), wraplength=700, justify="center",
            ).pack(pady=(0, 24))

            panel = tk.Frame(f, bg=BG_MID, padx=20, pady=16)
            panel.pack(padx=60)
            tk.Label(panel, text="Final Standings", bg=BG_MID, fg=ACCENT,
                     font=("Georgia", 13, "bold")).pack(anchor="w", pady=(0, 8))
            for i, p in enumerate(leaderboard):
                tk.Label(
                    panel, text=f"{i + 1}. {p.name} — {p.points} pts",
                    bg=BG_MID, fg=TEXT_LIGHT, font=("Georgia", 12),
                    anchor="w", width=40,
                ).pack(anchor="w")

            self._menu_button(f, "Main Menu", self._show_main_menu).pack(pady=20)

        self._swap_frame(build)

    # ------------------------------------------------------------------
    # Stats / History / How-to
    # ------------------------------------------------------------------
    def _show_stats(self) -> None:
        stats = self.storage.load_stats()

        def build(f: tk.Frame) -> None:
            tk.Label(f, text="Player Statistics", bg=BG_DARK, fg=ACCENT,
                     font=("Georgia", 20, "bold")).pack(pady=(30, 10))
            if not stats:
                tk.Label(
                    f, text="No games on record yet — play a round first!",
                    bg=BG_DARK, fg=TEXT_DIM, font=("Georgia", 12, "italic"),
                ).pack(pady=30)
            else:
                panel = tk.Frame(f, bg=BG_MID, padx=20, pady=14)
                panel.pack(padx=40, pady=10)
                headers = ("Name", "Games", "Wins", "Win %", "Total Pts")
                for j, h in enumerate(headers):
                    tk.Label(panel, text=h, bg=BG_MID, fg=ACCENT,
                             font=("Georgia", 11, "bold"), width=12,
                             anchor="w" if j == 0 else "center").grid(row=0, column=j, padx=4, pady=2)
                sorted_stats = sorted(
                    stats.items(),
                    key=lambda kv: (kv[1].get("wins", 0), kv[1].get("total_points", 0)),
                    reverse=True,
                )
                for i, (name, data) in enumerate(sorted_stats):
                    games = int(data.get("games", 0))
                    wins = int(data.get("wins", 0))
                    pts = int(data.get("total_points", 0))
                    winpct = f"{(100.0 * wins / games):.0f}%" if games else "—"
                    values = (name, games, wins, winpct, pts)
                    for j, v in enumerate(values):
                        tk.Label(panel, text=str(v), bg=BG_MID, fg=TEXT_LIGHT,
                                 font=("Georgia", 11), width=12,
                                 anchor="w" if j == 0 else "center").grid(
                            row=i + 1, column=j, padx=4, pady=2)

            self._menu_button(f, "Back", self._show_main_menu).pack(pady=20)

        self._swap_frame(build)

    def _show_history(self) -> None:
        history = self.storage.load_history()

        def build(f: tk.Frame) -> None:
            tk.Label(f, text="Recent Games", bg=BG_DARK, fg=ACCENT,
                     font=("Georgia", 20, "bold")).pack(pady=(30, 10))

            if not history:
                tk.Label(
                    f, text="No games played yet!",
                    bg=BG_DARK, fg=TEXT_DIM, font=("Georgia", 12, "italic"),
                ).pack(pady=30)
            else:
                # Scrollable list
                wrap = tk.Frame(f, bg=BG_DARK)
                wrap.pack(fill="both", expand=True, padx=40, pady=10)
                canvas = tk.Canvas(wrap, bg=BG_DARK, highlightthickness=0)
                scroll = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
                inner = tk.Frame(canvas, bg=BG_DARK)
                inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
                canvas.create_window((0, 0), window=inner, anchor="nw")
                canvas.configure(yscrollcommand=scroll.set)
                canvas.pack(side="left", fill="both", expand=True)
                scroll.pack(side="right", fill="y")

                for rec in reversed(history[-25:]):
                    panel = tk.Frame(inner, bg=BG_MID, padx=12, pady=8)
                    panel.pack(fill="x", pady=4)
                    tk.Label(panel,
                             text=f"{rec.get('timestamp', '')}  ·  Round {rec.get('round_number', '?')}",
                             bg=BG_MID, fg=TEXT_DIM, font=("Georgia", 9, "italic")
                             ).pack(anchor="w")
                    tk.Label(panel, text=rec.get("reason", ""),
                             bg=BG_MID, fg=TEXT_LIGHT, font=("Georgia", 11),
                             wraplength=720, justify="left").pack(anchor="w")
                    winners = rec.get("winners") or []
                    if winners:
                        tk.Label(panel, text=f"Winners: {', '.join(winners)}",
                                 bg=BG_MID, fg=ACCENT, font=("Georgia", 10, "bold")
                                 ).pack(anchor="w")

            self._menu_button(f, "Back", self._show_main_menu).pack(pady=10)

        self._swap_frame(build)

    def _show_how_to(self) -> None:
        text = (
            "GOAL\n"
            "• The Culprit wants to play their LAST card (the Culprit card) to "
            "escape justice.\n"
            "• Everyone else wants to expose the Culprit — via the Detective, "
            "Toby, or by ending the round with the handcuffs token on the "
            "right person.\n\n"
            "SCORING PER ROUND\n"
            "  1) Detective catches Culprit → Detective +2, other non-accomplices +1.\n"
            "  2) Toby exposes Culprit → Toby +3, other non-accomplices +1.\n"
            "  3) Culprit plays/discards last card → Culprit + accomplices +2.\n"
            "  4) Handcuffs on Culprit at round end → everyone else +1.\n\n"
            f"The first player to reach {WIN_THRESHOLD} points wins the game.\n\n"
            "ON THIS DEVICE\n"
            "• This is a pass-and-play adaptation: when it's your turn, the app "
            "will tell you to take the device. Hide the screen from others!\n"
            "• Click a card in your hand to play it. Some cards require you to "
            "choose a target — dialogs will guide you."
        )

        def build(f: tk.Frame) -> None:
            tk.Label(f, text="How to Play", bg=BG_DARK, fg=ACCENT,
                     font=("Georgia", 20, "bold")).pack(pady=(30, 10))
            box = tk.Text(
                f, bg=BG_MID, fg=TEXT_LIGHT, font=("Georgia", 11),
                wrap="word", height=22, width=80, padx=16, pady=12, bd=0,
                relief="flat",
            )
            box.insert("1.0", text)
            box.configure(state="disabled")
            box.pack(padx=40, pady=6, fill="both", expand=True)
            self._menu_button(f, "Back", self._show_main_menu).pack(pady=10)

        self._swap_frame(build)

    # ==================================================================
    # EffectCallbacks implementation (called by game.logic)
    # ==================================================================
    def choose_player(
        self, actor: Player, prompt: str, eligible: List[Player]
    ) -> Player:
        if len(eligible) == 1:
            return eligible[0]
        labels = [f"{p.name}  (hand: {p.hand_size()}, played: {len(p.played)})"
                  for p in eligible]
        idx = _ListDialog(self.root, "Choose a player", prompt, labels).result
        if idx is None:  # shouldn't happen due to blocked close
            idx = 0
        return eligible[idx]

    def choose_card_from_hand(
        self, actor: Player, prompt: str, hand_owner: Player, hand: List[str]
    ) -> str:
        if len(hand) == 1:
            return hand[0]
        labels = [CARD_NAMES[c] for c in hand]
        # If the actor is NOT the hand owner, labels shouldn't reveal names
        # (e.g. Toby choosing a card from another player's hand).
        if actor is not hand_owner:
            labels = [f"Card #{i + 1}" for i in range(len(hand))]
        idx = _ListDialog(self.root, "Choose a card", prompt, labels).result
        if idx is None:
            idx = 0
        return hand[idx]

    def ask_yes_no(self, actor: Player, prompt: str) -> bool:
        return bool(messagebox.askyesno(f"{actor.name}", prompt))

    def show_message(self, title: str, message: str) -> None:
        messagebox.showinfo(title, message)

    def show_private_message(self, viewer: Player, title: str, message: str) -> None:
        messagebox.showinfo(f"{viewer.name} — {title}", message)

    def prompt_soothsayer_message(self, actor: Player) -> str:
        resp = simpledialog.askstring(
            f"{actor.name} — Soothsayer",
            "Share your thoughts with everyone (who do you suspect, and why?):",
            parent=self.root,
        )
        return resp or ""


# ---------------------------------------------------------------------------
# Convenience top-level function
# ---------------------------------------------------------------------------
def launch() -> None:
    """Entry point used by ``main.py``."""
    app = GameApp()
    app.run()
