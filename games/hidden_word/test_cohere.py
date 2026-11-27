from contextlib import contextmanager
from copy import deepcopy
import json
from math import sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import numpy as np

from . import cohere, vectors


WORDS = ("휴식", "우산", "바다", "해양", "연필")
VALUES = np.asarray([[1, 0], [0, 1], [.6, .8], [.8, .6], [-1, 0]], dtype="<f4")
DICTIONARY = {"id": "test-nouns", "sha256": "test-dictionary", "word_count": len(WORDS)}


@contextmanager
def tiny_dictionary():
    with (patch.object(vectors, "load_nouns", return_value=(WORDS, DICTIONARY)),
          patch.object(cohere, "DIMENSIONS", 2), patch.object(cohere, "BATCH_ROWS", 2),
          patch.object(cohere, "REQUEST_INTERVAL", 0)):
        yield


def model(values=VALUES, **metadata):
    return vectors.WordVectors(WORDS, values.copy(), {**cohere._metadata(DICTIONARY), **metadata})


def client_for(callback=None):
    lookup = dict(zip(WORDS, VALUES))

    def respond(**request):
        return {"texts": request["texts"], "embeddings": {
            "float": [np.asarray(lookup.get(word, [3, 4])).tolist() for word in request["texts"]]}}

    return Mock(side_effect=callback or respond)


