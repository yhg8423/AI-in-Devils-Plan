"""Run the Heavy 13 match."""

from ..match import DAY_ONE_MAIN, DAY_ONE_PRISON, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=DAY_ONE_PRISON, seats=7, previous_main=DAY_ONE_MAIN)
