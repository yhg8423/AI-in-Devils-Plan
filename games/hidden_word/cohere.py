"""Cohere reference noun vectors and submitted-hint embeddings."""

import fcntl
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

from . import vectors as shared


MODEL_ID = "embed-v5.0-pro"
DIMENSIONS = 2048
SCORER_ID = f"cohere-{MODEL_ID}-stdict-20260605"
DEFAULT_PATH = shared.ROOT / "runs/models/hidden-word" / SCORER_ID
ENDPOINT = "https://api.cohere.com/v2/embed"
INPUT_TYPE = "clustering"
SETTINGS = {"input_type": INPUT_TYPE, "output_dimension": DIMENSIONS,
            "embedding_types": ["float"], "truncate": "NONE"}
# Measured repeat/batch variation reaches 0.999893; this checks direction drift,
# rather than promising identical provider weights or deterministic output.
ANCHOR_MINIMUM = .999
BATCH_ROWS = 94
REQUEST_INTERVAL = 3.0  # At most 1,920 inputs/minute, including two anchors.


def _metadata(dictionary):
    return {"id": SCORER_ID, "provider": "cohere", "model": MODEL_ID,
            "dictionary": dictionary, "input_protocol": shared.INPUT_PROTOCOL,
            "input_type": INPUT_TYPE, "format": "cohere-embeddings",
            "anchor_minimum_cosine": ANCHOR_MINIMUM, "out_of_vocabulary": "reject"}


