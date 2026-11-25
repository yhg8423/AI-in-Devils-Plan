"""Load official Korean fastText word vectors and calculate cosine locally."""

import argparse
from functools import lru_cache
import gzip
from hashlib import file_digest, sha256
from importlib.metadata import version
import json
from math import isfinite
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from urllib.request import urlopen
import warnings

import numpy as np

from .words import is_noun_word


MODEL_ID = "fasttext-cc-ko-300"
SOURCE = "https://fasttext.cc/docs/en/crawl-vectors.html"
DOWNLOAD = "https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.ko.300.vec.gz"
ARCHIVE_SHA256 = "9d71f0ae144e0f89dd233bfa7eca421be26bd1e5dd18e2cc56888a04be982d97"
DIMENSIONS = 300
VOCABULARY = 2_000_000
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "runs/models/hidden-word/fasttext-cc-ko-300"
SETUP = "uv run --locked --python 3.12 python -m games.hidden_word.vectors --download"
NOUN_FILTER = f"kiwipiepy-{version('kiwipiepy')}/model-{version('kiwipiepy-model')}/cong/NNG/oov=false"
BLOCK_ROWS = 8192
SCORE_CEILING = 99.9


def normalized_score(similarity, maximum):
    """Express closeness relative to the best other noun, capped at 99.9."""
    if not isfinite(maximum) or maximum <= 0:
        raise ValueError("보정 기준 유사도는 유한한 양수여야 합니다.")
    if similarity is None:
        return None
    if not isfinite(similarity):
        raise ValueError("보정할 유사도는 유한한 수치여야 합니다.")
    return min(SCORE_CEILING, max(0.0, similarity / maximum * 100))


@lru_cache(maxsize=1)
def _noun_analyzer():
    from kiwipiepy import Kiwi
    return Kiwi(num_workers=1, model_type="cong")


@lru_cache(maxsize=32768)
def _common_noun(word):
    if not is_noun_word(word):
        return False
    tokens = _noun_analyzer().tokenize(word)
    return bool(tokens) and all(token.tag == "NNG" and not token.oov for token in tokens) and "".join(token.form for token in tokens) == word


class WordVectors:
    def __init__(self, words, values, metadata=None):
        words = tuple(words)
        values = np.asarray(values, dtype="<f4")
        if (not words or any(not isinstance(word, str) or not word for word in words)
                or len(set(words)) != len(words) or values.ndim != 2
                or values.shape[0] != len(words) or values.shape[1] == 0):
            raise ValueError("단어와 유한한 벡터 행렬이 필요합니다.")
        # Keep the 2M × 300 matrix on disk; use float64 only for bounded blocks.
        norms = np.empty(len(words), dtype=np.float64)
        digest = sha256(json.dumps(words, ensure_ascii=True, separators=(",", ":")).encode())
        digest.update(b"\0")
        for start in range(0, len(words), BLOCK_ROWS):
            block = values[start:start + BLOCK_ROWS]
            if not np.isfinite(block).all():
                raise ValueError("벡터에는 유한한 수치만 사용할 수 있습니다.")
            norms[start:start + len(block)] = np.linalg.norm(block.astype(np.float64), axis=1)
            digest.update(memoryview(block).cast("B"))
        if np.any(norms == 0):
            raise ValueError("길이가 0인 벡터는 사용할 수 없습니다.")
        values.flags.writeable = False
        self._vectors, self._norms = values, norms
        self._words = words
        self._indices = {word: index for index, word in enumerate(words)}
        self._nearest = {}
        self.metadata = {**(metadata or {"id": "custom-fasttext"}),
                         "sha256": digest.hexdigest(), "dimensions": values.shape[1],
                         "vocabulary": len(words), "score": "cosine*100", "nearest_filter": NOUN_FILTER}

    def __contains__(self, word):
        return word in self._indices

    def is_hint(self, word):
        """Use the same dictionary-attested common nouns for hints and search."""
        return isinstance(word, str) and word in self and _common_noun(word)

    def similarity(self, first, second):
        left, right = self._indices[first], self._indices[second]
        cosine = np.dot(self._vectors[left].astype(np.float64), self._vectors[right].astype(np.float64))
        cosine /= self._norms[left] * self._norms[right]
        # Clamp only floating-point drift outside cosine's mathematical bounds.
        return float(np.clip(cosine, -1, 1) * 100)

    def nearest(self, word):
        """Find the closest eligible noun in the entire vocabulary, excluding itself."""
        if word not in self._nearest:
            target = self._indices[word]
            query = self._vectors[target].astype(np.float64) / self._norms[target]
            scores = np.empty(len(self._words), dtype=np.float64)
            for start in range(0, len(scores), BLOCK_ROWS):
                block = self._vectors[start:start + BLOCK_ROWS].astype(np.float64)
                scores[start:start + len(block)] = (block @ query) / self._norms[start:start + len(block)]
            for index in np.argsort(-scores, kind="stable"):
                candidate = self._words[index]
                if candidate != word and self.is_hint(candidate):
                    self._nearest[word] = {"word": candidate, "similarity": self.similarity(word, candidate)}
                    break
            else:
                raise ValueError(f"{word!r}와 비교할 수 있는 다른 명사가 fastText 사전에 없습니다.")
        return self._nearest[word].copy()


