"""Load shared Korean Word2Vec vectors and calculate cosine similarity locally."""

import argparse
from hashlib import sha256
from io import TextIOWrapper
import json
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile

import numpy as np


MODEL_ID = "kyubyong-ko-word2vec-2016"
SOURCE = "https://github.com/Kyubyong/wordvectors"
DOWNLOAD = "https://drive.usercontent.google.com/download?id=0B0ZXk88koS2KbDhXdWg1Q2RydlU&export=download&confirm=t"
ARCHIVE_SHA256 = "1f8dc03dd7d4901c33b8391b154a59f1ae7e603c354835b8f2d2fa155c587451"
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "runs/models/hidden-word/ko-word2vec.npz"
SETUP = "uv run --locked --python 3.12 python -m games.hidden_word.vectors --download"


class WordVectors:
    def __init__(self, words, values, metadata=None):
        words = tuple(words)
        values = np.asarray(values, dtype="<f4")
        if (not words or any(not isinstance(word, str) or not word for word in words)
                or len(set(words)) != len(words) or values.ndim != 2
                or values.shape[0] != len(words) or values.shape[1] == 0
                or not np.isfinite(values).all()):
            raise ValueError("Word2Vec 단어와 유한한 벡터 행렬이 필요합니다.")
        normalized = values.astype(np.float64)
        norms = np.linalg.norm(normalized, axis=1)
        if np.any(norms == 0):
            raise ValueError("Word2Vec에는 길이가 0인 벡터를 사용할 수 없습니다.")
        normalized /= norms[:, None]
        normalized.flags.writeable = False
        self._vectors = normalized
        self._indices = {word: index for index, word in enumerate(words)}
        digest = sha256(json.dumps(words, ensure_ascii=False, separators=(",", ":")).encode())
        digest.update(b"\0")
        digest.update(values.tobytes(order="C"))
        self.metadata = {**(metadata or {"id": "custom-word2vec"}),
                         "sha256": digest.hexdigest(), "dimensions": values.shape[1],
                         "vocabulary": len(words), "score": "cosine*100"}

    def __contains__(self, word):
        return word in self._indices

    def similarity(self, first, second):
        left, right = self._vectors[self._indices[first]], self._vectors[self._indices[second]]
        # Clamp only floating-point drift outside cosine's mathematical bounds.
        return float(np.clip(np.dot(left, right), -1, 1) * 100)


def read_tsv(stream, dimensions):
    """Read the author's multiline NumPy text export without unpickling ko.bin."""
    words, vectors, parts = [], [], []
    word = None
    for line in stream:
        if word is None:
            index, word, line = line.split("\t", 2)
            if int(index) != len(words) or not line.startswith("["):
                raise ValueError("Word2Vec TSV 레코드 순서가 올바르지 않습니다.")
            line = line[1:]
        complete = line.rstrip().endswith("]")
        parts.append(line.rstrip().removesuffix("]"))
        if complete:
            vector = np.asarray(" ".join(parts).split(), dtype="<f4")
            if vector.shape != (dimensions,):
                raise ValueError("Word2Vec TSV 벡터 차원이 올바르지 않습니다.")
            words.append(word)
            vectors.append(vector)
            word, parts = None, []
    if word is not None or not words:
        raise ValueError("Word2Vec TSV 데이터가 완전하지 않습니다.")
    return words, np.asarray(vectors, dtype="<f4")


def load_vectors(path=DEFAULT_PATH):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"한국어 Word2Vec 모델이 없습니다. 먼저 실행하세요: {SETUP}")
    try:
        with np.load(path, allow_pickle=False) as stored:
            metadata = json.loads(stored["metadata"].item())
            if not isinstance(metadata, dict):
                raise ValueError("Word2Vec 모델 정보는 JSON 객체여야 합니다.")
            vectors = WordVectors(stored["words"].tolist(), stored["vectors"], metadata)
        if metadata.get("sha256") != vectors.metadata["sha256"]:
            raise ValueError("저장된 Word2Vec 모델의 체크섬이 일치하지 않습니다.")
        return vectors
    except (BadZipFile, EOFError, KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Word2Vec 모델을 읽을 수 없습니다: {path}. {error}") from error


def install_vectors(archive=None, destination=DEFAULT_PATH):
    """Download the pinned author's archive, verify it, and atomically cache data."""
    destination = Path(destination)
    with TemporaryDirectory(prefix="hidden-word-vectors-") as directory:
        if archive is None:
            archive = Path(directory) / "ko.zip"
            print("한국어 Word2Vec 모델 내려받는 중 (약 77 MiB)...", flush=True)
            with urlopen(DOWNLOAD, timeout=30) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
        else:
            archive = Path(archive)
        if sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
            raise ValueError("공개 Word2Vec 원본 파일의 SHA-256이 일치하지 않습니다.")
        with ZipFile(archive) as packed, packed.open("ko.tsv") as data:
            words, values = read_tsv(TextIOWrapper(data, encoding="utf-8"), 200)
        if len(words) != 30185:
            raise ValueError("공개 Word2Vec 원본의 어휘 수가 일치하지 않습니다.")
        vectors = WordVectors(words, values, {"id": MODEL_ID, "source": SOURCE,
            "source_sha256": ARCHIVE_SHA256, "license": "MIT · Copyright 2016 Kyubyong Park"})
        destination.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=destination.parent, suffix=".npz", delete=False) as output:
            temporary = Path(output.name)
        try:
            np.savez_compressed(temporary, words=np.asarray(words), vectors=values,
                                metadata=np.asarray(json.dumps(vectors.metadata)))
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return vectors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="공개 한국어 Word2Vec 모델을 설치합니다.")
    args = parser.parse_args()
    try:
        vectors = install_vectors() if args.download else load_vectors()
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps({"path": str(DEFAULT_PATH), **vectors.metadata}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
