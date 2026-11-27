"""Race to assemble three privately editable reflection-symmetric silhouettes."""

from base64 import b64decode
from collections import OrderedDict, deque
from copy import deepcopy
import json
from itertools import combinations
from math import atan2, cos, isfinite, sin

from ...match import Decision, Match, encode
from .puzzles import COLORS, accepted_axes, align_placement, board, judge, make_puzzles, piece_atlas, placement_polygon
from .tutorial import TUTORIAL_EXPLANATIONS, tutorial_image
from .workbench import measurement_atlas, workbench_image


WAIT = encode({"type": "wait"})
MAX_ACTION_SIZE = 8192

LEGACY_RULES = """대칭 퍼즐 · 개인전

파랑·빨강·초록, 세 색의 조각을 각각 하나의 선대칭 도형으로 만드세요.
각 색의 조각을 빠짐없이 한 번씩 쓰고, 서로 겹치거나 떨어지지 않게 변끼리 이어 붙여야 합니다.
대칭은 조각의 경계가 아닌 전체 도형과 빈 공간의 윤곽으로 판단합니다.
어느 방향이든 반사 대칭축이 하나 이상 있으면 됩니다. 대칭축이 여러 개여도 됩니다.
정해진 정답 윤곽을 따라 만드는 문제가 아니며, 조건을 만족하는 다른 모양도 정답입니다.
세 색을 모두 완성한 뒤 버저를 눌러 한 번에 검사받으세요.
참가자 수보다 한 명 적은 인원이 올바르게 완성하면 경기가 끝나고, 남은 마지막 한 명이 탈락합니다.

파랑은 2개, 빨강과 초록은 각각 3개인 실제 다각형 조각을 사용합니다.
조각은 뒤집을 수 없고 시계 방향으로 원하는 각도만큼 회전할 수 있습니다.
정해진 격자나 테두리 없이 조각을 자유롭게 놓으세요. x는 오른쪽, y는 아래쪽으로 증가하는 연속 좌표입니다.
회전 뒤 조각의 가장 왼쪽·위쪽을 기준으로 위치를 잡으므로, x/y는 회전한 조각 경계 상자의 왼쪽 위입니다.
음수와 소수 좌표도 허용하며, 그림의 표시 범위는 현재 배치에 맞춰 자동으로 조절됩니다.
작업 중에는 미완성 배치나 겹침을 저장할 수 있습니다.
매번 세 색의 전체 배치를 다음 JSON으로 교체하세요. 빠진 조각은 작업판에서 치웁니다.
{"type":"arrange","placements":{"blue":[{"piece":"B1","x":0,"y":1,"rotation":90}],"red":[],"green":[]},"submit":false}
세 색의 키를 모두 쓰세요. 좌표 배치에는 조각 ID·유한한 수 x/y·rotation만 지정합니다. 뒤집기 옵션은 없습니다.
각도는 360도로 나눈 나머지를 사용합니다.
정확히 붙일 때는 조각 그림의 꼭짓점 v번호와 변 e번호를 선택할 수 있습니다.
변 e번호는 같은 번호의 꼭짓점에서 다음 꼭짓점으로 가는 변입니다. 마지막 변은 v0으로 돌아갑니다.
좌표 배치 대신 {"piece":"B2","edge":0,"vertex":0,"to_piece":"B1","to_edge":1,"to_vertex":1} 형식도 허용합니다.
먼저 이 색의 목록에 배치한 to_piece의 변과 반대 방향으로 edge를 맞추고, vertex를 to_vertex에 붙입니다.
vertex와 to_vertex는 선택한 변의 끝점일 필요가 없습니다. 조각은 회전·이동만 하고 크기는 바꾸지 않습니다.
어떤 조각·변·꼭짓점을 붙일지는 직접 고르세요. 이 기능은 정답을 찾아주거나 잘못 고른 변을 고치지 않습니다.
submit:true이면 배치와 버저를 한 행동으로 제출합니다. false이면 작업만 저장합니다.
{"type":"wait"}는 모든 작업을 그대로 둡니다. 형식 오류도 이전 작업을 보존하며 정답으로 보정하지 않습니다.

작업 그림은 자신만 볼 수 있고, 다른 사람의 완성 그림도 경기 종료 전에는 공개하지 않습니다.
버저 검사에서는 세 색을 모두 완성했는지만 공개하며, 색별 정답 여부는 알려주지 않습니다.
실패하면 수정해 다시 제출할 수 있습니다. 이는 이 시뮬레이션의 재시도 정책입니다.
같은 생각 구간의 버저는 저장된 응답 시간이 짧은 순서로 처리하고, 동률은 시작 시 공개한
시드 기반 우선순위를 따릅니다. 마지막 생존 자리가 채워지면 뒤의 버저는 처리하지 않습니다.
별도 라운드·전체 시간 제한·대화·관계 평가는 없습니다. 호출 상한이 끝나면 스크립트 시연 행동으로 이어갑니다.
"""

