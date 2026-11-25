"""Run Hidden Word after the Day 4 main and prison match results."""

from ..match import DAY_FIVE_MAIN, DAY_FOUR_MAIN, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=DAY_FIVE_MAIN, seats=(6, 5), previous_main=DAY_FOUR_MAIN, after_prison=True)
