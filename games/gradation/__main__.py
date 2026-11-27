"""Run the Day 6 Gradation prison match after shared stage integration."""

from games import match as runtime
from .game import play


def main(argv=None):
    return runtime.run_cli(play, title=runtime.DAY_SIX_PRISON, seats=(3, 2),
                           previous_main=runtime.DAY_SIX_MAIN, argv=argv)


if __name__ == "__main__":
    main()