MODERN_INSTRUCTIONS = """\n부분 접합도 가능합니다. 길이가 다른 변도 일부가 양의 길이만큼 맞닿으면 연결됩니다.
꼭짓점 하나만 닿는 점 접촉은 연결로 인정하지 않습니다.
첨부 이미지 여섯 장은 현재 blue·red·green 작업판, 이어서 같은 순서의 고정 조각 상세도입니다.
상세도는 조각의 변·꼭짓점을 읽는 자료이며 정답 배치나 색별 판정은 제공하지 않습니다.
한 생각 구간에서 초안과 추가 검토를 합쳐 최대 세 번 판단할 수 있습니다. 추가 검토에서는
내 초안의 작업판 그림을 다시 봅니다. 이는 버저 검사나 정답 힌트가 아닙니다.
최근 최종 전략 메모와 전체 검사 실패 기록을 참고해 이미 시도한 배치를 반복하지 마세요.
전체 검사 실패는 어느 색이 틀렸는지 알려주지 않습니다.
전략 메모에는 선택한 행동과 짧은 근거만 요약하세요.
"""
RULES = LEGACY_RULES + MODERN_INSTRUCTIONS

FOCUS_INSTRUCTIONS = """한 생각 구간에서는 지정된 한 색에 집중합니다. 다른 두 색의 작업은 그대로 보존됩니다.
이미지 순서: 이번 색의 현재 작업판, 모든 조각을 같은 배율로 그린 비교도, 조각별 확대도입니다.
비교도에서 크기를 비교하고, 확대도에서 꼭짓점·변 번호를 읽으세요. 확대도는 조각마다 배율이 다릅니다.
전체 도형과 빈 공간에 반사 대칭축이 있으면 되며 조각 경계는 대칭일 필요가 없습니다.
뒤집기 없이 시계 방향으로 자유롭게 회전하고 이동하세요. x/y는 회전한 경계 상자의 왼쪽 위입니다.
음수·소수 좌표도 허용합니다. 부분 접합도 가능합니다. 변 일부만 양의 길이로 맞닿아도 연결되며, 길이가 다른 변도 접합할 수 있습니다.
한 점만 닿으면 연결이 아닙니다. 겹침·미완성 작업도 저장할 수 있습니다.
초안과 추가 검토를 합쳐 최대 세 번 판단합니다. 추가 그림은 내 초안이며 정답 판정이 아닙니다.
같은 배치를 이동·회전하거나 JSON 표현만 바꾸어도 같은 방문으로 셉니다.
방문 기록은 정답·오답 판정이 아닙니다. 이미 맞는 색일 수도 있으므로 반복을 금지하지 않습니다.
반사축 후보를 정하고 양쪽 외곽의 볼록·오목한 특징이 서로 대응하는지 확인하세요. 비슷한 길이의 변을 맞추는 것만으로는 부족합니다.
검토에서 연결을 바꾸기 전 아직 대응하지 않는 구체적인 외곽 부분을 확인하세요. 근거는 짧게 요약하세요.
검토 전후 배치가 같은 도형이면 추가 검토 요청을 줄입니다. 확신하는 배치는 그대로 유지해도 됩니다.
버저는 세 색의 전체 작업을 한 번에 검사합니다. 전체 실패는 이번 색이 틀렸다는 뜻이 아닙니다.
전략 메모에는 선택한 행동과 짧은 근거만 요약하세요.
"""
FOCUS_RULES = """대칭 퍼즐 · 개인전
파랑·빨강·초록 세 색을 각각 하나의 선대칭 도형으로 만드세요. 파랑은 2개, 빨강과 초록은 각각 3개입니다.
각 색의 모든 조각을 한 번씩 사용해 겹침 없이 변으로 연결하고, 빈 공간을 포함한 전체 윤곽에 반사 대칭축을 만드세요.
정해진 답안 윤곽은 없으며 조건을 만족하는 다른 모양도 정답입니다.
한 구간에 한 색씩 파랑·빨강·초록 순서로 집중하며 나머지 작업은 보존합니다.
arrange_color는 이번 색의 조각 목록만 교체합니다. 전체 arrange도 허용하지만 모델 행동에서는 이번 색만 적용합니다.
작업 그림과 메모는 자신만 볼 수 있고 다른 사람의 작업은 경기 종료 전 공개하지 않습니다.
세 색을 모두 완성한 뒤 버저를 누르세요. 전체 완성 여부만 공개하며 색별 판정은 제공하지 않습니다.
실패하면 수정해 다시 제출할 수 있습니다. 이는 이 시뮬레이션의 재시도 정책입니다.
참가자보다 한 명 적은 인원이 완성하면 끝나고 남은 한 명이 탈락합니다.
같은 구간의 버저는 저장된 응답 시간이 짧은 순서로 처리하며 동률은 공개된 시드 우선순위를 따릅니다.
마지막 생존 자리가 채워지면 뒤의 버저는 처리하지 않습니다.
별도 라운드·전체 시간 제한·대화·관계 평가는 없습니다. 호출 상한 뒤에는 스크립트 시연 행동으로 이어갑니다.
""" + FOCUS_INSTRUCTIONS

