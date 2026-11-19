"""Run the Day 4 Wall Go II prison match."""

from ..match import DAY_FOUR_MAIN, DAY_FOUR_PRISON, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=DAY_FOUR_PRISON, seats=3, previous_main=DAY_FOUR_MAIN)