def _request(payload):
    from ..models import _api_key

    key = _api_key(shared.ROOT / ".env", "COHERE_API_KEY")
    request = Request(ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode(),
                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    for attempt in range(5):
        try:
            with urlopen(request, timeout=180) as response:
                return json.load(response)
        except HTTPError as error:
            status = error.code
            retryable = status == 429 or 500 <= status < 600
            error.close()
            if not retryable or attempt == 4:
                raise RuntimeError(f"Cohere 임베딩 요청 실패 (HTTP {status}). 키·사용 한도·연결을 확인한 뒤 재개하세요.") from None
        except (URLError, TimeoutError):
            if attempt == 4:
                raise RuntimeError("Cohere 임베딩 연결에 실패했습니다. 연결을 확인한 뒤 재개하세요.") from None
        sleep(min(45, 2 ** (attempt + 1)))


def embed(texts, *, client=None, dimensions=None):
    dimensions = DIMENSIONS if dimensions is None else dimensions
    texts = list(texts)
    payload = {"model": MODEL_ID, "texts": texts, **SETTINGS, "output_dimension": dimensions}
    response = _request(payload) if client is None else client(**payload)
    try:
        if "texts" in response and response["texts"] != texts:
            raise ValueError("Cohere 임베딩 응답의 입력 순서가 다릅니다.")
        values = np.asarray(response["embeddings"]["float"], dtype="<f4")
        if values.shape != (len(texts), dimensions) or not np.isfinite(values).all():
            raise ValueError("Cohere 임베딩 응답의 수량·차원·수치가 올바르지 않습니다.")
        norms = np.linalg.norm(values.astype(np.float64), axis=1)
        if np.any(norms == 0):
            raise ValueError("Cohere 임베딩 응답에 영벡터가 있습니다.")
    except (KeyError, TypeError) as error:
        raise ValueError("Cohere 임베딩 응답 형식이 올바르지 않습니다.") from error
    return (values.astype(np.float64) / norms[:, None]).astype("<f4")


def _check_anchors(fresh, saved):
    fresh, saved = fresh.astype(np.float64), saved.astype(np.float64)
    agreement = np.sum(fresh * saved, axis=1) / (np.linalg.norm(fresh, axis=1) * np.linalg.norm(saved, axis=1))
    if not np.isfinite(agreement).all() or np.any(agreement <= ANCHOR_MINIMUM):
        raise ValueError("Cohere 임베딩이 저장된 기준 모델과 달라 힌트를 판정할 수 없습니다.")


def hint_vector(vectors, hint, *, client=None):
    if (vectors.metadata.get("id") != SCORER_ID or vectors.metadata.get("model") != MODEL_ID
            or vectors.metadata.get("input_type") != INPUT_TYPE):
        raise ValueError("사전 밖 힌트를 판정하려면 동일한 Cohere 기준 캐시가 필요합니다.")
    anchor = "우산" if "우산" in vectors else vectors._words[0]
    values = embed([hint, anchor], client=client, dimensions=vectors.metadata["dimensions"])
    _check_anchors(values[1:], vectors._vectors[[vectors._indices[anchor]]])
    return values[0]


def load_vectors(path=DEFAULT_PATH):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Cohere 명사 임베딩 캐시가 없습니다. 먼저 실행하세요: {shared.SETUP}")
    words, dictionary = shared.load_nouns()
    vectors = shared._read_vectors(path)
    if (vectors._words != words or vectors.metadata["dimensions"] != DIMENSIONS
            or any(vectors.metadata.get(key) != value for key, value in _metadata(dictionary).items())):
        raise ValueError("표준국어대사전 명사 목록 또는 Cohere 임베딩 모델 설정이 다릅니다.")
    vectors._hint_cache = path / "hints"
    return vectors


def install_vectors(destination=DEFAULT_PATH, *, source=None, client=None):
    """Adopt checked research vectors or resume a rate-limited full API build."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (destination.parent / f".{destination.name}.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if destination.exists():
            return load_vectors(destination)
        words, dictionary = shared.load_nouns()
        metadata = _metadata(dictionary)

        def publish(matrix_path):
            return shared._publish(matrix_path, destination, words, dictionary,
                                   metadata=metadata, dimensions=DIMENSIONS, loader=load_vectors)

        if source is not None:
            source = Path(source)
            saved = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
            if (not isinstance(saved, dict) or saved.get("provider") != "cohere"
                    or saved.get("model") != MODEL_ID or saved.get("dimensions") != DIMENSIONS
                    or saved.get("settings") != {**SETTINGS, "output_dimension": DIMENSIONS}
                    or saved.get("complete") is not True
                    or json.loads((source / "words.json").read_text(encoding="utf-8")) != list(words)
                    or saved.get("input_sha256") != shared._file_hash(source / "words.json")
                    or saved.get("vectors_sha256") != shared._file_hash(source / "vectors.npy")):
                raise ValueError("가져올 Cohere 임베딩 캐시의 모델·입력 모드·사전·체크섬이 일치하지 않습니다.")
            return publish(source / "vectors.npy")

        partials = destination.parent / f".{destination.name}-partials"
        partials.mkdir(exist_ok=True)
        anchors = tuple(word for word in ("휴식", "우산") if word in words) or words[:2]
        manifest = {**metadata, "dimensions": DIMENSIONS, "batch_rows": BATCH_ROWS, "anchors": anchors}
        # JSON round-trip converts tuples to lists for comparison on resumed builds.
        manifest = json.loads(json.dumps(manifest))
        manifest_path = partials / "metadata.json"
        if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise ValueError("중단된 Cohere 임베딩 캐시의 모델·사전 설정이 다릅니다.")
        shared._write_json(manifest_path, manifest)
        last_request = -REQUEST_INTERVAL

        def batch(path, texts, reference=None):
            nonlocal last_request
            receipt = path.with_suffix(".json")
            if path.exists() and receipt.exists():
                if json.loads(receipt.read_text(encoding="utf-8")) != {"sha256": shared._file_hash(path), "texts": list(texts)}:
                    raise ValueError("중단된 Cohere 임베딩 배치의 체크섬이 다릅니다.")
                values = np.load(path, allow_pickle=False)
            else:
                sleep(max(0, REQUEST_INTERVAL - (monotonic() - last_request)))
                last_request = monotonic()
                values = embed(texts, client=client)
                if reference is not None:
                    _check_anchors(values[-len(anchors):], reference)
                temporary = path.with_suffix(".npy.tmp")
                with temporary.open("wb") as stream:
                    np.save(stream, values)
                temporary.replace(path)
                shared._write_json(receipt, {"sha256": shared._file_hash(path), "texts": list(texts)})
            if (values.shape != (len(texts), DIMENSIONS) or values.dtype != np.dtype("<f4")
                    or not np.isfinite(values).all() or np.any(np.linalg.norm(values.astype(np.float64), axis=1) == 0)):
                raise ValueError("Cohere 임베딩 배치의 수량·차원·수치가 올바르지 않습니다.")
            return values

        reference = batch(partials / "anchors.npy", anchors)
        with TemporaryDirectory(prefix=".cohere-build-", dir=destination.parent) as staging:
            matrix_path = Path(staging) / "vectors.npy"
            matrix = np.lib.format.open_memmap(matrix_path, mode="w+", dtype="<f4", shape=(len(words), DIMENSIONS))
            for start in range(0, len(words), BATCH_ROWS):
                nouns = words[start:start + BATCH_ROWS]
                values = batch(partials / f"{start:06}.npy", [*nouns, *anchors], reference)
                _check_anchors(values[len(nouns):], reference)
                matrix[start:start + len(nouns)] = values[:len(nouns)]
                if start // BATCH_ROWS % 10 == 0 or start + len(nouns) == len(words):
                    print(f"Cohere 임베딩 준비 · {start + len(nouns)}/{len(words)}개 명사", flush=True)
            matrix.flush()
            del matrix
            vectors = publish(matrix_path)
        shutil.rmtree(partials)
        return vectors