WORKBENCH_INSTRUCTIONS = """\n세 번째 확대도 아래 표는 모든 원본 변의 길이와 방향을 보여주는 자·각도기입니다.
변의 방향각은 원본 조각의 rotation:0 기준이며, 현재 rotation을 더하면 작업판의 방향입니다.
방향표를 읽기 쉽도록 첫 조각 하나를 x:0, y:0, rotation:0의 기준으로 두고 나머지를 조립해 보세요.
전체를 함께 회전하거나 이동해도 대칭 여부는 같으므로 기준 조각의 위치를 계속 바꿀 필요는 없습니다.
표에서 길이와 각도를 비교하고 접합할 조각·변·꼭짓점은 직접 고르세요. 부분 접합에서는 긴 변의 나머지가 외곽에 남을 수 있습니다.
네 번째 이미지는 번호표와 조각 경계를 지운 전체 윤곽과 반사축 비교도입니다.
arrange_color에 선택 사항인 axis를 넣어 직접 정한 반사축을 비교할 수 있습니다.
axis는 x축에서 시계 방향으로 잰 도 단위 각도이며, 축은 현재 전체 도형의 면적 중심을 지납니다.
axis:90은 세로 반사축으로 왼쪽과 오른쪽을 비교합니다. axis:0은 가로 반사축으로 위와 아래를 비교합니다.
axis는 거울선의 방향이며 조각의 회전각이나 두 점이 서로 비춰지는 방향이 아닙니다.
null은 축을 지우며, 생략하면 이전 축을 유지합니다.
선대칭 도형의 반사축은 면적 중심을 지나므로 축의 각도만 고르면 됩니다.
반사본의 분홍 윤곽과 내 도형의 청록 윤곽을 비교하세요. 빈 공간도 대응해야 합니다.
이 그림은 내 선택을 그대로 비춘 것이며 정답 판정이나 자동으로 고른 축이 아닙니다.
반사본이 맞지 않으면 조각의 배치뿐 아니라 고른 축의 방향도 검토하세요. 기울어진 축도 허용됩니다.
배치 전체를 회전하면 대칭축도 같은 각도만큼 회전합니다. 화면의 90도 축을 고정해서 사용하지 마세요.
색의 조각이 세 개라면 첫 두 조각의 접합과 마지막 조각의 접합을 구분해서 검토하세요.
불일치가 남는데 같은 두 조각의 접합을 반복했다면 그 첫 접합을 풀고 다른 변이나 다른 두 조각부터 시작하세요.
길이가 같은 변을 끝까지 붙이는 경우뿐 아니라, 긴 변 일부를 붙이고 나머지를 외곽이나 빈 공간에 남기는 경우도 비교하세요.
추가 검토에서는 먼저 axis를 골라 반사본을 보고, 불일치를 찾으면 실제 접합을 바꾸세요.
전략 메모에는 선택한 축, 대응하지 않는 윤곽, 유지하거나 바꾼 접합만 짧게 요약하세요.
"""
WORKBENCH_RULES = FOCUS_RULES + WORKBENCH_INSTRUCTIONS
DIAGONAL_RULE = "초록은 G1의 가장 긴 변과 45도를 이루는 반사축이 하나 이상 있어야 합니다. 배치 전체를 회전해도 이 각도 차이는 같습니다."
ORIGINAL_RULES = (WORKBENCH_RULES + "\n빨강과 초록에는 이 시뮬레이션에서 새로 만든 조각 세트를 사용합니다.\n"
                  + DIAGONAL_RULE + "\n")
TWO_SURVIVOR_RULES = ORIGINAL_RULES.replace(
    "참가자보다 한 명 적은 인원이 완성하면 끝나고 남은 한 명이 탈락합니다.",
    "참가자 4명 중 먼저 완성한 2명이 생존하고 남은 2명은 탈락합니다.",
)


def _initial_protocol(match):
    log = match.resume_log
    if log is not None and log.resume:
        setup = next((json.loads(row["content"]) for row in log.events if row["msg_type"] == "sym_setup"), None)
        rules = next((row["content"] for row in log.events if row["msg_type"] == "rules"), None)
        if setup is not None:
            return setup["version"], rules or {2: LEGACY_RULES, 3: RULES, 4: FOCUS_RULES,
                                               5: WORKBENCH_RULES}[setup["version"]]
        if rules is not None:
            return (2 if rules == LEGACY_RULES else 3 if rules == RULES else 4 if rules == FOCUS_RULES else 5), rules
    return 5, TWO_SURVIVOR_RULES


def _puzzle_pack(match, rules):
    log = match.resume_log
    if log is not None and log.resume:
        saved_setup = next((row for row in log.events if row["msg_type"] == "sym_setup"), None)
        if saved_setup is not None:
            return json.loads(saved_setup["content"]).get("puzzle_pack", "broadcast")
    return "original" if rules in (ORIGINAL_RULES, TWO_SURVIVOR_RULES) else "broadcast"


def _next_saved_event(match):
    log = match.resume_log
    if log is not None and log.resume and log.events_seen < len(log.events):
        return log.events[log.events_seen]
    return None


