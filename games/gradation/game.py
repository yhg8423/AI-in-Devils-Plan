"""Symmetric cup colors hide both an opponent's number and original position.

Broadcast rule source:
https://namu.moe/w/데블스%20플랜:%20데드%20어게인/6일차#s-5.1
The two-player single-duel route, seeded draw, tied-duel first-player retention,
and invalid/late preparation fallbacks are explicit simulation policies.
"""

from collections import Counter
from io import BytesIO
import json

import pygame

from games.match import Decision, Match, encode


COLORS = ("black", "silver", "gray", "white", "gray", "silver", "black")
COLOR_NAMES = tuple(dict.fromkeys(COLORS))
PREPARE_SECONDS = 300
TITLE = "6일차 감옥 매치 · 그라데이션"
RULES = """그라데이션 · 숫자와 통의 원래 위치를 숨기는 감옥 매치

3인 규칙: 첫 대진과 선공은 추첨합니다. 대결 승자는 대기자와 다음 대결을 치르고 첫 선공을 맡습니다.
패자는 대기합니다. 두 대결을 연속으로 이긴 한 명이 결승에 진출하고 나머지 두 명은 탈락합니다.
누적 2승과 다르며 다른 사람이 이기면 연승은 그 사람의 1승부터 다시 셉니다.
2인 변형: 한 대결의 승자가 결승에 진출하고 패자가 탈락합니다. 총점 동률이면 승자가 나올 때까지 재대결합니다.
2인 단일 대결은 현재 진행 인원을 위한 시뮬레이터 변형이며 방송에서 확인된 별도 2인 규칙은 아닙니다.

대결마다 두 참가자는 동시에 비공개로 5분 안에 숫자 7개를 배치합니다.
0~9 숫자 큐브가 각각 두 개씩 있습니다. 각 통에 하나씩 넣어 왼쪽→오른쪽 비감소 순서로 만들고 합은30이하입니다.
통의 색은 왼쪽부터 black,silver,gray,white,gray,silver,black입니다. 흰색은1개, 나머지는각2개입니다.
통은 원래 위치를 드러내지 않고 제출합니다. 상대는 제출 색과 남은 색별 개수만 알 수 있습니다.

대결은7라운드입니다. 선공이 미사용 통 하나를 먼저 제출하고, 그 색만 본 후공이 응답합니다.
두 사람이 모두 제출한 뒤에만 숫자를 동시에 공개합니다. 더 큰 숫자가1점, 같은 숫자는둘다0점입니다.
다음 라운드 선공은 직전 라운드 승자이고 비기면 기존 선공을 유지합니다. 사용한 통은 다시 낼 수 없습니다.
7라운드 총점이 높은 사람이 대결 승자입니다. 총점 동률 재대결은 승리나 연승 증가로 세지 않습니다.
재대결에서는 같은 대진·처음 선공을 유지하고 새 숫자를 배치합니다(첫 선공 유지 방식은 구현 정책).
대화·협상·관계 평가는 없으며 피스를 베팅·소모·추가 지급하지 않습니다.

배치 제출은 {"numbers":[0,1,2,3,4,5,6]}, 통 선택은 자기자리1~7의 {"slot":1}입니다.
배치가 잘못됐거나300초를 넘기면 미리 생성한 적법한 대체 배치를 사용합니다. 임의 정렬·수치 보정·감점은 하지 않습니다.
통 제출 제한 시간은 공개 규칙에서 확인되지 않아 추가하지 않습니다. 잘못된 선택·모델 호출 예산 소진은 적법한 스크립트 행동으로 이어갑니다.
상대에게 원래 슬롯 번호나 좌우 빈칸을 보여주지 않습니다. 공개 기록에도 색·공개 숫자만 남깁니다.
"""


def validate_numbers(numbers):
    if (not isinstance(numbers, list) or len(numbers) != 7
            or any(type(number) is not int or not 0 <= number <= 9 for number in numbers)
            or numbers != sorted(numbers) or sum(numbers) > 30
            or any(count > 2 for count in Counter(numbers).values())):
        raise ValueError("숫자7개: 0~9 정수, 각2개이하, 비감소, 합30이하가 필요합니다.")
    return numbers.copy()


def parse_layout(text):
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {"numbers"}:
        raise ValueError("numbers 배열을 지정하세요.")
    return validate_numbers(value["numbers"])


def accepts_layout(text):
    try:
        parse_layout(text)
        return True
    except (ValueError, TypeError, RecursionError):
        return False


def parse_slot(text, unused):
    value = json.loads(text)
    if (not isinstance(value, dict) or set(value) != {"slot"} or type(value["slot"]) is not int
            or value["slot"] not in unused):
        raise ValueError("미사용 통 번호를 slot 정수로 지정하세요.")
    return value["slot"]


def accepts_slot(text, unused):
    try:
        parse_slot(text, unused)
        return True
    except (ValueError, TypeError, RecursionError):
        return False


