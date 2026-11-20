"""Generated picture pairs, flattened identically for model and replay viewing."""

from base64 import b64decode, b64encode
from binascii import Error as Base64Error
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import pygame


WIDTH, HEIGHT = 960, 640
THEMES = ("fishing", "market", "beach", "cafe")
ASSET_ROOT = Path(__file__).with_name("assets") / "generated"
PNG_PREFIX = "data:image/png;base64,"


def _targets(value):
    if (not isinstance(value, list) or len(value) != 5
            or any(not isinstance(target, dict) or set(target) != {"id", "x", "y", "w", "h"}
                   or not isinstance(target["id"], str) or not target["id"]
                   or any(type(target[key]) is not int for key in ("x", "y", "w", "h"))
                   or target["w"] <= 0 or target["h"] <= 0
                   or not 0 <= target["x"] < target["x"] + target["w"] <= WIDTH
                   or not 0 <= target["y"] < target["y"] + target["h"] <= HEIGHT
                   for target in value)
            or len({target["id"] for target in value}) != 5):
        raise ValueError("생성된 그림에는 서로 다른 정답 영역 5개가 필요합니다.")
    for index, target in enumerate(value):
        for other in value[index + 1:]:
            if (target["x"] < other["x"] + other["w"] and other["x"] < target["x"] + target["w"]
                    and target["y"] < other["y"] + other["h"] and other["y"] < target["y"] + target["h"]):
                raise ValueError("생성된 그림의 정답 영역은 서로 겹칠 수 없습니다.")
    return deepcopy(value)


def _asset_image(name):
    if (not isinstance(name, str) or not name
            or (ASSET_ROOT / name).resolve().parent != ASSET_ROOT.resolve()):
        raise ValueError("생성된 그림 파일은 assets/generated 안에 있어야 합니다.")
    try:
        image = pygame.image.load(str(ASSET_ROOT / name))
    except (FileNotFoundError, OSError, pygame.error) as error:
        raise ValueError(f"생성된 그림 파일을 읽을 수 없습니다: {name}") from error
    scaled = pygame.transform.smoothscale(image, (WIDTH, HEIGHT))
    opaque = pygame.Surface((WIDTH, HEIGHT))
    opaque.fill("#ffffff")
    opaque.blit(scaled, (0, 0))
    return opaque


def _png(surface):
    output = BytesIO()
    pygame.image.save(surface, output, "picture.png")
    return output.getvalue()


@lru_cache(maxsize=len(THEMES))
def _asset_scene(theme):
    try:
        manifest = json.loads((ASSET_ROOT / "manifest.json").read_text(encoding="utf-8"))
        if manifest["version"] != 1:
            raise ValueError("지원하지 않는 생성 그림 목록 버전입니다.")
        entry = manifest["scenes"][theme]
        targets = _targets(entry["targets"])
        original, edited = (_asset_image(entry[key]) for key in ("original", "edited"))
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("틀린 그림 찾기의 생성 그림과 manifest.json이 필요합니다.") from error
    changed = original.copy()
    for target in targets:
        area = pygame.Rect(*(target[key] for key in ("x", "y", "w", "h")))
        before = pygame.surfarray.array3d(original.subsurface(area))
        after = pygame.surfarray.array3d(edited.subsurface(area))
        if not (before != after).any():
            raise ValueError(f"생성된 그림의 {target['id']} 영역에 실제 변화가 없습니다.")
        changed.blit(edited, area.topleft, area)
    original_png, changed_png = _png(original), _png(changed)
    return {
        "id": sha256(original_png + changed_png).hexdigest()[:16], "theme": theme,
        "original": PNG_PREFIX + b64encode(original_png).decode("ascii"),
        "changed": PNG_PREFIX + b64encode(changed_png).decode("ascii"), "targets": targets,
    }


def make_scene(seed, round_number=1):
    """Select a fixed illustrated pair; the referee's regions never enter views."""
    if type(seed) is not int or type(round_number) is not int or round_number < 1:
        raise ValueError("그림 시드와 1 이상의 라운드 정수가 필요합니다.")
    # ponytail: four fixed picture pairs; add authored pairs if repeated overtime needs more art.
    return deepcopy(_asset_scene(THEMES[(round_number - 1) % len(THEMES)]))


def picture(scene, changed=False):
    return {"id": scene["id"], "theme": scene["theme"], "width": WIDTH, "height": HEIGHT,
            "image": scene["changed" if changed else "original"]}


def render_picture(view):
    """Return the replay's exact PNG bytes, also accepting older vector replays."""
    if "image" in view:
        image = view["image"]
        if not isinstance(image, str) or not image.startswith(PNG_PREFIX):
            raise ValueError("그림은 자체 포함 PNG 데이터여야 합니다.")
        try:
            encoded = b64decode(image[len(PNG_PREFIX):], validate=True)
            surface = pygame.image.load(BytesIO(encoded))
            if not encoded.startswith(b"\x89PNG\r\n\x1a\n") or surface.get_size() != (view["width"], view["height"]):
                raise ValueError("PNG 그림 크기가 표시 정보와 일치하지 않습니다.")
        except (Base64Error, pygame.error) as error:
            raise ValueError("PNG 그림 데이터를 읽을 수 없습니다.") from error
        return encoded
    surface = pygame.Surface((view["width"], view["height"]))
    for shape in view["shapes"]:
        kind = shape["kind"]
        if kind in ("rect", "ellipse"):
            getattr(pygame.draw, kind)(surface, shape["fill"],
                                       (shape["x"], shape["y"], shape["w"], shape["h"]))
        elif kind == "polygon":
            pygame.draw.polygon(surface, shape["fill"], shape["points"])
        elif kind == "line":
            pygame.draw.lines(surface, shape["stroke"], False, shape["points"], shape["width"])
        else:
            raise ValueError(f"지원하지 않는 그림 도형: {kind}")
    return _png(surface)


def judge_marks(scene, marks):
    """Score each changed region at most once, even for multiple nearby marks."""
    if (not isinstance(marks, list) or len(marks) > 5
            or any(not isinstance(mark, dict) or set(mark) != {"x", "y"}
                   or type(mark["x"]) is not int or not 0 <= mark["x"] < WIDTH
                   or type(mark["y"]) is not int or not 0 <= mark["y"] < HEIGHT for mark in marks)):
        raise ValueError("그림 안의 정수 x·y 좌표를 최대 5개 지정하세요.")
    claimed = set()
    answers = []
    for mark in marks:
        target = next((target for target in scene["targets"]
                       if target["id"] not in claimed
                       and target["x"] <= mark["x"] < target["x"] + target["w"]
                       and target["y"] <= mark["y"] < target["y"] + target["h"]), None)
        if target is not None:
            claimed.add(target["id"])
        answers.append({**mark, "correct": target is not None, "target": target["id"] if target else None})
    return {"score": len(claimed), "marks": answers, "targets": deepcopy(scene["targets"])}