def _upgrade_ready(match, kind="sym_tools"):
    log = match.resume_log
    if log is None or not log.resume:
        return False
    saved = _next_saved_event(match)
    return saved["msg_type"] == kind if saved is not None else not log.journal.remaining


def _show_tutorial(match):
    saved = _next_saved_event(match)
    value = (json.loads(saved["content"]) if saved is not None and saved["msg_type"] == "sym_tutorial" else
             {"version": 1, "board": tutorial_image(), "explanations": TUTORIAL_EXPLANATIONS})
    match.event("sym_tutorial", value)
    return value


def _tutorial_at_start(match):
    log = match.resume_log
    return log is None or not log.resume or _upgrade_ready(match, "sym_tutorial")


def _image_bytes(images):
    return tuple(b64decode(image["image"].partition(",")[2], validate=True) for image in images)


def placement_key(puzzle, placements):
    """Describe labeled rigid pieces up to translation/rotation, never reflection or grading."""
    polygons = sorted((placement["piece"], list(placement_polygon(puzzle, placement).exterior.coords)[:-1])
                      for placement in placements)
    if not polygons:
        return ()
    anchor = polygons[0][1]
    frames = []
    for index, (ox, oy) in enumerate(anchor):
        x, y = anchor[(index + 1) % len(anchor)]
        angle = atan2(y - oy, x - ox)
        c, s = cos(angle), sin(angle)
        frame = []
        for name, points in polygons:
            ring = tuple((round((x - ox) * c + (y - oy) * s, 6),
                          round(-(x - ox) * s + (y - oy) * c, 6)) for x, y in points)
            frame.append((name, min(ring[i:] + ring[:i] for i in range(len(ring)))))
        frames.append(tuple(frame))
    return min(frames)


def remember_visit(history, puzzle, placements, window):
    key = placement_key(puzzle, placements)
    previous = history.pop(key, None)
    history[key] = {"placements": deepcopy(placements), "count": previous["count"] + 1 if previous else 1,
                    "last_window": window}


def pair_history(puzzle, visits):
    """Describe repeated relative poses without testing correctness or proposing an answer."""
    result = []
    if len(puzzle["pieces"]) < 3:
        return result
    for pair in combinations(sorted(piece["id"] for piece in puzzle["pieces"]), 2):
        seen = {}
        for visit in visits:
            poses = [placement for placement in visit["placements"] if placement["piece"] in pair]
            if len(poses) == 2:
                key = placement_key(puzzle, poses)
                seen[key] = seen.get(key, 0) + visit["count"]
        if seen:
            result.append({"pieces": pair, "relative_poses": len(seen), "most_repeated": max(seen.values())})
    return result


def focus_prompt(name, window, color, placements, *, visits=(), notes=(), failures=(), race="",
                 last_verdict=None, tutorial=None, show_tutorial=False, workbench=False, axis=None, puzzle=None):
    """The same image-only focused task can also be used by an isolated practice probe."""
    prefix = color[0].upper()
    return (
        f"생각 구간 {window} · {name}. 이번 집중 색: {color} ({COLORS[color][0]}).\n{race}\n"
        f"내 마지막 전체 검사 결과: {encode(last_verdict)}. 내 이번 색의 현재 배치: {encode(placements)}\n"
        + FOCUS_INSTRUCTIONS
        + (WORKBENCH_INSTRUCTIONS + f"내 현재 반사축 각도: {encode(axis)} (이 구간 시작 시 저장값; 추가 검토 그림은 임시 답안의 axis 사용). "
           + f"최근 두 조각별 상대 배치 기록 (정답 판정 아님): {encode(pair_history(puzzle, visits))}\n"
           if workbench else "")
        + (DIAGONAL_RULE + "\n" if puzzle and puzzle.get("diagonal_axis") else "")
        + f'이번 색의 전체 배치를 {{"type":"arrange_color","color":"{color}","placements":[],"submit":false}}로 교체하세요. '
        "빠진 조각은 이번 색에서만 치웁니다. 다른 색은 바뀌지 않습니다. "
        "기존 전체 arrange 형식도 허용하지만 이번 색의 목록만 적용하고 다른 색 목록은 무시합니다. "
        'submit:true이면 세 색 전체 작업에 버저를 누릅니다. {"type":"wait"}는 작업을 유지합니다.\n'
        f'정확한 접합 형식 예시: {{"piece":"{prefix}2","edge":0,"vertex":0,"to_piece":"{prefix}1","to_edge":1,"to_vertex":1}}. '
        "목록에서 먼저 배치한 대상의 변과 반대 방향을 맞추고 지정 꼭짓점을 붙입니다. "
        "e번호는 같은 v번호에서 다음 꼭짓점으로 향하며 마지막 변은 v0으로 갑니다. "
        "선택한 꼭짓점은 선택한 변의 끝점일 필요가 없습니다. 이 번호는 형식 예시이며 정답 접합이 아닙니다.\n"
        + (("다섯 번째" if workbench else "네 번째")
           + " 이미지는 실제 퍼즐과 다른 연습 조각의 완성 예시입니다. 이번 구간의 추가 검토에도 보입니다.\n"
           if show_tutorial else "")
        + (tutorial["explanations"]["ko"] + "\n" if tutorial is not None else "")
        + f"내 이번 색의 최근 서로 다른 방문 배치 (최대 12개, count는 저장 횟수): {encode(list(visits))}\n"
        + f"내 최근 최종 전략 메모 (최대 3개): {encode(list(notes))}\n"
        + f"내 최근 전체 검사 실패 기록 (최대 12개, 색별 판정 아님): {encode(list(failures))}"
    )


