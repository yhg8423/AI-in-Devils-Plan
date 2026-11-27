"""Run the sixth exile match: Flags Around the World."""

import sys

from ...match import FIFTH_EXILE, SIXTH_EXILE, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=SIXTH_EXILE, seats=(4, 3, 5, 6) if "--resume" in sys.argv else 4,
            exile_roster=True, previous_exile=FIFTH_EXILE)
