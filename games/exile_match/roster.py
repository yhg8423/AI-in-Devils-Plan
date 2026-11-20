"""Collect the first four exile entrants from an explicit campaign prefix."""

from collections.abc import Sequence
from pathlib import Path

from ..match import FIRST_EXILE, PRISON_STAGES, read_completed_match


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


def collect_second_exile_players(previous: Path, paths: Sequence[Path]) -> list[str]:
    """Join three first-match survivors with the next chronological exile entrant.

    If a main/prison result eliminates several people, its recorded elimination
    order determines the next arrival; remaining arrivals wait for later matches.
    """
    logs, entrants, counts = _campaign_entrants(paths)
    header, result, _ = read_completed_match(Path(previous), FIRST_EXILE)
    sources = header.get("from_matches")
    if (not isinstance(sources, list) or not sources or len(sources) >= len(logs)
            or any(not _points_to(source, log) for source, log in zip(sources, logs))):
        raise ValueError("이전 유배지 매치가 같은 캠페인의 선행 기록을 가리켜야 합니다.")
    first = collect_exile_players(logs[:len(sources)])
    survivors, eliminated = result.get("survivors"), result.get("eliminated")
    if (header.get("players") != first or not isinstance(survivors, list) or len(survivors) != 3
            or any(not isinstance(name, str) for name in survivors) or len(set(survivors)) != 3
            or not isinstance(eliminated, list) or len(eliminated) != 1
            or any(not isinstance(name, str) for name in eliminated)
            or set(survivors) & set(eliminated) or set(survivors + eliminated) != set(first)):
        raise ValueError("첫 유배지 매치의 생존자 3명과 탈락자 1명이 올바르지 않습니다.")
    if len(entrants) < 5 or (len(counts) > 1 and counts[-2] >= 5):
        raise ValueError("첫 유배지 이후 새 탈락자가 합류하는 첫 경기까지의 기록만 지정하세요.")
    return [*survivors, entrants[4]]