def parse_action(text, puzzles):
    if not isinstance(text, str) or len(text) > MAX_ACTION_SIZE:
        raise ValueError("대칭 퍼즐 행동이 너무 크거나 문자열이 아닙니다.")
    value = json.loads(text)
    if value == {"type": "wait"}:
        return value
    single = isinstance(value, dict) and value.get("type") == "arrange_color"
    annotation = {}
    if single:
        if (set(value) not in ({"type", "color", "placements", "submit"},
                               {"type", "color", "placements", "submit", "axis"}) or not isinstance(value["color"], str)
                or value["color"] not in COLORS
                or type(value["submit"]) is not bool):
            raise ValueError("이번 색과 전체 조각 목록, submit 여부를 arrange_color JSON으로 지정하세요.")
        if "axis" in value:
            axis = value["axis"]
            if axis is not None and (type(axis) not in (int, float) or abs(axis) > 1_000_000 or not isfinite(axis)):
                raise ValueError("axis는 유한한 도 단위 각도 또는 null이어야 합니다.")
            annotation["axis"] = axis % 180 if axis is not None else None
        color = value["color"]
        value = {"type": "arrange", "placements": {key: value["placements"] if key == color else [] for key in COLORS},
                 "submit": value["submit"]}
    if (not isinstance(value, dict) or set(value) != {"type", "placements", "submit"}
            or value["type"] != "arrange" or type(value["submit"]) is not bool
            or not isinstance(value["placements"], dict) or set(value["placements"]) != set(COLORS)):
        raise ValueError("세 색의 전체 placements와 submit 여부를 arrange JSON으로 지정하세요.")
    normalized = {}
    for puzzle in puzzles:
        placements = value["placements"][puzzle["id"]]
        if not isinstance(placements, list) or len(placements) > len(puzzle["pieces"]):
            raise ValueError("해당 색의 조각 배치 목록을 지정하세요.")
        used, resolved = set(), []
        for placement in placements:
            if isinstance(placement, dict) and "to_piece" in placement:
                placement = align_placement(puzzle, placement, resolved)
            placement_polygon(puzzle, placement)
            if placement["piece"] in used:
                raise ValueError("각 조각 ID는 한 번만 지정하세요.")
            used.add(placement["piece"])
            resolved.append(placement)
        normalized[puzzle["id"]] = sorted(resolved, key=lambda placement: placement["piece"])
    if single:
        return {"type": "arrange_color", "color": color, "placements": normalized[color], "submit": value["submit"],
                **annotation}
    return {"type": "arrange", "placements": normalized, "submit": value["submit"]}


def _accepts(text, puzzles, focus_color=None):
    try:
        action = parse_action(text, puzzles)
        return action["type"] != "arrange_color" or action["color"] == focus_color
    except (ValueError, TypeError, RecursionError):
        return False


def merged_placements(action, previous, focus_color=None):
    if action["type"] == "wait":
        return deepcopy(previous)
    if action["type"] == "arrange" and focus_color is None:
        return action["placements"]
    color = focus_color or action["color"]
    placements = action["placements"][color] if action["type"] == "arrange" else action["placements"]
    return {**previous, color: placements}


