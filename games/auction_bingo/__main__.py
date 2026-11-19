"""Run the Day 4 Auction Bingo main match."""

from ..match import DAY_FOUR_MAIN, DAY_THREE_MAIN, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=DAY_FOUR_MAIN, seats=7, previous_main=DAY_THREE_MAIN,
            after_prison=True, guest="G01")
