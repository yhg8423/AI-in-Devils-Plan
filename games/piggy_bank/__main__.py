"""Run the Day 3 Piggy Bank prison match."""

from ..match import DAY_THREE_MAIN, DAY_THREE_PRISON, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=DAY_THREE_PRISON, seats=4, previous_main=DAY_THREE_MAIN)
