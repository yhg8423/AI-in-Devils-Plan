"""Run and display a scripted 16-player Either Or match."""

import argparse
from collections.abc import Iterable

from chatarena.arena import Arena
from concordia.components.agent.observation import OBSERVATION_TAG
from concordia.language_model.language_model import LanguageModel

from .choice_five import CHANNEL_NAMES, INFORMATION, PLAYER_COUNT, PREVIEW, SCORE, format_speech, room_label
from .simulation import DiscussionAction, ScriptedLanguageModel, make_arena, play_choice_five


DEMO_DISCUSSION_ROUNDS = 10


def next_demo_speech(
    prompt: str, channel: str, *replies: tuple[str, str], to: str | None = None
) -> DiscussionAction:
    for cue, text in replies:
        if cue in prompt and text not in prompt:
            speech: DiscussionAction = {"type": "speak", "channel": channel, "text": text}
            if to is not None:
                speech["to"] = to
            return speech
    return {"type": "pass"}


def demo_room_speech(prompt: str, room: int, *replies: tuple[str, str]) -> DiscussionAction:
    if f"현재 위치 {room_label(room)}" not in prompt:
        return {"type": "move", "room": room}
    return next_demo_speech(prompt, "room", *replies)


def demo_models(player_names: Iterable[str]) -> dict[str, str | LanguageModel]:
    models: dict[str, str | LanguageModel] = dict.fromkeys(player_names, SCORE)
    first, second, third, fourth, fifth, sixth = tuple(models)[:6]
    whisper = f"{third}, 이번에는 네가 정보를 맡아줘."
    acceptance = "좋아. 내가 확인할게."
    follow_up = "고마워. 타일 순서에 영향을 주는 규칙이 있으면 알려줘."
    team_proposal = f"팀에서는 {fifth}가 정보를 맡자."
    models.update(
        {
            first: ScriptedLanguageModel(
                SCORE,
                lambda prompt: next_demo_speech(
                    prompt, "public", ("", "각자 점수와 정보 중 무엇을 맡을지 정해요.")
                ),
            ),
            second: ScriptedLanguageModel(
                SCORE,
                lambda prompt: next_demo_speech(
                    prompt, "whisper", ("", whisper), (acceptance, follow_up), to=third
                ),
            ),
            third: ScriptedLanguageModel(
                lambda prompt: INFORMATION if whisper in prompt else SCORE,
                lambda prompt: next_demo_speech(
                    prompt, "whisper", (whisper, acceptance),
                    (follow_up, "알겠어. 미리보기에서 그 부분부터 볼게."), to=second
                ),
            ),
            fourth: ScriptedLanguageModel(
                SCORE,
                lambda prompt: demo_room_speech(prompt, 1, ("", team_proposal)),
            ),
            fifth: ScriptedLanguageModel(
                lambda prompt: INFORMATION if team_proposal in prompt else SCORE,
                lambda prompt: demo_room_speech(
                    prompt, 1, (team_proposal, "그럼 내가 정보를 고를게.")
                ),
            ),
            sixth: ScriptedLanguageModel(SCORE, lambda prompt: demo_room_speech(prompt, 1)),
        }
    )
    return models


def make_demo_arena() -> Arena:
    initial_scores = {f"P{seat:02}": seat - 9 for seat in range(1, PLAYER_COUNT + 1)}
    return make_arena(initial_scores, demo_models(initial_scores), discussion_rounds=DEMO_DISCUSSION_ROUNDS)


def main() -> None:
    arena = make_demo_arena()
    initial_scores = arena.environment.scores
    parser = argparse.ArgumentParser(description="양자택일 5번 선택 모의 실행")
    parser.add_argument("--player", choices=initial_scores, help="이 참가자에게 보인 대화를 표시")
    args = parser.parse_args()
    play_choice_five(arena)
    scores = arena.environment.scores
    preview_prefix = f"{OBSERVATION_TAG} {PREVIEW.splitlines()[0]}"
    print(f"양자택일 5번 선택 · 모의 참가자 {arena.num_players}명")
    for message in arena.environment.get_observation(args.player):
        if message.msg_type in CHANNEL_NAMES:
            print(format_speech(message))
        elif message.msg_type == "room_move":
            print(f"[이동] {message.content}")
    print()
    print("참가자 | 승점 전 → 후 | 미리보기 수신")
    for player in arena.players:
        name = player.name
        memories = player.backend.memory.get_all_memories_as_text()
        received = any(memory.startswith(preview_prefix) for memory in memories)
        print(
            f"{name}    | {initial_scores[name]:3} → {scores[name]:3}  | "
            f"{'예' if received else '아니요'}"
        )


if __name__ == "__main__":
    main()
