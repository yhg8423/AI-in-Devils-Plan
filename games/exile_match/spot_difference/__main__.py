"""Run the second exile match: Spot the Changes."""

from ...match import FIRST_EXILE, SECOND_EXILE, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=SECOND_EXILE, seats=4, exile_roster=True, previous_exile=FIRST_EXILE)
