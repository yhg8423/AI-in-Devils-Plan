"""Run the seventh exile match: Count the Rectangles."""

import sys

from ...match import SEVENTH_EXILE, SIXTH_EXILE, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=SEVENTH_EXILE, seats=(4, 3) if "--resume" in sys.argv else 4,
            exile_roster=True, previous_exile=SIXTH_EXILE)
