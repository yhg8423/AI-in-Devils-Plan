"""Compatibility imports and command for the original Either Or module."""

from games.either_or.lay_the_grass.choice_five_demo import make_demo_arena as make_demo_arena
from games.either_or.lay_the_grass.demo import main as main
from games.either_or.lay_the_grass.choice_five import (
    CHANNEL_NAMES as CHANNEL_NAMES,
    CHOICE_REQUEST as CHOICE_REQUEST,
    INFORMATION as INFORMATION,
    MAX_SPEECH_LENGTH as MAX_SPEECH_LENGTH,
    OPTIONS as OPTIONS,
    PLAYER_COUNT as PLAYER_COUNT,
    POINTS_AWARDED as POINTS_AWARDED,
    PREVIEW as PREVIEW,
    SCORE as SCORE,
    ChoiceFive as ChoiceFive,
    format_speech as format_speech,
)
from games.either_or.lay_the_grass.simulation import (
    DISCUSSION_PROMPT as DISCUSSION_PROMPT,
    ConcordiaBackend as ConcordiaBackend,
    ScriptedLanguageModel as ScriptedLanguageModel,
    make_arena as make_arena,
    play_choice_five as play_choice_five,
)


if __name__ == "__main__":
    main()