def read_fasttext(stream, destination, *, dimensions=DIMENSIONS, vocabulary=VOCABULARY):
    """Stream the complete official text export into a memory-mapped NumPy file."""
    if tuple(map(int, stream.readline().split())) != (vocabulary, dimensions):
        raise ValueError("fastText 원본의 어휘 수·차원이 일치하지 않습니다.")
    values = np.lib.format.open_memmap(destination, mode="w+", dtype="<f4", shape=(vocabulary, dimensions))
    words = []
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        for index in range(vocabulary):
            word, separator, numbers = stream.readline().rstrip().partition(" ")
            if not word or not separator:
                raise ValueError("fastText 단어 레코드가 완전하지 않습니다.")
            try:
                vector = np.fromstring(numbers, dtype="<f4", sep=" ")
            except (ValueError, DeprecationWarning) as error:
                raise ValueError("fastText 벡터에 올바르지 않은 수치가 있습니다.") from error
            if vector.shape != (dimensions,):
                raise ValueError("fastText 벡터 차원이 올바르지 않습니다.")
            words.append(word)
            values[index] = vector
            if (index + 1) % 250_000 == 0:
                print(f"fastText 변환 중 · {index + 1:,}/{vocabulary:,}개 단어", flush=True)
    if stream.read().strip():
        raise ValueError("fastText 원본에 예상보다 많은 레코드가 있습니다.")
    values.flush()
    return words, values


def load_vectors(path=DEFAULT_PATH):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"한국어 fastText 모델이 없습니다. 먼저 실행하세요: {SETUP}")
    try:
        metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("fastText 모델 정보는 JSON 객체여야 합니다.")
        words = json.loads((path / "words.json").read_text(encoding="utf-8"))
        if not isinstance(words, list):
            raise ValueError("fastText 단어 목록은 JSON 배열이어야 합니다.")
        vectors = WordVectors(words, np.load(path / "vectors.npy", mmap_mode="r", allow_pickle=False), metadata)
        if metadata.get("sha256") != vectors.metadata["sha256"]:
            raise ValueError("저장된 fastText 모델의 체크섬이 일치하지 않습니다.")
        return vectors
    except (OSError, EOFError, KeyError, TypeError, ValueError) as error:
        raise ValueError(f"fastText 모델을 읽을 수 없습니다: {path}. {error}") from error


def install_vectors(archive=None, destination=DEFAULT_PATH):
    """Verify the pinned text export and publish a complete cache atomically."""
    destination = Path(destination)
    with TemporaryDirectory(prefix="hidden-word-download-") as directory:
        if archive is None:
            if destination.exists():
                return load_vectors(destination)
            archive = Path(directory) / "cc.ko.300.vec.gz"
            print("한국어 fastText 모델 내려받는 중 (약 1.27 GB)...", flush=True)
            with urlopen(DOWNLOAD, timeout=60) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
        else:
            archive = Path(archive)
        with archive.open("rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != ARCHIVE_SHA256:
                raise ValueError("공식 fastText 원본 파일의 SHA-256이 일치하지 않습니다.")
        if destination.exists():
            return load_vectors(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".fasttext-", dir=destination.parent) as staging:
            cache = Path(staging) / "model"
            cache.mkdir()
            # The official export contains malformed UTF-8 tokens. Preserve their
            # bytes without merging words; the Hangul noun filter excludes them.
            with gzip.open(archive, "rt", encoding="utf-8", errors="surrogateescape") as stream:
                words, values = read_fasttext(stream, cache / "vectors.npy", dimensions=DIMENSIONS, vocabulary=VOCABULARY)
            vectors = WordVectors(words, values, {"id": MODEL_ID, "source": SOURCE,
                "download": DOWNLOAD, "source_sha256": ARCHIVE_SHA256, "license": "CC BY-SA 3.0",
                "format": "fasttext-text", "out_of_vocabulary": "reject"})
            (cache / "words.json").write_text(json.dumps(words, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")
            (cache / "metadata.json").write_text(json.dumps(vectors.metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            cache.rename(destination)
            return vectors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="공식 한국어 fastText 모델을 설치합니다.")
    args = parser.parse_args()
    try:
        vectors = install_vectors() if args.download else load_vectors()
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps({"path": str(DEFAULT_PATH), **vectors.metadata}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
