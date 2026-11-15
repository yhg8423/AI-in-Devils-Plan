"""Run the full Either/Or match."""

from ..match import DAY_ONE_MAIN, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=DAY_ONE_MAIN, seats=16)
