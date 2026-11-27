"""Collect exile rosters from completed results and explicit campaign prefixes."""

from collections.abc import Sequence
from pathlib import Path

from ..match import (
    FIRST_EXILE, SECOND_EXILE, THIRD_EXILE, FOURTH_EXILE, FIFTH_EXILE, SIXTH_EXILE,
    SEVENTH_EXILE, EIGHTH_EXILE, PRISON_STAGES, read_completed_match,
)


STAGES = tuple(title for main, (prison, _) in PRISON_STAGES.items() for title in (main, prison))


def _points_to(source, expected: Path) -> bool:
    if not isinstance(source, str) or not source:
        return False
    # Raw logs use cwd-relative paths; exported logs use paths relative to their root.
    return any((base / source).resolve() == expected for base in (Path.cwd(), *expected.parents))


def _campaign_entrants(paths: Sequence[Path]):
    logs = [Path(path).resolve() for path in paths]
    if not logs or len(logs) > len(STAGES) or len(set(logs)) != len(logs):
        raise ValueError("1일차 메인부터 순서대로 서로 다른 완료 기록을 지정하세요.")

    entrants, counts = [], []
    for index, path in enumerate(logs):
        header, result, _ = read_completed_match(path, STAGES[index])
        links = ({"from_main": index - 1} if index % 2 else
                 {"from_main": index - 2, "from_prison": index - 1} if index else {})
        for name in ("from_main", "from_prison"):
            if name not in links:
                if name in header:
                    raise ValueError(f"{path}: 진행 순서에 맞지 않는 {name} 연결입니다.")
            elif not _points_to(header.get(name), logs[links[name]]):
                raise ValueError(f"{path}: {name}이 같은 캠페인의 선행 기록을 가리켜야 합니다.")

        players, eliminated = header.get("players"), result.get("eliminated")
        if (not isinstance(players, list) or not players
                or any(not isinstance(name, str) or not name or any(c.isspace() for c in name)
                       for name in players)
                or len(set(players)) != len(players)):
            raise ValueError(f"{path}: 참가자 명단이 올바르지 않습니다.")
        if (not isinstance(eliminated, list)
                or any(not isinstance(name, str) or name not in players for name in eliminated)
                or len(set(eliminated)) != len(eliminated)):
            raise ValueError(f"{path}: 탈락 명단은 해당 경기의 서로 다른 참가자여야 합니다.")
        if set(entrants) & set(players):
            raise ValueError(f"{path}: 이미 유배지에 들어간 참가자가 다시 출전할 수 없습니다.")
        entrants.extend(eliminated)
        counts.append(len(entrants))
    return logs, entrants, counts


def collect_exile_players(paths: Sequence[Path]) -> list[str]:
    """Import the first four entrants without changing source records."""
    _, entrants, _ = _campaign_entrants(paths)
    if len(entrants) > 4:
        raise ValueError("유배지 참가자가 4명을 초과합니다. 첫 4명이 모이는 시점까지의 기록만 지정하세요.")

    if len(entrants) != 4:
        raise ValueError(f"첫 유배지 매치에는 4명이 필요합니다. 현재 수집된 참가자는 {len(entrants)}명입니다.")
    return entrants


def _previous_sources(header, logs, *, allow_equal=False):
    sources = header.get("from_matches")
    if (not isinstance(sources, list) or not sources or len(sources) > len(logs)
            or (not allow_equal and len(sources) == len(logs))
            or any(not _points_to(source, log) for source, log in zip(sources, logs))):
        raise ValueError("이전 유배지 매치가 같은 캠페인의 선행 기록을 가리켜야 합니다.")
    return logs[:len(sources)]


def _survivors(header, result, players, count, message):
    survivors, eliminated = result.get("survivors"), result.get("eliminated")
    if (header.get("players") != players or not isinstance(survivors, list) or len(survivors) != count
            or any(not isinstance(name, str) for name in survivors) or len(set(survivors)) != count
            or not isinstance(eliminated, list) or len(eliminated) != len(players) - count
            or any(not isinstance(name, str) for name in eliminated)
            or set(survivors) & set(eliminated) or set(survivors + eliminated) != set(players)):
        raise ValueError(message)
    return survivors


def _previous_exile(header, previous, message):
    link = header.get("from_exile")
    if not isinstance(link, str) or not link:
        raise ValueError(message)
    path = next((path for base in (Path.cwd(), *previous.parents)
                 if (path := (base / link).resolve()).is_file()), None)
    if path is None:
        raise ValueError(message)
    return path