def play(match: Match):
    players = list(match.players)
    version, rules = _initial_protocol(match)
    if (len(players) not in (3, 4) or len(set(players)) != len(players)
            or len(players) != 4 and rules == TWO_SURVIVOR_RULES):
        raise ValueError("새 대칭 퍼즐에는 서로 다른 참가자 4명이 필요합니다.")
    match.relationship_reviews_enabled = False
    match.model_observations = lambda name, events: [event for event in events if event.msg_type == "rules"]
    priority = match.rng.sample(players, len(players))
    pack = _puzzle_pack(match, rules)
    puzzles = make_puzzles(match.rng.randrange(2 ** 32), pack=pack)
    modern = version >= 3
    focus_start_window = 1 if version >= 4 else None
    initial_boards = {puzzle["id"]: board(puzzle, detailed=True) if modern else board(puzzle) for puzzle in puzzles}
    atlases = {puzzle["id"]: measurement_atlas(puzzle) if version >= 5 else piece_atlas(puzzle)
               for puzzle in puzzles} if modern else {}
    overviews = {puzzle["id"]: piece_atlas(puzzle, common_scale=True) for puzzle in puzzles} if version >= 4 else {}
    states = {name: {"placements": {color: [] for color in COLORS}, "boards": initial_boards.copy()}
              for name in players}

    def enable_workbench():
        for state in states.values():
            state.setdefault("axes", dict.fromkeys(COLORS))
            state["workbenches"] = {puzzle["id"]: workbench_image(
                puzzle, state["placements"][puzzle["id"]], axis=state["axes"][puzzle["id"]]) for puzzle in puzzles}

    if version >= 5:
        enable_workbench()
    own_notes = {name: deque(maxlen=3) for name in players}
    own_failures = {name: deque(maxlen=12) for name in players}
    visited = {name: {color: OrderedDict() for color in COLORS} for name in players}
    attempts, last_verdict = dict.fromkeys(players, 0), dict.fromkeys(players, None)
    finishes, winners, window = [], [], 0
    saved_setup = (next((json.loads(event["content"]) for event in match.resume_log.events
                         if event["msg_type"] == "sym_setup"), None)
                   if match.resume_log is not None and match.resume_log.resume else None)
    slots = saved_setup.get("survivors") if saved_setup is not None else 2 if rules == TWO_SURVIVOR_RULES else len(players) - 1
    if type(slots) is not int or slots not in (2, 3) or slots >= len(players):
        raise ValueError("저장된 대칭 퍼즐의 생존 인원이 올바르지 않습니다.")
    match.event("rules", rules)
    match.event("sym_setup", {"version": version, "players": players, "priority": priority,
                              "survivors": slots, "mode": "polygons", **({"thinking_passes": 3} if modern else {}),
                              **({"puzzle_pack": pack} if pack == "original" else {}),
                              **({"workbench": "participant_axis"} if version >= 5 else {}),
                              **({"focus_mode": "one_color", "focus_start_window": focus_start_window} if version >= 4 else {})})
    match.event("sym_puzzles", {"puzzles": [{"id": puzzle["id"], "label": puzzle["label"],
        "piece_ids": [piece["id"] for piece in puzzle["pieces"]], "board": initial_boards[puzzle["id"]],
        **({"details": atlases[puzzle["id"]]} if modern else {}),
        **({"overview": overviews[puzzle["id"]]} if version >= 4 else {})}
        for puzzle in puzzles]})
    tutorial, tutorial_window = None, None
    if modern and _tutorial_at_start(match):
        tutorial, tutorial_window = _show_tutorial(match), 1
    while len(winners) < slots:
        window += 1
        active = [name for name in players if name not in winners]
        focus_color = tuple(COLORS)[(window - focus_start_window) % 3] if version >= 4 else None
        match.event("sym_window", {"window": window, "active": active,
                                   **({"focus_color": focus_color} if focus_color else {})})
        while version < 5:
            saved = _next_saved_event(match)
            if saved is not None and saved["msg_type"] == "sym_tutorial" and tutorial is None and modern:
                tutorial, tutorial_window = _show_tutorial(match), window
                continue
            if not _upgrade_ready(match):
                break
            tools = json.loads(saved["content"]) if saved is not None else {
                "version": 5, "thinking_passes": 3, "focus_mode": "one_color",
                "focus_start_window": focus_start_window or window,
                "focus_color": tuple(COLORS)[(window - (focus_start_window or window)) % 3],
                "workbench": "participant_axis", "instructions": WORKBENCH_INSTRUCTIONS,
                "puzzles": [{"id": puzzle["id"], "details": measurement_atlas(puzzle),
                             "overview": piece_atlas(puzzle, common_scale=True)} for puzzle in puzzles]}
            match.event("sym_tools", tools)
            version = tools["version"]
            atlases = {puzzle["id"]: puzzle["details"] for puzzle in tools["puzzles"]}
            if version >= 4:
                focus_start_window = tools["focus_start_window"]
                overviews = {puzzle["id"]: puzzle["overview"] for puzzle in tools["puzzles"]}
                focus_color = tuple(COLORS)[(window - focus_start_window) % 3]
            if not modern:
                for state in states.values():
                    state["boards"] = {puzzle["id"]: board(puzzle, state["placements"][puzzle["id"]], detailed=True)
                                       for puzzle in puzzles}
                modern = True
            if version >= 5:
                enable_workbench()
        if modern and tutorial is None and _upgrade_ready(match, "sym_tutorial"):
            tutorial, tutorial_window = _show_tutorial(match), window
        example_images = [tutorial["board"]] if tutorial is not None and (version >= 5 or window == tutorial_window) else []
        scripted_times = {name: match.policy.randrange(1_000_000_000, 60_000_000_000) for name in active}
        decisions = {name: Decision(
            f"생각 구간 {window} · {name}. 파랑·빨강·초록 세 대칭 퍼즐을 모두 완성하세요.\n"
            f"생존 확정 순서: {encode(winners)}. 아직 참가 중: {encode(active)}. "
            f"공개 버저 횟수: {encode(attempts)}. 동률 우선순위: {encode(priority)}.\n"
            f"내 마지막 전체 검사 결과: {encode(last_verdict[name])}. "
            f"내 이전 작업 배치: {encode(states[name]['placements'])}\n"
            + ("앞의 이미지 여섯 장은 blue·red·green의 현재 작업판, 이어서 같은 순서의 고정 조각 상세도입니다. "
               if modern else "첨부 이미지 세 장은 차례로 blue·red·green의 조각 보관함과 나의 현재 작업판입니다. ")
            + "다른 참가자의 작업과 완성 예는 제공되지 않습니다. 각 색의 모든 조각을 겹침 없이 변으로 연결하고, "
            "빈 공간을 포함한 전체 모양에 방향 제한 없이 하나 이상의 반사 대칭축을 만드세요. "
            "조각 경계 자체가 대칭일 필요는 없으며, 세 색 모두 조건을 만족해야 생존합니다.\n"
            "그림의 x는 오른쪽, y는 아래쪽으로 증가하는 연속 좌표입니다. 음수·소수도 허용합니다. "
            "격자나 정해진 판의 테두리는 없으며 그림의 표시 범위는 배치에 맞춰 바뀝니다. "
            "시계 방향으로 원하는 각도를 회전할 수 있고 뒤집기는 금지합니다. "
            "x/y는 회전한 조각 경계 상자의 왼쪽 위입니다. "
            "정밀한 접합은 그림의 v꼭짓점/e변 번호로 선택하세요. "
            "e번호는 v번호에서 다음 꼭짓점으로 향하는 변입니다. "
            '{"piece":"B2","edge":0,"vertex":0,"to_piece":"B1","to_edge":1,"to_vertex":1}은 '
            "먼저 목록에 배치한 B1의 e1과 B2의 e0을 반대 방향으로 맞춘 뒤 B2의 v0을 B1의 v1에 붙입니다. "
            "형식 예시이며 이 변들이 정답이라는 뜻은 아닙니다. 변과 꼭짓점은 직접 고르세요. "
            "접합 기능은 선택한 변의 방향과 꼭짓점만 맞추며 겹침이나 대칭을 자동으로 고치지 않습니다.\n"
            '{"type":"arrange","placements":{"blue":[{"piece":"B1","x":0,"y":1,"rotation":90}],'
            '"red":[],"green":[]},"submit":false} 형식으로 세 색 전체 작업을 교체하세요. '
            "유지할 조각을 모두 포함하고 좌표 배치나 위의 접합 형식을 쓰세요. 빠진 조각은 치워지며 빈 목록은 그 색을 비웁니다. "
            "submit:true이면 세 색을 검사받도록 즉시 버저도 누릅니다. false이면 작업만 저장합니다. "
            '{"type":"wait"}는 전체 작업을 그대로 유지합니다. 실패한 답안은 고쳐 다시 제출할 수 있습니다.'
            + (MODERN_INSTRUCTIONS.replace("첨부 이미지 여섯 장", "앞의 이미지 여섯 장")
               + ("\n일곱 번째 이미지는 별도 연습 조각의 대칭 완성 예시입니다. 이번 생각 구간의 추가 검토에도 함께 보입니다."
                  if example_images else "")
               + ("\n" + tutorial["explanations"]["ko"] if tutorial is not None else "")
               + f"\n내 최근 최종 전략 메모 (최대 3개): {encode(list(own_notes[name]))}"
               + f"\n내 최근 전체 검사 실패 기록 (최대 12개): {encode(list(own_failures[name]))}"
               if modern else ""),
            encode({"type": "arrange", "placements": {puzzle["id"]: puzzle["solution"] for puzzle in puzzles},
                    "submit": True}), valid=lambda action: _accepts(action, puzzles), invalid_default=WAIT)
            for name in active}
        if focus_color:
            race = (f"생존 확정 순서: {encode(winners)}. 아직 참가 중: {encode(active)}. "
                    f"공개 버저 횟수: {encode(attempts)}. 동률 우선순위: {encode(priority)}.")
            decisions = {name: Decision(focus_prompt(
                name, window, focus_color, states[name]["placements"][focus_color],
                visits=list(visited[name][focus_color].values())[-12:], notes=own_notes[name], failures=own_failures[name],
                race=race + f" 내 보존 중인 다른 색 조각 수: {encode({color: len(states[name]['placements'][color]) for color in COLORS if color != focus_color})}.",
                last_verdict=last_verdict[name], tutorial=tutorial, show_tutorial=bool(example_images),
                workbench=version >= 5, axis=states[name].get("axes", {}).get(focus_color),
                puzzle=next(puzzle for puzzle in puzzles if puzzle["id"] == focus_color)),
                decisions[name].default, valid=lambda action: _accepts(action, puzzles, focus_color), invalid_default=WAIT)
                for name in active}
        elapsed = {}
        decision_start = len(match.events)
        pending_axes = {name: states[name].get("axes", {}).get(focus_color) for name in active}

        def draft_axis(name, action):
            if action["type"] == "arrange_color" and "axis" in action:
                pending_axes[name] = action["axis"]
            return pending_axes[name]

        def review_images(name, raw_draft):
            try:
                draft = parse_action(raw_draft, puzzles)
            except (ValueError, TypeError, RecursionError):
                draft = {"type": "wait"}
            placements = merged_placements(draft, states[name]["placements"], focus_color)
            if focus_color:
                puzzle = next(puzzle for puzzle in puzzles if puzzle["id"] == focus_color)
                return _image_bytes([board(puzzle, placements[focus_color], detailed=True),
                                     overviews[focus_color], atlases[focus_color]]
                                    + ([workbench_image(puzzle, placements[focus_color],
                                                        axis=draft_axis(name, draft))]
                                       if version >= 5 else []) + example_images)
            previews = [board(puzzle, placements[puzzle["id"]], detailed=True) for puzzle in puzzles]
            return _image_bytes(previews + [atlases[puzzle["id"]] for puzzle in puzzles] + example_images)

        def review_key(name, raw_draft):
            draft = parse_action(raw_draft, puzzles)
            placements = merged_placements(draft, states[name]["placements"], focus_color)
            puzzle = next(puzzle for puzzle in puzzles if puzzle["id"] == focus_color)
            key = placement_key(puzzle, placements[focus_color])
            if version < 5:
                return key
            axis = draft_axis(name, draft)
            anchor = min(placements[focus_color], key=lambda placement: placement["piece"], default=None)
            return key, round((axis - anchor["rotation"]) % 180, 6) if axis is not None and anchor else axis

        request_images = {}
        for name in active:
            views = ([states[name]["boards"][focus_color], overviews[focus_color], atlases[focus_color]] if focus_color else
                     [states[name]["boards"][puzzle["id"]] for puzzle in puzzles]
                     + ([atlases[puzzle["id"]] for puzzle in puzzles] if modern else []))
            if version >= 5:
                views.append(states[name]["workbenches"][focus_color])
            request_images[name] = _image_bytes(views + example_images)
        replies = match.decide_together("symmetry_arrange", decisions, response_times=elapsed,
            images_by_player=request_images,
            max_reviews=2 if modern else 0, review_images=review_images if modern else None,
            review_key=review_key if focus_color else None)
        final_notes = {}
        for event in match.events[decision_start:]:
            if event.msg_type == "decision_note" and event.agent_name in own_notes:
                value = json.loads(event.content)
                if value.get("phase") == "symmetry_arrange" and not value.get("review"):
                    final_notes[event.agent_name] = value["note"]
        for name, note in final_notes.items():
            own_notes[name].append({"window": window, "note": note})
        submitting = []
        for name in active:
            action = parse_action(replies[name], puzzles)
            if action["type"] == "wait":
                continue
            applied_focus = focus_color if name in elapsed else None
            placements = merged_placements(action, states[name]["placements"], applied_focus)
            previous = states[name]
            states[name] = {"placements": placements,
                           "boards": {puzzle["id"]: board(puzzle, placements[puzzle["id"]], detailed=True)
                                      if modern else board(puzzle, placements[puzzle["id"]]) for puzzle in puzzles}}
            if version >= 5:
                axes = dict(previous["axes"])
                if applied_focus:
                    axes[applied_focus] = draft_axis(name, action)
                states[name]["axes"] = axes
                states[name]["workbenches"] = {puzzle["id"]: workbench_image(
                    puzzle, placements[puzzle["id"]], axis=axes[puzzle["id"]]) for puzzle in puzzles}
            for puzzle in puzzles:
                if applied_focus is None or puzzle["id"] == applied_focus:
                    remember_visit(visited[name][puzzle["id"]], puzzle, placements[puzzle["id"]], window)
            match.event("sym_board", {"player": name, "window": window, **states[name],
                                      "submitted": action["submit"]}, private=[name], actor=name)
            if action["submit"]:
                submitting.append(name)
        submitting.sort(key=lambda name: (elapsed.get(name, scripted_times[name]), priority.index(name)))
        for name in submitting:
            attempts[name] += 1
            common = {"player": name, "window": window, "attempt": attempts[name],
                      "elapsed_ns": elapsed.get(name, scripted_times[name])}
            match.event("sym_buzz", common, actor=name)
            correct = all(judge(puzzle, states[name]["placements"][puzzle["id"]]) for puzzle in puzzles)
            last_verdict[name] = correct
            match.event("sym_verdict", {**common, "correct": correct, "reason": None if correct else "not_symmetric"}, actor=name)
            if not correct:
                own_failures[name].append({"window": window, "action": replies[name], "correct": False,
                                          **({"placements": deepcopy(states[name]["placements"])} if focus_color else {})})
            if correct:
                winners.append(name)
                finish = {**common, "rank": len(winners)}
                finishes.append(finish)
                match.event("sym_finish", finish)
                if len(winners) == slots:
                    break
    scores, axes = {}, {}
    for name in players:
        axes[name] = {}
        for puzzle in puzzles:
            found = accepted_axes(puzzle, states[name]["placements"][puzzle["id"]])
            axes[name][puzzle["id"]] = found[0] if found else None
        scores[name] = sum(axis is not None for axis in axes[name].values())
    match.event("sym_reveal", {"boards": deepcopy(states), "axes": axes})
    ranking = winners + [name for name in players if name not in winners]
    return {"ranking": ranking, "ranking_groups": [[name] for name in winners] + [ranking[slots:]], "survivors": winners,
            "eliminated": ranking[slots:], "scores": scores, "finish_turns": {row["player"]: row["window"] for row in finishes},
            "finishes": finishes, "turns": window, "attempts": attempts, "pieces": match.pieces.copy()}
