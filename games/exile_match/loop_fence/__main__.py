"""Run the fourth exile match: Loop Fence."""

from ...match import FOURTH_EXILE, THIRD_EXILE, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=FOURTH_EXILE, seats=4, exile_roster=True, previous_exile=THIRD_EXILE)
