"""A simultaneous four-player race to complete a notched-strip puzzle."""

from ..match import Decision, Match, encode
from .diagram import piece_diagram
from .puzzle import Board, SIZE, SOURCE_URL, parse_action, piece_data, solution


RULES = """피스 퍼즐 · 4인 개인전

1. 목표
각자 같은 5종류의 피스 8개로 가로 4개·세로 4개가 만나는 격자를 완성합니다.
본인의 생존을 위해 경쟁하세요. 먼저 완성 제출한 3명은 생존하고 마지막 1명은 최종 탈락합니다.
대화·협상·관계 평가 없이 각자의 보드를 비공개로 조작합니다.

2. 홈과 방향
피스마다 홈 4개가 있습니다. side 0은 위에서 파인 홈, side 1은 아래에서 파인 홈입니다.
depth는 피스 높이를 100으로 보았을 때의 홈 깊이이며 33·58·83 중 하나입니다.
교차하는 두 홈은 서로 위·아래 방향이 달라야 하고 깊이 합이 100 이상이어야 합니다.
행 피스는 왼쪽→오른쪽, 열 피스는 위쪽→아래쪽으로 홈을 읽습니다.
reverse=true는 홈의 순서를 뒤집고, flip=true는 위·아래 홈 방향을 모두 뒤집습니다.

3. 진행
한 턴에 각자 배치·회수·버저 제출·패스 중 한 행동을 동시에 비공개로 선택합니다.
배치 시 가로 row 또는 세로 col의 1~4번 자리를 지정합니다. 이미 놓인 피스를 다시 배치할 수 있습니다.
자리에 다른 피스가 있으면 그 피스는 보관함으로 돌아옵니다. 회수는 놓인 피스에만 할 수 있습니다.
배치할 최종 자리와 방향을 지정합니다. 교차점의 홈 조건으로 결합을 판정합니다.
8개를 모두 놓고 16개 교차점이 맞더라도 submit으로 버저를 눌러야 완성 제출입니다.
오답 제출 뒤에는 보드를 수정해 다시 제출할 수 있습니다.

4. 순위
완성 제출한 턴이 빠른 사람이 앞섭니다. 같은 턴에 완성하면 시작 때 공개한 추첨 순서로 판정합니다.
3명의 생존자가 정해지면 종료하고 전원의 최종 보드를 공개합니다. 경기 도중 남의 보드는 볼 수 없습니다.
모델 호출 상한이 끝나면 스크립트 기본 행동으로 이어갑니다. 잘못된 모델 행동 형식은 패스로 처리합니다.
"""


def prompt(player, board, turn):
    return (
        f"피스 퍼즐 {turn}턴 · {player}. 먼저 완성 제출한 3명만 생존합니다. "
        "현재 자기 배치를 검산하고 생존에 필요한 한 행동을 고르세요. 다른 참가자의 배치는 비공개입니다.\n"
        "가로 row의 홈은 왼쪽→오른쪽, 세로 col의 홈은 위쪽→아래쪽으로 읽습니다. "
        "side 0=위쪽 홈, 1=아래쪽 홈. reverse는 홈 순서를 뒤집고 flip은 모든 side의 0·1을 뒤집습니다. "
        "교차점에서 방향이 반대이고 depth 합이 100 이상이어야 맞습니다. "
        "row의 c번째 홈과 col의 r번째 홈이 (r,c)에서 만납니다.\n"
        f"공통 피스: {encode(piece_data())}\n내 보드: {encode(board.snapshot())}\n"
        '배치: {"type":"place","piece":"K1","axis":"row","slot":1,"reverse":false,"flip":true}. '
        'axis는 row/col, slot은 1~4, 방향은 true/false입니다. 배치한 피스를 다시 이동·회전할 수 있고, '
        "목표 자리에 있던 다른 피스는 보관함으로 돌아옵니다. "
        '회수: {"type":"remove","piece":"K1"}. 버저: {"type":"submit"}. 패스: {"type":"pass"}.\n'
        "8개 피스의 16개 교차점이 모두 맞으면 버저를 누르세요. note에는 자신의 판단을 짧게 요약하세요."
    )


def play(match: Match):
    if len(match.players) != 4 or len(set(match.players)) != 4:
        raise ValueError("첫 피스 퍼즐에는 서로 다른 참가자 4명이 필요합니다.")
    match.relationship_reviews_enabled = False
    order = match.rng.sample(list(match.players), 4)
    boards = {name: Board() for name in match.players}
    target = solution()
    targets = {name: match.policy.sample(target, len(target)) for name in match.players}
    match.event("rules", RULES)
    match.event("exile_setup", {"version": 1, "players": list(match.players), "pieces": piece_data(),
                                "size": SIZE, "turn_order": order, "source_url": SOURCE_URL, "adapted": True})
    finished, finish_turns = [], {}
    turn = 0
    while len(finished) < 3:
        turn += 1
        active = [name for name in order if name not in finished]
        match.event("exile_turn", {"turn": turn, "active": active})
        decisions = {name: Decision(prompt(name, boards[name], turn),
                                    encode(boards[name].next_action(targets[name])),
                                    valid=boards[name].accepts, invalid_default=encode({"type": "pass"}))
                     for name in active}
        actions = match.decide_together("exile_move", decisions, images=(piece_diagram(),))
        for name in active:
            action = parse_action(actions[name])
            correct = boards[name].apply(action)
            match.event("exile_board", {"player": name, "turn": turn, **boards[name].snapshot()},
                        actor=name, private=[name])
            if action["type"] == "submit":
                if correct:
                    finished.append(name)
                    finish_turns[name] = turn
                match.event("exile_attempt", {"player": name, "turn": turn, "correct": correct,
                                              "place": len(finished) if correct else None}, actor=name)
    ranking = [*finished, *(name for name in order if name not in finished)]
    match.event("exile_reveal", {"boards": {name: {"player": name, "turn": turn, **board.snapshot()}
                                            for name, board in boards.items()}})
    return {"ranking": ranking, "survivors": ranking[:3], "eliminated": ranking[3:],
            "finish_turns": finish_turns, "turns": turn, "pieces": match.pieces.copy()}
