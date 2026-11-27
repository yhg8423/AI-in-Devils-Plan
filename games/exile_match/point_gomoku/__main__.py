"""Run the last two exiles' Point Gomoku match."""

from ...match import EIGHTH_EXILE, SEVENTH_EXILE, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=EIGHTH_EXILE, seats=2, exile_roster=True, previous_exile=SEVENTH_EXILE)
