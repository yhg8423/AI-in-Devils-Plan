"""Run the Mystery Stock Exchange match."""

from ..match import DAY_ONE_MAIN, DAY_TWO_MAIN, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=DAY_TWO_MAIN, seats=(12, 13), previous_main=DAY_ONE_MAIN, after_prison=True)
