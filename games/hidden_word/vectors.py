"""Load fixed noun vectors and cache submitted-text embeddings for cosine scoring."""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import fcntl
import gzip
from hashlib import file_digest, sha256
import json
from math import isfinite
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
import unicodedata

import numpy as np

from .words import is_noun_word


MODEL_ID = "text-embedding-3-large"
DICTIONARY_ID = "stdict-nouns-20260605"
SCORER_ID = f"openai-{MODEL_ID}-stdict-20260605"
DIMENSIONS = 3072
VOCABULARY = 213_810
DICTIONARY_SHA256 = "3eb7cd7110d36b2fd058cdb7055aefe3c050f17030df9c3938a1c34135148d3c"
ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).with_name("data")
DEFAULT_PATH = ROOT / "runs/models/hidden-word" / SCORER_ID
LEGACY_PATH = ROOT / "runs/models/hidden-word/fasttext-cc-ko-300"
SETUP = "uv run --locked --python 3.12 python -m games.hidden_word.vectors --download"
NOUN_FILTER = "stdict_noun_membership_v1"
BLOCK_ROWS = 4096
BATCH_ROWS = 512
SCORE_CEILING = 99.9
INPUT_PROTOCOL = "plain isolated dictionary headword; no prompt"
HINT_INPUT_PROTOCOL = "plain submitted text; no prompt"
HANGUL_HINT = re.compile(r"[가-힣ㄱ-ㅣ]+")


def normalize_hint(text):
    if not isinstance(text, str) or not (text := unicodedata.normalize("NFC", text.strip())):
        raise ValueError("빈 문자열은 힌트로 사용할 수 없습니다.")
    return text


def scorer_metadata(vectors):
    """Describe runtime hint scoring without changing the fixed reference cache."""
    return {**vectors.metadata, "out_of_vocabulary": "embed_on_demand",
            "hint_input_protocol": HINT_INPUT_PROTOCOL, "hint_text_normalization": "NFC+strip"}


def _embedding_values(response, count, dimensions, *, model=MODEL_ID):
    data = sorted(response.data, key=lambda row: row.index)
    if response.model != model or [row.index for row in data] != list(range(count)):
        raise ValueError("OpenAI 임베딩 응답의 모델·입력 순서가 다릅니다.")
    values = np.asarray([np.frombuffer(base64.b64decode(row.embedding, validate=True), dtype="<f4")
                         if isinstance(row.embedding, str) else row.embedding for row in data], dtype="<f4")
    if (values.shape != (count, dimensions) or not np.isfinite(values).all()
            or np.any(np.linalg.norm(values.astype(np.float64), axis=1) == 0)):
        raise ValueError("임베딩 배치의 수량·차원·수치가 올바르지 않습니다.")
    return values


def _file_hash(path):
    with Path(path).open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def _write_json(path, value):
    path = Path(path)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@lru_cache(maxsize=1)
def load_nouns():
    """Verify the complete, pinned noun export shipped with the project."""
    metadata = json.loads((DATA / f"{DICTIONARY_ID}.meta.json").read_text(encoding="utf-8"))
    archive = DATA / f"{DICTIONARY_ID}.json.gz"
    if _file_hash(archive) != metadata["compressed_sha256"]:
        raise ValueError("표준국어대사전 명사 파일의 체크섬이 일치하지 않습니다.")
    with gzip.open(archive, "rb") as stream:
        payload = stream.read()
    words = json.loads(payload)
    if (sha256(payload).hexdigest() != DICTIONARY_SHA256 or metadata["sha256"] != DICTIONARY_SHA256
            or metadata["id"] != DICTIONARY_ID or metadata["word_count"] != VOCABULARY
            or not isinstance(words, list) or len(words) != VOCABULARY
            or any(not isinstance(word, str) or not word for word in words) or len(set(words)) != VOCABULARY):
        raise ValueError("표준국어대사전 명사 목록의 수량·체크섬이 올바르지 않습니다.")
    dictionary = {key: metadata[key] for key in ("id", "sha256", "word_count")}
    dictionary.update({key: metadata["source"][key] for key in ("snapshot_date", "revision", "mirror", "license")})
    return tuple(words), dictionary


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
def _legacy_noun_filter():
    from importlib.metadata import version

    return f"kiwipiepy-{version('kiwipiepy')}/model-{version('kiwipiepy-model')}/cong/NNG/oov=false"


@lru_cache(maxsize=1)
def _noun_analyzer():
    from kiwipiepy import Kiwi

    return Kiwi(num_workers=1, model_type="cong")


@lru_cache(maxsize=32768)
def _legacy_common_noun(word):
    if not is_noun_word(word):
        return False
    tokens = _noun_analyzer().tokenize(word)
    return bool(tokens) and all(token.tag == "NNG" and not token.oov for token in tokens) and "".join(token.form for token in tokens) == word