def random_layout(rng):
    inventory = list(range(10)) * 2
    while True:
        numbers = sorted(rng.sample(inventory, 7))
        if sum(numbers) <= 30:
            return numbers


class Duel:
    def __init__(self, players, numbers):
        if len(players) != 2 or len(set(players)) != 2 or set(numbers) != set(players):
            raise ValueError("그라데이션 대결에는 서로 다른 두 참가자의 배치가 필요합니다.")
        self.players = tuple(players)
        self.numbers = {player: validate_numbers(numbers[player]) for player in players}
        self.unused = {player: set(range(1, 8)) for player in players}
        self.scores = dict.fromkeys(players, 0)

    def remaining(self):
        return {player: {color: sum(COLORS[slot - 1] == color for slot in self.unused[player])
                         for color in COLOR_NAMES} for player in self.players}

    def take(self, player, slot):
        if type(slot) is not int or player not in self.players or slot not in self.unused[player]:
            raise ValueError("자신의 미사용 통을1~7로 선택하세요.")
        self.unused[player].remove(slot)
        return {"color": COLORS[slot - 1], "value": self.numbers[player][slot - 1]}

    def reveal(self, choices, leader):
        if set(choices) != set(self.players) or leader not in self.players:
            raise ValueError("두 사람의 제출과 유효한 선공이 필요합니다.")
        first, second = self.players
        winner = (first if choices[first]["value"] > choices[second]["value"] else
                  second if choices[first]["value"] < choices[second]["value"] else None)
        if winner is not None:
            self.scores[winner] += 1
        return winner, winner or leader


def board_image(player, players, numbers=None, unused=None, remaining=None, offered=None):
    """Render own original slots; render opponents as anonymous color counts only."""
    pygame.font.init()
    image = pygame.Surface((1100, 700))
    image.fill("#101820")
    title, font, small = (pygame.font.Font(None, size) for size in (36, 29, 23))
    def text(value, x, y, style=font, color="#f2e9da"):
        image.blit(style.render(str(value), True, color), (x, y))
    text("GRADATION / PRIVATE VIEW", 30, 25, title)
    text(f"Player: {player}", 30, 72)
    other = next(name for name in players if name != player)
    palette = {"black": "#20252d", "silver": "#697482", "gray": "#b4bac2", "white": "#f5f3ec"}
    text(f"Opponent: {other} / anonymous remaining cups", 30, 130)
    counts = (remaining or {name: dict(Counter(COLORS)) for name in players})[other]
    for index, color in enumerate(COLOR_NAMES):
        x = 35 + index * 264
        pygame.draw.rect(image, palette[color], (x, 180, 235, 90), border_radius=8)
        text(f"{color}: {counts[color]}", x + 15, 209, color="#f7f7f7" if color in ("black", "silver") else "#101820")
    text("No left/right positions or original opponent slot IDs are shown.", 30, 294, small)
    if offered:
        text("Current public offer: " + ", ".join(f"{name}: {color} / ?" for name, color in offered.items()), 30, 345)
    text("Your fixed slots (left to right, nondecreasing numbers)", 30, 405)
    own_unused = set(range(1, 8)) if unused is None else set(unused)
    for slot, color in enumerate(COLORS, 1):
        x = 30 + (slot - 1) * 152
        pygame.draw.rect(image, palette[color], (x, 455, 135, 120), border_radius=8)
        ink = "#f7f7f7" if color in ("black", "silver") else "#101820"
        text(numbers[slot - 1] if numbers is not None else "?", x + 55, 485, title, ink)
        text(f"slot {slot}", x + 35, 540, small, ink)
        if slot not in own_unused:
            pygame.draw.line(image, "#e15260", (x + 8, 465), (x + 127, 563), 5)
    text(f"Your sum: {sum(numbers) if numbers is not None else '?'} / 30", 30, 609)
    text("Used slots are crossed out only on your own private row.", 30, 654, small)
    output = BytesIO()
    pygame.image.save(image, output, "gradation-private.png")
    return output.getvalue()


def observations(name, events):
    return [event for event in events
            if (event.visible_to == "all" or name in event.visible_to)
            and (event.msg_type == "rules" or event.msg_type.startswith("grad_")
                 or event.msg_type in {"action", "decision_note", "invalid_action"})]


