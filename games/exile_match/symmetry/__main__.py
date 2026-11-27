"""Run the fifth exile match: Symmetrical Puzzle."""

import sys

from ...match import FIFTH_EXILE, FOURTH_EXILE, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=FIFTH_EXILE, seats=(4, 3) if "--resume" in sys.argv else 4,
            exile_roster=True, previous_exile=FOURTH_EXILE)