@lru_cache(maxsize=32768)
def _inferred_noun_hint(word):
    tokens = _noun_analyzer().tokenize(word)
    nouns = {"NNG", "NNP", "NNB"}
    return (any(token.tag in nouns for token in tokens)
            and all(token.tag in nouns | {"XPN", "XSN"} for token in tokens)
            and "".join(token.form for token in tokens) == word)


class WordVectors:
    def __init__(self, words, values, metadata=None):
        words = tuple(words)
        values = np.asarray(values, dtype="<f4")
        if (not words or any(not isinstance(word, str) or not word for word in words)
                or len(set(words)) != len(words) or values.ndim != 2
                or values.shape[0] != len(words) or values.shape[1] == 0):
            raise ValueError("단어와 유한한 벡터 행렬이 필요합니다.")
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
        self._vectors, self._norms, self._words = values, norms, words
        self._indices = {word: index for index, word in enumerate(words)}
        self._nearest = {}
        self._hint_vectors = {}
        self._hint_cache = None
        self._legacy = (metadata or {}).get("id") == "fasttext-cc-ko-300"
        self.metadata = {**(metadata or {"id": "custom-embeddings"}),
                         "sha256": digest.hexdigest(), "dimensions": values.shape[1],
                         "vocabulary": len(words), "score": "cosine*100",
                         "nearest_filter": _legacy_noun_filter() if self._legacy else NOUN_FILTER}

    def __contains__(self, word):
        return isinstance(word, str) and word in self._indices

    def is_hint(self, word):
        """Membership for the fixed reference and offline scripted hint examples."""
        return word in self and (not self._legacy or _legacy_common_noun(word))

    def is_korean_noun_hint(self, word):
        """Accept Hangul nouns and noun compounds, including inferred new terms."""
        if not isinstance(word, str) or HANGUL_HINT.fullmatch(word) is None:
            return False
        return word in self or _inferred_noun_hint(word)

    def similarity(self, first, second):
        left, right = self._indices[first], self._indices[second]
        cosine = np.dot(self._vectors[left].astype(np.float64), self._vectors[right].astype(np.float64))
        cosine /= self._norms[left] * self._norms[right]
        return float(np.clip(cosine, -1, 1) * 100)

    def hint_similarity(self, secret, hint, *, client=None, cache_dir=None):
        """Score a submitted text; supplemental embeddings never join the reference."""
        hint = normalize_hint(hint)
        if hint in self:
            return self.similarity(secret, hint)
        target = self._indices[secret]
        if hint not in self._hint_vectors:
            cohere = self.metadata.get("provider") == "cohere"
            manifest = {"version": 1, "base_sha256": self.metadata["sha256"],
                "model": self.metadata.get("model", MODEL_ID), "dimensions": self._vectors.shape[1],
                "input_protocol": HINT_INPUT_PROTOCOL, "normalization": "NFC+strip", "text": hint}
            if cohere:
                manifest.update(provider="cohere", input_type=self.metadata["input_type"])
            key = sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            directory = Path(cache_dir or self._hint_cache or DEFAULT_PATH / "hints")
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{key}.json"
            with path.with_suffix(".lock").open("a+b") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if path.exists():
                    entry = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(entry, dict) or entry.get("key") != manifest:
                        raise ValueError("힌트 임베딩 캐시의 모델·입력 정보가 다릅니다.")
                    value = np.asarray(entry.get("vector"), dtype="<f4")
                    if (value.shape != (manifest["dimensions"],) or not np.isfinite(value).all()
                            or np.linalg.norm(value.astype(np.float64)) == 0
                            or entry.get("vector_sha256") != sha256(value.tobytes()).hexdigest()):
                        raise ValueError("힌트 임베딩 캐시의 수치·체크섬이 올바르지 않습니다.")
                else:
                    def request(provided):
                        anchor = "우산" if "우산" in self else self._words[0]
                        response = provided.embeddings.create(model=manifest["model"], input=[hint, anchor],
                            dimensions=manifest["dimensions"], encoding_format="base64")
                        values = _embedding_values(response, 2, manifest["dimensions"], model=manifest["model"])
                        fresh = values[1].astype(np.float64)
                        saved = self._vectors[self._indices[anchor]].astype(np.float64)
                        agreement = float(fresh @ saved / (np.linalg.norm(fresh) * np.linalg.norm(saved)))
                        if agreement <= .99999:
                            raise ValueError("OpenAI 임베딩이 저장된 기준 모델과 달라 힌트를 판정할 수 없습니다.")
                        return values[0]

                    if cohere:
                        from .cohere import hint_vector

                        value = hint_vector(self, hint, client=client)
                    elif client is None:
                        if self.metadata.get("id") != SCORER_ID:
                            raise RuntimeError("사전 밖 힌트를 판정하려면 OpenAI 기준 캐시가 필요합니다.")
                        from openai import APIError, OpenAI
                        from ..models import _openai_key

                        try:
                            with OpenAI(api_key=_openai_key(ROOT / ".env"), base_url="https://api.openai.com/v1",
                                        timeout=180, max_retries=5) as provided:
                                value = request(provided)
                        except APIError:
                            raise RuntimeError("힌트 임베딩 요청에 실패했습니다. OpenAI 키·사용 한도·연결을 확인한 뒤 재개하세요.") from None
                    else:
                        value = request(client)
                    _write_json(path, {"key": manifest, "vector": value.tolist(),
                                       "vector_sha256": sha256(value.tobytes()).hexdigest()})
                value.flags.writeable = False
                self._hint_vectors[hint] = value
        value = self._hint_vectors[hint].astype(np.float64)
        cosine = float(self._vectors[target].astype(np.float64) @ value)
        cosine /= self._norms[target] * np.linalg.norm(value)
        return float(np.clip(cosine, -1, 1) * 100)

    def nearest(self, word):
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
                raise ValueError(f"{word!r}와 비교할 수 있는 다른 명사가 사전에 없습니다.")
        return self._nearest[word].copy()


