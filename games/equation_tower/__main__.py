"""Run the Day 5 Tower of Equations prison match."""

from ..match import DAY_FIVE_MAIN, DAY_FIVE_PRISON, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=DAY_FIVE_PRISON, seats=(3, 2), previous_main=DAY_FIVE_MAIN)
