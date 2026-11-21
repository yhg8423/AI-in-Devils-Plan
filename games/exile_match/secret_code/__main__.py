"""Run the third exile match: Secret Code."""

from ...match import SECOND_EXILE, THIRD_EXILE, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title=THIRD_EXILE, seats=4, exile_roster=True, previous_exile=SECOND_EXILE)
