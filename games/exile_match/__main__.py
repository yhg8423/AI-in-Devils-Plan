"""Run the first exile match: Piece Puzzle."""

from ..match import FIRST_EXILE, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=FIRST_EXILE, seats=4, exile_roster=True)