def source_cache(path, *, words=WORDS, values=VALUES, updates=None):
    path.mkdir()
    (path / "words.json").write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
    np.save(path / "vectors.npy", values)
    metadata = {"provider": "cohere", "model": cohere.MODEL_ID, "dimensions": cohere.DIMENSIONS,
                "settings": {**cohere.SETTINGS, "output_dimension": cohere.DIMENSIONS}, "complete": True,
                "input_sha256": vectors._file_hash(path / "words.json"),
                "vectors_sha256": vectors._file_hash(path / "vectors.npy"), **(updates or {})}
    (path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


class CohereVectorsTest(unittest.TestCase):
    def test_import_reuses_checked_research_vectors_without_api_and_keeps_an_independent_cache(self):
        with TemporaryDirectory() as directory, tiny_dictionary():
            root = Path(directory)
            source_cache(root / "source")
            offline = Mock(side_effect=AssertionError("import must not call API"))
            installed = cohere.install_vectors(root / "cache", source=root / "source", client=offline)
            np.testing.assert_array_equal(installed._vectors, VALUES)
            self.assertFalse(installed._vectors.flags.writeable)
            self.assertEqual(installed.metadata["provider"], "cohere")
            self.assertEqual(installed.metadata["input_type"], "clustering")
            self.assertNotEqual((root / "source/vectors.npy").stat().st_ino,
                                (root / "cache/vectors.npy").stat().st_ino)
            np.save(root / "source/vectors.npy", np.zeros_like(VALUES))
            loaded = cohere.install_vectors(root / "cache", source=root / "missing", client=offline)
            np.testing.assert_array_equal(loaded._vectors, VALUES)
            self.assertEqual(loaded.metadata, installed.metadata)
            offline.assert_not_called()

    def test_import_rejects_other_provider_mode_partial_or_damaged_vectors(self):
        variations = [
            {"updates": {"provider": "openai"}},
            {"updates": {"model": "wrong-model"}},
            {"updates": {"settings": {**cohere.SETTINGS, "output_dimension": 2,
                                        "input_type": "search_query"}}},
            {"updates": {"complete": False}},
            {"updates": {"vectors_sha256": "0" * 64}},
            {"updates": {"input_sha256": "0" * 64}},
            {"words": tuple(reversed(WORDS))},
            {"values": VALUES.astype("<f8")},
            {"values": np.ones((len(WORDS), 3), dtype="<f4")},
            {"values": np.zeros_like(VALUES)},
        ]
        for variation in variations:
            with self.subTest(variation=variation), TemporaryDirectory() as directory, tiny_dictionary():
                root = Path(directory)
                source_cache(root / "source", **variation)
                offline = Mock(side_effect=AssertionError("bad import must not call API"))
                with self.assertRaises(ValueError):
                    cohere.install_vectors(root / "cache", source=root / "source", client=offline)
                self.assertFalse((root / "cache").exists())
                offline.assert_not_called()

    def test_oov_hint_uses_exact_cohere_mode_and_reuses_persistent_vectors(self):
        base = model()
        original = deepcopy(base.metadata)
        nearest = base.nearest("휴식")
        with TemporaryDirectory() as directory:
            cache = Path(directory)
            client = client_for()
            self.assertAlmostEqual(base.hint_similarity("휴식", "시장경제", client=client, cache_dir=cache), 60, places=5)
            self.assertAlmostEqual(base.hint_similarity("우산", "시장경제", client=client, cache_dir=cache), 80, places=5)
            client.assert_called_once_with(model=cohere.MODEL_ID, texts=["시장경제", "우산"],
                input_type="clustering", output_dimension=2, embedding_types=["float"], truncate="NONE")
            fresh = model()
            offline = Mock(side_effect=AssertionError("persistent hint must stay offline"))
            self.assertAlmostEqual(fresh.hint_similarity("휴식", "시장경제", client=offline, cache_dir=cache), 60, places=5)
            self.assertEqual(fresh.hint_similarity("휴식", "연필", client=offline, cache_dir=cache), -100)
            offline.assert_not_called()
            entry = json.loads(next(cache.glob("*.json")).read_text())
            self.assertEqual(entry["key"]["provider"], "cohere")
            self.assertEqual(entry["key"]["input_type"], "clustering")
            changed_mode = model(input_type="search_query")
            with self.assertRaisesRegex(ValueError, "동일한 Cohere"):
                changed_mode.hint_similarity("휴식", "시장경제", client=offline, cache_dir=cache)
            self.assertEqual(len(list(cache.glob("*.json"))), 1)
        self.assertEqual(base.metadata, original)
        self.assertEqual(base.nearest("휴식"), nearest)
        self.assertNotIn("시장경제", base)

    def test_hint_anchor_accepts_observed_small_drift_but_rejects_changes_and_malformed_responses(self):
        def response(anchor):
            return lambda **request: {"texts": request["texts"], "embeddings": {"float": [[3, 4], anchor]}}

        with TemporaryDirectory() as directory:
            cache = Path(directory)
            client = client_for(response([sqrt(1 - .9999 ** 2), .9999]))
            self.assertAlmostEqual(model().hint_similarity("휴식", "시장경제", client=client, cache_dir=cache), 60, places=5)
        cases = [
            client_for(response([1, 0])),
            Mock(side_effect=RuntimeError("temporary failure")),
            Mock(return_value={"texts": ["우산", "시장경제"], "embeddings": {"float": [[3, 4], [0, 1]]}}),
            Mock(return_value={"embeddings": {"float": [[3, 4, 5], [0, 1, 2]]}}),
            Mock(return_value={"embeddings": {"float": [[float("nan"), 1], [0, 1]]}}),
            Mock(return_value={"embeddings": {"float": [[0, 0], [0, 1]]}}),
            Mock(return_value={}),
        ]
        for client in cases:
            with self.subTest(response=client), TemporaryDirectory() as directory:
                cache = Path(directory)
                base = model()
                with self.assertRaises((ValueError, RuntimeError)):
                    base.hint_similarity("휴식", "시장경제", client=client, cache_dir=cache)
                self.assertEqual(list(cache.glob("*.json")), [])
                self.assertAlmostEqual(base.hint_similarity("휴식", "시장경제", client=client_for(), cache_dir=cache), 60, places=5)

    def test_completed_paid_batches_are_reused_after_an_interrupted_build(self):
        respond = client_for()

        def interrupted(**request):
            if request["texts"][:2] == list(WORDS[2:4]):
                raise RuntimeError("interrupted request")
            return respond(**request)

        with TemporaryDirectory() as directory, tiny_dictionary():
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "interrupted request"):
                cohere.install_vectors(root / "cache", client=client_for(interrupted))
            self.assertFalse((root / "cache").exists())
            self.assertTrue((root / ".cache-partials/anchors.json").exists())
            self.assertTrue((root / ".cache-partials/000000.json").exists())
            resumed = client_for()
            installed = cohere.install_vectors(root / "cache", client=resumed)
            np.testing.assert_allclose(installed._vectors, VALUES)
            self.assertEqual(resumed.call_count, 2)
            self.assertEqual(resumed.call_args_list[0].kwargs["texts"], [*WORDS[2:4], *WORDS[:2]])
            self.assertEqual(resumed.call_args_list[1].kwargs["texts"], [*WORDS[4:], *WORDS[:2]])
            self.assertFalse((root / ".cache-partials").exists())

    def test_changed_anchor_batch_is_not_saved_and_can_be_retried(self):
        respond = client_for()

        def drifted(**request):
            response = respond(**request)
            if len(request["texts"]) > 2:
                response["embeddings"]["float"][-1] = [1, 0]
            return response

        with TemporaryDirectory() as directory, tiny_dictionary():
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "저장된 기준 모델"):
                cohere.install_vectors(root / "cache", client=client_for(drifted))
            self.assertFalse((root / ".cache-partials/000000.json").exists())
            self.assertFalse((root / ".cache-partials/000000.npy").exists())
            resumed = client_for()
            cohere.install_vectors(root / "cache", client=resumed)
            self.assertEqual(resumed.call_count, 3)


if __name__ == "__main__":
    unittest.main()