def collect_second_exile_players(previous: Path, paths: Sequence[Path]) -> list[str]:
    """Join three first-match survivors with the next chronological exile entrant.

    If a main/prison result eliminates several people, its recorded elimination
    order determines the next arrival; remaining arrivals wait for later matches.
    """
    logs, entrants, counts = _campaign_entrants(paths)
    header, result, _ = read_completed_match(Path(previous), FIRST_EXILE)
    first = collect_exile_players(_previous_sources(header, logs))
    survivors = _survivors(header, result, first, 3, "첫 유배지 매치의 생존자 3명과 탈락자 1명이 올바르지 않습니다.")
    if len(entrants) < 5 or (len(counts) > 1 and counts[-2] >= 5):
        raise ValueError("첫 유배지 이후 새 탈락자가 합류하는 첫 경기까지의 기록만 지정하세요.")
    return [*survivors, entrants[4]]


def collect_third_exile_players(previous: Path, paths: Sequence[Path]) -> list[str]:
    """Join two second-match survivors with arrivals six and seven, including queued arrivals."""
    logs, entrants, counts = _campaign_entrants(paths)
    previous = Path(previous).resolve()
    header, result, _ = read_completed_match(previous, SECOND_EXILE)
    sources = _previous_sources(header, logs, allow_equal=True)
    first = _previous_exile(header, previous, "두 번째 유배지 매치가 첫 유배지 매치의 기록을 가리켜야 합니다.")
    second = collect_second_exile_players(first, sources)
    survivors = _survivors(header, result, second, 2, "두 번째 유배지 매치의 생존자 2명과 탈락자 2명이 올바르지 않습니다.")
    if len(entrants) < 7 or (len(counts) > 1 and counts[-2] >= 7):
        raise ValueError("두 번째 유배지 이후 새 탈락자 2명이 모이는 첫 경기까지의 기록만 지정하세요.")
    return [*survivors, *entrants[5:7]]


def collect_fourth_exile_players(previous: Path, paths: Sequence[Path]) -> list[str]:
    """Join three third-match survivors with arrival eight, which may already be queued."""
    logs, entrants, counts = _campaign_entrants(paths)
    previous = Path(previous).resolve()
    header, result, _ = read_completed_match(previous, THIRD_EXILE)
    sources = _previous_sources(header, logs, allow_equal=True)
    second = _previous_exile(header, previous, "세 번째 유배지 매치가 두 번째 유배지 매치의 기록을 가리켜야 합니다.")
    third = collect_third_exile_players(second, sources)
    survivors = _survivors(header, result, third, 3, "세 번째 유배지 매치의 생존자 3명과 탈락자 1명이 올바르지 않습니다.")
    if len(entrants) < 8 or (len(counts) > 1 and counts[-2] >= 8):
        raise ValueError("세 번째 유배지 이후 새 탈락자가 합류하는 첫 경기까지의 기록만 지정하세요.")
    return [*survivors, entrants[7]]


def collect_fifth_exile_players(previous: Path, paths: Sequence[Path], *, legacy=False) -> list[str]:
    """After Day 4 main, join two fence survivors with arrivals nine and ten.

    Only existing replays/resumes may use the former three-survivor schedule.
    """
    logs, entrants, counts = _campaign_entrants(paths)
    if not legacy and len(logs) != 7:
        raise ValueError("대칭 퍼즐은 4일차 메인 이후입니다. 1일차 메인부터 4일차 메인까지의 기록을 지정하세요.")
    previous = Path(previous).resolve()
    header, result, _ = read_completed_match(previous, FOURTH_EXILE)
    sources = _previous_sources(header, logs, allow_equal=True)
    third = _previous_exile(header, previous, "네 번째 유배지 매치가 세 번째 유배지 매치의 기록을 가리켜야 합니다.")
    fourth = collect_fourth_exile_players(third, sources)
    count = 3 if legacy else 2
    survivors = _survivors(header, result, fourth, count,
        f"네 번째 유배지 매치의 생존자 {count}명이 올바르지 않습니다. 새 일정은 울타리 치기를 4인→2인으로 다시 실행하세요.")
    needed = 9 if legacy else 10
    if ((len(entrants) < needed if legacy else len(entrants) != needed)
            or (len(counts) > 1 and counts[-2] >= needed)):
        raise ValueError(f"네 번째 유배지 이후 새 탈락자 {needed - 8}명이 모이는 첫 경기까지의 기록만 지정하세요.")
    return [*survivors, *entrants[8:needed]]


def collect_sixth_exile_players(previous: Path, paths: Sequence[Path]) -> list[str]:
    """Join two symmetry survivors with Day 4 prison and Day 5 main arrivals."""
    logs, entrants, counts = _campaign_entrants(paths)
    if len(logs) != 9:
        raise ValueError("만국기에는 1일차 메인부터 5일차 메인까지의 완료 기록을 지정하세요.")
    previous = Path(previous).resolve()
    header, result, _ = read_completed_match(previous, FIFTH_EXILE)
    sources = _previous_sources(header, logs, allow_equal=True)
    fourth = _previous_exile(header, previous, "대칭 퍼즐이 네 번째 유배지 매치를 가리켜야 합니다.")
    fifth = collect_fifth_exile_players(fourth, sources)
    survivors = _survivors(header, result, fifth, 2,
                          "대칭 퍼즐의 생존자 2명이 올바르지 않습니다. 새 일정으로 대칭 퍼즐을 다시 실행하세요.")
    if len(entrants) != 12 or counts[-2] >= 12:
        raise ValueError("만국기는 대칭 퍼즐 생존자 2명과 4일차 감옥·5일차 메인 탈락자 2명으로 4명이 모여야 합니다.")
    return [*survivors, *entrants[10:12]]


