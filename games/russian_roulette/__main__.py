"""Run the Russian Roulette match."""

from ..match import DAY_TWO_MAIN, run_cli
from .game import play


if __name__ == "__main__":
    run_cli(play, title="2일차 감옥 매치 · 러시안 룰렛", seats=6, previous_main=DAY_TWO_MAIN)
