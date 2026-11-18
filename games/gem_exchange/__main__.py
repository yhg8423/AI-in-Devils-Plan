"""Run the Day 3 Gem Black Market main match."""

from ..match import DAY_THREE_MAIN, DAY_TWO_MAIN, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=DAY_THREE_MAIN, seats=(9, 10), previous_main=DAY_TWO_MAIN, after_prison=True)