def _read_vectors(path):
    path = Path(path)
    try:
        metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("모델 정보는 JSON 객체여야 합니다.")
        words = json.loads((path / "words.json").read_text(encoding="utf-8"))
        if not isinstance(words, list):
            raise ValueError("단어 목록은 JSON 배열이어야 합니다.")
        matrix = np.load(path / "vectors.npy", mmap_mode="r", allow_pickle=False)
        if matrix.dtype != np.dtype("<f4"):
            raise ValueError("캐시 벡터는 float32 형식이어야 합니다.")
        vectors = WordVectors(words, matrix, metadata)
        if metadata.get("sha256") != vectors.metadata["sha256"]:
            raise ValueError("저장된 모델의 체크섬이 일치하지 않습니다.")
        return vectors
    except (OSError, EOFError, KeyError, TypeError, ValueError) as error:
        raise ValueError(f"임베딩 모델을 읽을 수 없습니다: {path}. {error}") from error


def _scorer_metadata(dictionary):
    return {"id": SCORER_ID, "provider": "openai", "model": MODEL_ID,
            "dictionary": dictionary, "input_protocol": INPUT_PROTOCOL,
            "format": "openai-embeddings", "out_of_vocabulary": "reject"}


def load_vectors(path=DEFAULT_PATH):
    if not Path(path).exists():
        raise FileNotFoundError(f"OpenAI 명사 임베딩 캐시가 없습니다. 먼저 실행하세요: {SETUP}")
    words, dictionary = load_nouns()
    vectors = _read_vectors(path)
    if (vectors._words != words or vectors.metadata["dimensions"] != DIMENSIONS
            or any(vectors.metadata.get(key) != value for key, value in _scorer_metadata(dictionary).items())):
        raise ValueError("표준국어대사전 명사 목록 또는 OpenAI 임베딩 모델 설정이 다릅니다.")
    vectors._hint_cache = Path(path) / "hints"
    return vectors


def load_legacy_vectors(path=LEGACY_PATH):
    """Read the old cache only for historical fastText replay display projection."""
    vectors = _read_vectors(path)
    if vectors.metadata.get("id") != "fasttext-cc-ko-300":
        raise ValueError("이전 fastText 기록에 해당하는 캐시가 아닙니다.")
    return vectors


def _publish(matrix_path, destination, words, dictionary, *, metadata=None, dimensions=None, loader=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".openai-", dir=destination.parent) as staging:
        cache = Path(staging) / "model"
        cache.mkdir()
        shutil.copyfile(matrix_path, cache / "vectors.npy")
        matrix = np.load(cache / "vectors.npy", mmap_mode="r", allow_pickle=False)
        if matrix.shape != (len(words), DIMENSIONS if dimensions is None else dimensions) or matrix.dtype != np.dtype("<f4"):
            raise ValueError("임베딩 캐시의 단어 수·차원·형식이 다릅니다.")
        vectors = WordVectors(words, matrix, {**(_scorer_metadata(dictionary) if metadata is None else metadata),
            "vectors_sha256": _file_hash(cache / "vectors.npy")})
        _write_json(cache / "words.json", words)
        _write_json(cache / "metadata.json", vectors.metadata)
        cache.rename(destination)
    return (loader or load_vectors)(destination)


