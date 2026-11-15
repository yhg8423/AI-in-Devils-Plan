"""Private, directional relationship ratings carried in match logs."""

from collections.abc import Mapping, Sequence
from typing import TypedDict


class Relationship(TypedDict):
    affinity: int
    trust: int
    reason: str


Ratings = dict[str, Relationship]
RelationshipState = dict[str, Ratings]
REASON_LIMIT = 160


def parse_ratings(data: object, player: str, players: Sequence[str]) -> Ratings:
    if not isinstance(data, dict):
        raise ValueError("Expected a relationship ratings object")
    ratings: Ratings = {}
    for other, entry in data.items():
        if other == player or other not in players or not isinstance(entry, dict):
            raise ValueError("Unknown relationship target")
        if entry.keys() != {"affinity", "trust", "reason"}:
            raise ValueError("Expected affinity, trust and reason")
        affinity, trust, reason = entry["affinity"], entry["trust"], entry["reason"]
        if any(type(score) is not int or not 0 <= score <= 100 for score in (affinity, trust)):
            raise ValueError("Relationship scores must be integers from 0 to 100")
        if not isinstance(reason, str) or not 0 < len(reason.strip()) <= REASON_LIMIT:
            raise ValueError("Invalid relationship note length")
        ratings[other] = {"affinity": affinity, "trust": trust, "reason": reason.strip()}
    return ratings


def format_ratings(ratings: Mapping[str, Relationship]) -> str:
    return "\n".join(f"{other} · 친밀도 {entry['affinity']}/100 · 신뢰도 {entry['trust']}/100 · {entry['reason']}"
                     for other, entry in ratings.items())
