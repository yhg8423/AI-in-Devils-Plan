"""Validate shared Word2Vec data before opening a Hidden Word match log."""

import argparse
from functools import partial
import json
from pathlib import Path
import sys

from ..match import DAY_FIVE_MAIN, DAY_FOUR_MAIN, run_cli
from .game import play, validate_saved_setup, validate_vectors
from .vectors import load_vectors


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    options = dict(title=DAY_FIVE_MAIN, seats=(6, 5), previous_main=DAY_FOUR_MAIN, after_prison=True, argv=argv)
    if "--help" in argv or "-h" in argv:
        return run_cli(play, **options)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=Path)
    args, _ = parser.parse_known_args(argv)
    try:
        setup = None
        if args.resume:
            if args.output is None:
                raise ValueError("--resume에는 중단된 매치의 --output 경로가 필요합니다.")
            with args.output.open(encoding="utf-8") as stream:
                for line in stream:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("중단된 매치의 기록 형식이 올바르지 않습니다.")
                    if row.get("msg_type") == "word_setup":
                        setup = json.loads(row["content"])
                        break
            if not isinstance(setup, dict) or setup.get("version") != 2:
                validate_saved_setup(setup, None)
        vectors = validate_vectors(load_vectors())
        if args.resume:
            validate_saved_setup(setup, vectors)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    return run_cli(partial(play, vectors=vectors), **options)


if __name__ == "__main__":
    main()