def collect_seventh_exile_players(previous: Path, paths: Sequence[Path]) -> list[str]:
    """Join three Flags survivors with the Day 5 prison elimination."""
    logs, entrants, _ = _campaign_entrants(paths)
    if len(logs) != 10:
        raise ValueError("네모 세기에는 1일차 메인부터 5일차 감옥까지의 완료 기록을 지정하세요.")
    previous = Path(previous).resolve()
    header, result, _ = read_completed_match(previous, SIXTH_EXILE)
    sources = _previous_sources(header, logs)
    fifth = _previous_exile(header, previous, "만국기가 대칭 퍼즐의 기록을 가리켜야 합니다.")
    sixth = collect_sixth_exile_players(fifth, sources)
    survivors = _survivors(header, result, sixth, 3, "만국기의 생존자 3명과 탈락자 1명이 올바르지 않습니다.")
    _, earlier_entrants, _ = _campaign_entrants(sources)
    arrivals = entrants[len(earlier_entrants):]
    if len(arrivals) != 1:
        raise ValueError("만국기 이후 5일차 감옥 탈락자 1명이 합류해야 합니다.")
    return [*survivors, *arrivals]


def collect_eighth_exile_players(previous: Path, paths: Sequence[Path]) -> list[str]:
    """Keep the two rectangle survivors, ordered by their original exile entry."""
    logs, entrants, _ = _campaign_entrants(paths)
    if len(logs) != 10:
        raise ValueError("포인트 오목에는 5일차 감옥까지의 완료 기록만 지정하세요.")
    previous = Path(previous).resolve()
    header, result, _ = read_completed_match(previous, SEVENTH_EXILE)
    sources = _previous_sources(header, logs, allow_equal=True)
    if len(sources) != len(logs):
        raise ValueError("네모 세기와 포인트 오목은 같은 선행 경기 목록을 사용해야 합니다.")
    sixth = _previous_exile(header, previous, "네모 세기가 만국기의 기록을 가리켜야 합니다.")
    seventh = collect_seventh_exile_players(sixth, sources)
    survivors = _survivors(header, result, seventh, 2, "네모 세기의 생존자 2명이 올바르지 않습니다.")
    return sorted(survivors, key=entrants.index)


def read_exile_returnee(path: Path, main_path=None, prison_path=None):
    """Verify the complete exile chain before admitting its winner to Day 6."""
    path = Path(path).resolve()
    header, result, _ = read_completed_match(path, EIGHTH_EXILE)
    sources = header.get("from_matches")
    if not isinstance(sources, list) or len(sources) != 10:
        raise ValueError("포인트 오목의 5일차 감옥까지 선행 기록이 필요합니다.")
    logs = []
    for source in sources:
        if not isinstance(source, str) or not source:
            raise ValueError("포인트 오목의 선행 기록 경로가 올바르지 않습니다.")
        resolved = next((candidate for base in (Path.cwd(), *path.parents)
                         if (candidate := (base / source).resolve()).is_file()), None)
        if resolved is None:
            raise ValueError("포인트 오목의 선행 기록을 찾을 수 없습니다.")
        logs.append(resolved)
    seventh = _previous_exile(header, path, "포인트 오목이 네모 세기의 기록을 가리켜야 합니다.")
    players = collect_eighth_exile_players(seventh, logs)
    survivors = _survivors(header, result, players, 1, "포인트 오목의 최종 생존자가 올바르지 않습니다.")
    winner = survivors[0]
    balances, awards = result.get("pieces"), result.get("pieces_awarded")
    if (result.get("returnee") != winner or not isinstance(balances, dict) or not isinstance(awards, dict)
            or type(balances.get(winner)) is not int or balances[winner] != 5
            or type(awards.get(winner)) is not int or awards[winner] != 5):
        raise ValueError("포인트 오목 복귀자는 피스 5개를 받아야 합니다.")
    if main_path is not None and logs[-2] != Path(main_path).resolve():
        raise ValueError("복귀자와 본선은 같은 5일차 메인 기록을 이어야 합니다.")
    if prison_path is not None and logs[-1] != Path(prison_path).resolve():
        raise ValueError("복귀자와 본선은 같은 5일차 감옥 기록을 이어야 합니다.")
    return winner, 5
