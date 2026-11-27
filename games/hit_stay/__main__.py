"""Run HIT, STAY after the Day 5 main and prison matches."""

from ..match import DAY_FIVE_MAIN, DAY_SIX_MAIN, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=DAY_SIX_MAIN, seats=(5, 4), previous_main=DAY_FIVE_MAIN,
            after_prison=True, returnee=True)
