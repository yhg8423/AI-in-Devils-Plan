"""Deterministic flag sets and flattened images without country-name metadata."""

from base64 import b64encode
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from random import Random

import pygame


COUNTRIES = tuple("ar au at be br ca ch cl cn co cz de dk es fi fr gb gr hu id ie in it jp kr mc mx my ng nl no nz pe pl pt ro ru se th tr tw ua us za ci td sn ml".split())
ASSETS = Path(__file__).with_name("assets")
WIDTH = 1000
GRID = {"columns": 5, "left": 25, "top": 70, "cell_width": 190, "cell_height": 132}


def make_puzzle(seed):
    rng = Random(seed)
    study = rng.sample(COUNTRIES, 10)
    remembered = rng.sample(study, 5)
    choices = remembered + rng.sample([code for code in COUNTRIES if code not in study], 20)
    rng.shuffle(choices)
    return {"study": study, "choices": choices,
            "correct": [index for index, code in enumerate(choices, 1) if code in remembered]}


@lru_cache(maxsize=len(COUNTRIES))
def _flag(code):
    source = pygame.image.load(ASSETS / f"{code}.png")
    image = pygame.Surface(source.get_size(), flags=pygame.SRCALPHA, depth=32)
    image.blit(source, (0, 0))
    return image


def _view(surface, alt, **extra):
    output = BytesIO()
    pygame.image.save(surface, output, "flags.png")
    png = output.getvalue()
    return {"id": sha256(png).hexdigest()[:16], "width": surface.get_width(), "height": surface.get_height(),
            "image": "data:image/png;base64," + b64encode(png).decode("ascii"), "alt": alt, **extra}


def _draw_flag(surface, code, centre, width=156, height=94):
    image = _flag(code)
    scale = min(width / image.get_width(), height / image.get_height())
    image = pygame.transform.smoothscale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
    rect = image.get_rect(center=centre)
    surface.blit(image, rect)
    pygame.draw.rect(surface, "#8b9aac", rect.inflate(2, 2), width=1)


def board(codes, *, study=False):
    pygame.font.init()
    rows = 2 if study else 5
    height = 360 if study else 760
    surface = pygame.Surface((WIDTH, height))
    surface.fill("#111c2c")
    title = pygame.font.Font(None, 35).render("REMEMBER THE FLAGS" if study else "CHOOSE FIVE FLAGS", True, "#f2deb0")
    surface.blit(title, (25, 20))
    font = pygame.font.Font(None, 25)
    for index, code in enumerate(codes):
        x, y = GRID["left"] + index % 5 * 190, GRID["top"] + index // 5 * 132
        pygame.draw.rect(surface, "#f7f4ec", (x, y, 181, 122), border_radius=6)
        label = font.render(str(index + 1), True, "#172239")
        surface.blit(label, (x + 8, y + 5))
        _draw_flag(surface, code, (x + 90, y + 69))
    return _view(surface, "국기 관찰 순서" if study else "번호가 붙은 국기 보기 25개",
                 grid={**GRID, "rows": rows})


def frame(code):
    surface = pygame.Surface((300, 210))
    surface.fill("#111c2c")
    _draw_flag(surface, code, (150, 105), width=260, height=160)
    return _view(surface, "관찰 중인 국기")
