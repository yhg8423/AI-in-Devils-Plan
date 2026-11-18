"""Run the Russian Roulette match."""

from ..match import DAY_TWO_MAIN, DAY_TWO_PRISON, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=DAY_TWO_PRISON, seats=6, previous_main=DAY_TWO_MAIN)