def install_vectors(destination=DEFAULT_PATH, *, source=None, client=None):
    """Publish a complete cache; interrupted API batches remain reusable."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Concurrent setup commands share paid batches; the OS releases this lock on exit.
    with (destination.parent / f".{destination.name}.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _install_vectors(destination, source=source, client=client)


def _install_vectors(destination, *, source=None, client=None):
    if destination.exists():
        return load_vectors(destination)
    words, dictionary = load_nouns()
    if source is not None:
        source = Path(source)
        metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
        if (not isinstance(metadata, dict) or metadata.get("model") != MODEL_ID
                or metadata.get("input_protocol") not in
                {INPUT_PROTOCOL, "plain isolated Korean dictionary headword, no prompt"}
                or json.loads((source / "words.json").read_text(encoding="utf-8")) != list(words)
                or metadata.get("vectors_sha256") != _file_hash(source / "vectors.npy")):
            raise ValueError("가져올 임베딩 캐시의 모델·사전·체크섬이 일치하지 않습니다.")
        return _publish(source / "vectors.npy", destination, words, dictionary)
    if client is None:
        from openai import OpenAI
        from ..models import _openai_key

        with OpenAI(api_key=_openai_key(ROOT / ".env"), base_url="https://api.openai.com/v1",
                    timeout=180, max_retries=5) as client:
            return _install_vectors(destination, client=client)
    partials = destination.parent / f".{destination.name}-partials"
    partials.mkdir(parents=True, exist_ok=True)
    manifest = {**_scorer_metadata(dictionary), "dimensions": DIMENSIONS, "batch_rows": BATCH_ROWS}
    manifest_path = partials / "metadata.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
        raise ValueError("중단된 임베딩 캐시의 모델·사전 설정이 다릅니다.")
    _write_json(manifest_path, manifest)

    def encode_batch(start):
        batch = words[start:start + BATCH_ROWS]
        matrix_path = partials / f"{start:06}.npy"
        receipt_path = matrix_path.with_suffix(".json")
        cached = matrix_path.exists() and receipt_path.exists()
        if cached:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt != {"start": start, "count": len(batch), "sha256": _file_hash(matrix_path)}:
                raise ValueError("중단된 임베딩 배치의 체크섬이 다릅니다.")
            values = np.load(matrix_path, allow_pickle=False)
        else:
            response = client.embeddings.create(model=MODEL_ID, input=list(batch),
                dimensions=DIMENSIONS, encoding_format="base64")
            values = _embedding_values(response, len(batch), DIMENSIONS)
        if (values.shape != (len(batch), DIMENSIONS) or values.dtype != np.dtype("<f4")
                or not np.isfinite(values).all() or np.any(np.linalg.norm(values.astype(np.float64), axis=1) == 0)):
            raise ValueError("임베딩 배치의 수량·차원·수치가 올바르지 않습니다.")
        if not cached:
            temporary = matrix_path.with_suffix(".npy.tmp")
            with temporary.open("wb") as stream:
                np.save(stream, values)
            temporary.replace(matrix_path)
            _write_json(receipt_path, {"start": start, "count": len(batch), "sha256": _file_hash(matrix_path)})
        return start, values

    with TemporaryDirectory(prefix=".openai-build-", dir=destination.parent) as directory:
        matrix_path = Path(directory) / "vectors.npy"
        matrix = np.lib.format.open_memmap(matrix_path, mode="w+", dtype="<f4", shape=(len(words), DIMENSIONS))
        starts = range(0, len(words), BATCH_ROWS)
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(encode_batch, start): start for start in starts}
            total = len(futures)
            try:
                for count, future in enumerate(as_completed(futures), 1):
                    start, values = future.result()
                    matrix[start:start + len(values)] = values
                    del futures[future]
                    if count % 10 == 0 or count == total:
                        print(f"OpenAI 임베딩 준비 · {count}/{total}개 배치", flush=True)
            except BaseException:
                for future in futures:
                    future.cancel()
                raise
        matrix.flush()
        del matrix
        vectors = _publish(matrix_path, destination, words, dictionary)
    shutil.rmtree(partials)
    return vectors


def main():
    # The OpenAI loader remains available for resumes; setup now prepares Cohere.
    from .cohere import DEFAULT_PATH, install_vectors, load_vectors

    parser = argparse.ArgumentParser(description=__doc__)
    install = parser.add_mutually_exclusive_group()
    install.add_argument("--download", action="store_true", help="Cohere API로 전체 명사 임베딩을 한 번 준비합니다.")
    install.add_argument("--from-cache", type=Path, help="검증된 동일 사전·모델 캐시를 가져옵니다.")
    args = parser.parse_args()
    try:
        vectors = install_vectors(source=args.from_cache) if args.download or args.from_cache else load_vectors()
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps({"path": str(DEFAULT_PATH), **scorer_metadata(vectors)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