def play(match: Match):
    players = list(match.players)
    if len(players) not in (2, 3) or len(set(players)) != len(players):
        raise ValueError("그라데이션에는 서로 다른2~3명이 필요합니다.")
    match.relationship_reviews_enabled = False
    match.model_observations = observations
    order = match.rng.sample(players, len(players))
    duel_mode = len(players) == 2
    match.event("rules", RULES)
    match.event("grad_setup", {"version": 1, "players": players.copy(), "order": order.copy(),
                              "colors": list(COLORS), "goal": 2, "duel": duel_mode, "discussion": False,
                              "prepare_seconds": PREPARE_SECONDS})
    current, waiting, leader = order[:2], order[2] if len(order) == 3 else None, order[0]
    holder, streak, replay, number, games = None, 0, 0, 0, []
    while True:
        number += 1
        first_leader = leader
        match.event("grad_match", {"match": number, "players": current.copy(), "waiting": waiting,
                                  "leader": leader, "streak": streak, "replay": replay})
        defaults = {name: random_layout(match.policy) for name in current}
        times = {}
        prepared = match.decide_together("grad_prepare", {name: Decision(
            f"그라데이션 대결{number}. 참가자 {encode(current)}, 대기자 {waiting}, 첫 선공 {leader}. "
            f"현재 연승자 {holder}, 연승 {streak}. 300초 안에 자기 통7개의 숫자를 동시에 비공개 제출하세요. "
            '0~9 각2개 재고, 비감소, 합30이하. JSON {"numbers":[0,1,2,3,4,5,6]}만 제출하세요. '
            "상대의 배치는 볼 수 없습니다.", encode({"numbers": defaults[name]}),
            valid=accepts_layout, invalid_default=encode({"numbers": defaults[name]})) for name in current},
            response_times=times, images_by_player={name: (board_image(name, current),) for name in current}, max_reviews=0)
        numbers = {name: defaults[name] if times.get(name, 0) > PREPARE_SECONDS * 1_000_000_000
                   else parse_layout(prepared[name]) for name in current}
        duel = Duel(current, numbers)
        for name in current:
            match.event("grad_layout", {"match": number, "player": name, "numbers": numbers[name].copy(),
                                        "elapsed_ns": times.get(name, 0),
                                        "late": times.get(name, 0) > PREPARE_SECONDS * 1_000_000_000},
                        private=[name], actor=name)
            match.event("grad_ready", {"match": number, "player": name})
        for round_number in range(1, 8):
            match.event("grad_round", {"match": number, "round": round_number, "leader": leader,
                                      "scores": duel.scores.copy(), "remaining": duel.remaining()})
            follower = next(name for name in current if name != leader)
            choices, offered = {}, {}
            for name in (leader, follower):
                options = [encode({"slot": slot}) for slot in sorted(duel.unused[name])]
                default = encode({"slot": match.policy.choice(sorted(duel.unused[name]))})
                own = {"numbers": numbers[name], "unused_slots": sorted(duel.unused[name])}
                prompt = (f"그라데이션 대결{number} 라운드{round_number}. 선공 {leader}, 현재 점수 {encode(duel.scores)}. "
                          f"내 비공개 상태 {encode(own)}. 상대 정보는 익명 색 개수 {encode(duel.remaining())}. "
                          f"이번에 먼저 공개된 제출 색 {encode(offered)}. 아직 어느 제출 숫자도 공개되지 않았습니다. "
                          '자신의 미사용 통 하나를 {"slot":1} 형식으로 선택하세요. 원래 위치는 상대에게 숨겨집니다.')
                answer = match.decide(name, "grad_choose", prompt, default, options=options,
                                      valid=lambda text: accepts_slot(text, duel.unused[name]),
                                      images=(board_image(name, current, numbers[name], duel.unused[name],
                                                          duel.remaining(), offered),))
                slot = parse_slot(answer, duel.unused[name])
                choices[name] = duel.take(name, slot)
                offered[name] = choices[name]["color"]
                match.event("grad_selection", {"match": number, "round": round_number, "player": name, "slot": slot},
                            private=[name], actor=name)
                match.event("grad_offer", {"match": number, "round": round_number, "player": name,
                                          "color": choices[name]["color"]}, actor=name)
            winner, next_leader = duel.reveal(choices, leader)
            match.event("grad_reveal", {"match": number, "round": round_number, "choices": choices,
                                       "winner": winner, "scores": duel.scores.copy(), "next_leader": next_leader})
            leader = next_leader
        first, second = current
        winner = (first if duel.scores[first] > duel.scores[second] else
                  second if duel.scores[second] > duel.scores[first] else None)
        tied = winner is None
        if winner is not None:
            streak = streak + 1 if holder == winner else 1
            holder = winner
        result = {"match": number, "players": current.copy(), "scores": duel.scores.copy(), "winner": winner,
                  "tied": tied, "streak": streak, "waiting": waiting}
        games.append(result)
        match.event("grad_match_result", result)
        if tied:
            replay += 1
            leader = first_leader
            continue
        if duel_mode or streak >= 2:
            break
        loser = next(name for name in current if name != winner)
        current, waiting, leader, replay = [winner, waiting], loser, winner, 0
    eliminated = [name for name in order if name != winner]
    return {"ranking": [winner, *eliminated], "ranking_groups": [[winner], eliminated],
            "survivors": [winner], "finalists": [winner], "eliminated": eliminated,
            "scores": games[-1]["scores"].copy(), "games": games, "matches": number,
            "pieces": match.pieces.copy(), "pieces_awarded": dict.fromkeys(players, 0)}
