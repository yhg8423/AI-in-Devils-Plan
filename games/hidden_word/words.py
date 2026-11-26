"""Original noun envelopes and candidate actions for a scripted demonstration."""

from hashlib import sha256
import json
import re


NOUN = re.compile(r"[가-힣]{1,16}")
ENVELOPES = (
    ("우산", "도서관", "기억", "강", "여행"),
    ("가을", "학교", "약속", "구름", "음식"),
    ("아침", "볼펜", "용기", "바다", "음악"),
    ("봄", "연필", "시장", "산", "휴식"),
    ("여름", "가위", "공원", "사랑", "운동"),
    ("겨울", "망치", "병원", "행복", "별"),
)
DECK_SHA256 = sha256(json.dumps(ENVELOPES, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
# These are candidate hint actions, never similarity scores. Demonstrations use
# the same cached dictionary embeddings as model-driven play.
ASSOCIATIONS = {
    "봄": ("꽃", "새싹", "봄철"), "여름": ("해변", "더위", "여름철"),
    "가을": ("낙엽", "추수", "가을철"), "겨울": ("눈", "추위", "겨울철"),
    "아침": ("출근", "일출", "새벽"),
    "연필": ("공책", "필기", "필기구"), "볼펜": ("펜", "필기", "문구"),
    "가위": ("종이", "절단", "절삭기"), "망치": ("못", "공구", "장도리"),
    "우산": ("장마", "비", "양산"),
    "학교": ("교실", "학생", "학원"), "병원": ("의사", "진료", "의료원"),
    "도서관": ("서가", "독서", "도서실"), "공원": ("벤치", "산책", "정원"),
    "시장": ("상인", "거래", "장터"),
    "사랑": ("마음", "연인", "애정"), "행복": ("미소", "만족", "기쁨"),
    "용기": ("위험", "도전", "담력"), "기억": ("과거", "회상", "추억"),
    "약속": ("시간", "신뢰", "다짐"),
    "바다": ("모래", "파도", "해양"), "산": ("등산", "봉우리", "산악"),
    "강": ("다리", "물줄기", "하천"), "별": ("밤", "우주", "항성"),
    "구름": ("하늘", "수증기", "운무"),
    "음식": ("주방", "식사", "요리"), "음악": ("무대", "선율", "악곡"),
    "여행": ("짐", "관광", "여정"), "운동": ("건강", "체육", "스포츠"),
    "휴식": ("의자", "재충전", "쉼"),
}
WORDS = tuple(word for envelope in ENVELOPES for word in envelope)


def is_noun_word(value):
    """Validate Hangul spelling shape; vector membership is checked separately."""
    return isinstance(value, str) and NOUN.fullmatch(value) is not None


def scripted_guess(clues, player_index, phase, vectors):
    """Infer from publicly revealed clues without reading the setter's chosen word."""
    if not clues:
        return WORDS[player_index % len(WORDS)]
    last = clues[-1]
    candidates = sorted(WORDS, key=lambda word: (-vectors.similarity(word, last), word))
    return candidates[(player_index + phase) % min(3, len(candidates))]
