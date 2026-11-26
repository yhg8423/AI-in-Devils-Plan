import base64
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from . import vectors


WORDS = ("바다", "학교의", "우산국", "ㄱ", "해양", "연필")
VALUES = np.array([[1, 0], [2, 1], [1, 2], [-1, 0], [3, 4], [0, 1]], dtype="<f4")


@contextmanager
def tiny_dictionary(words=WORDS):
    dictionary = {"id": "fixture-nouns", "sha256": "fixture-dictionary", "word_count": len(words)}
    with patch.object(vectors, "load_nouns", return_value=(tuple(words), dictionary)), \
         patch.object(vectors, "DIMENSIONS", 2), patch.object(vectors, "BATCH_ROWS", 2):
        yield dictionary


def response(words, values=None):
    lookup = dict(zip(WORDS, VALUES))
    if values is None:
        values = [lookup.get(word, [1, 1]) for word in words]
    data = [SimpleNamespace(index=index, embedding=base64.b64encode(
        np.asarray(value, dtype="<f4").tobytes()).decode("ascii")) for index, value in enumerate(values)]
    return SimpleNamespace(model=vectors.MODEL_ID, data=list(reversed(data)))


def fake_client(callback=None):
    return SimpleNamespace(embeddings=SimpleNamespace(create=Mock(
        side_effect=callback or (lambda **request: response(request["input"])))))


def source_cache(directory, *, words=WORDS, values=VALUES, updates=None):
    directory.mkdir()
    np.save(directory / "vectors.npy", values)
    (directory / "words.json").write_text(json.dumps(words), encoding="utf-8")
    metadata = {"model": vectors.MODEL_ID,
                "input_protocol": "plain isolated Korean dictionary headword, no prompt",
                "vectors_sha256": sha256((directory / "vectors.npy").read_bytes()).hexdigest(),
                **(updates or {})}
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


class WordVectorsTest(unittest.TestCase):
    def test_bundled_dictionary_is_complete_and_registered_nouns_are_not_reparsed(self):
        words, metadata = vectors.load_nouns()
        self.assertEqual(len(words), 213810)
        self.assertEqual(len(set(words)), 213810)
        digest = sha256(json.dumps(words, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(digest, vectors.DICTIONARY_SHA256)
        self.assertEqual(metadata["word_count"], len(words))
        for word in ("학교의", "우산국", "ㄱ", "강", "바다", "봄", "별"):
            self.assertIn(word, words)
        model = vectors.WordVectors(WORDS, VALUES)
        for word in WORDS:
            self.assertTrue(model.is_hint(word))
        for word in ("없는단어", None, ["해양"], 1):
            self.assertFalse(model.is_hint(word))
        self.assertEqual(model.metadata["nearest_filter"], vectors.NOUN_FILTER)

    def test_normalized_score_preserves_the_strict_95_boundary(self):
        self.assertEqual(vectors.normalized_score(60, 60), 99.9)
        self.assertEqual(vectors.normalized_score(51, 60), 85)
        self.assertEqual(vectors.normalized_score(57, 60), 95)
        self.assertGreater(vectors.normalized_score(57.001, 60), 95)
        self.assertEqual(vectors.normalized_score(-30, 60), 0)
        self.assertEqual(vectors.normalized_score(100, 60), 99.9)
        self.assertIsNone(vectors.normalized_score(None, 60))
        for maximum in (0, -1, float("nan"), float("inf")):
            with self.subTest(maximum=maximum), self.assertRaises(ValueError):
                vectors.normalized_score(50, maximum)
        with self.assertRaises(ValueError):
            vectors.normalized_score(float("nan"), 60)

    def test_raw_cosine_self_exclusion_stable_ties_and_block_boundaries(self):
        with patch.object(vectors, "BLOCK_ROWS", 1):
            model = vectors.WordVectors(["바다", "학교의", "우산국", "ㄱ"],
                                        [[1, 0], [3, 4], [3, 4], [-1, 0]])
            self.assertEqual(model.similarity("바다", "바다"), 100)
            self.assertAlmostEqual(model.similarity("바다", "학교의"), 60)
            self.assertEqual(model.similarity("바다", "ㄱ"), -100)
            self.assertEqual(model.similarity("학교의", "바다"), model.similarity("바다", "학교의"))
            self.assertEqual(model.nearest("바다"), {"word": "학교의", "similarity": 60})
            model.nearest("바다")["word"] = "변경"
            self.assertEqual(model.nearest("바다")["word"], "학교의")
            negative = vectors.WordVectors(["바다", "대양", "해양"], [[1, 0], [-1, 0], [-1, 0]])
            self.assertEqual(negative.nearest("바다"), {"word": "대양", "similarity": -100})
            with self.assertRaises(KeyError):
                model.similarity("바다", "없는단어")
            with self.assertRaises(KeyError):
                model.nearest("없는단어")
            with self.assertRaisesRegex(ValueError, "다른 명사"):
                vectors.WordVectors(["바다"], [[1, 0]]).nearest("바다")
            for values in ([[0, 0]], [[float("nan"), 1]], [[float("inf"), 1]], [[]], []):
                with self.subTest(values=values), self.assertRaises(ValueError):
                    vectors.WordVectors(["바다"], values)

    def test_legacy_fasttext_cache_keeps_its_historical_noun_filter(self):
        words = ["바다", "학교의", "라인강", "sea", "쉘부르의", "살윈", "바닷", "해양"]
        values = np.asarray([[1, 0]] * 7 + [[3, 4]], dtype="<f4")
        legacy = vectors.WordVectors(words, values, {"id": "fasttext-cc-ko-300"})
        self.assertEqual(legacy.nearest("바다"), {"word": "해양", "similarity": 60})
        self.assertFalse(legacy.is_hint("학교의"))
        with TemporaryDirectory() as directory:
            path = Path(directory)
            np.save(path / "vectors.npy", values)
            (path / "words.json").write_text(json.dumps(words))
            (path / "metadata.json").write_text(json.dumps(legacy.metadata))
            loaded = vectors.load_legacy_vectors(path)
            self.assertEqual(loaded.metadata, legacy.metadata)
            self.assertEqual(loaded.nearest("바다"), legacy.nearest("바다"))
            with tiny_dictionary(), self.assertRaises(ValueError):
                vectors.load_vectors(path)

    def test_source_adoption_is_offline_and_independent_of_source_files(self):
        client = fake_client(lambda **_: self.fail("API must not be called"))
        with TemporaryDirectory() as directory, tiny_dictionary():
            root = Path(directory)
            source, destination = root / "source", root / "cache"
            source_cache(source)
            installed = vectors.install_vectors(destination, source=source, client=client)
            np.testing.assert_array_equal(installed._vectors, VALUES)
            self.assertIsInstance(installed._vectors.base, np.memmap)
            self.assertFalse(installed._vectors.flags.writeable)
            self.assertNotEqual((source / "vectors.npy").stat().st_ino,
                                (destination / "vectors.npy").stat().st_ino)
            np.save(source / "vectors.npy", np.zeros_like(VALUES))
            loaded = vectors.install_vectors(destination, source=root / "missing", client=client)
            np.testing.assert_array_equal(loaded._vectors, VALUES)
            self.assertEqual(loaded.metadata, installed.metadata)
            client.embeddings.create.assert_not_called()

    def test_source_adoption_rejects_wrong_words_model_protocol_hash_or_shape(self):
        variations = [
            {"words": tuple(reversed(WORDS))},
            {"updates": {"model": "another-model"}},
            {"updates": {"input_protocol": "query: prefixed word"}},
            {"updates": {"vectors_sha256": "0" * 64}},
            {"values": np.ones((len(WORDS), 3), dtype="<f4")},
            {"values": VALUES.astype("<f8")},
        ]
        for variation in variations:
            with self.subTest(variation=tuple(variation)), TemporaryDirectory() as directory, tiny_dictionary():
                root = Path(directory)
                source_cache(root / "source", **variation)
                with self.assertRaises(ValueError):
                    vectors.install_vectors(root / "cache", source=root / "source")
                self.assertFalse((root / "cache").exists())
                self.assertEqual(list(root.glob(".openai-*")), [])

    def test_cached_load_rejects_changed_vectors_and_model_metadata(self):
        with TemporaryDirectory() as directory, tiny_dictionary():
            root = Path(directory)
            source_cache(root / "source")
            destination = root / "cache"
            original = vectors.install_vectors(destination, source=root / "source").metadata
            changed = VALUES.copy()
            changed[0, 1] = 2
            np.save(destination / "vectors.npy", changed)
            with self.assertRaisesRegex(ValueError, "체크섬"):
                vectors.load_vectors(destination)
            np.save(destination / "vectors.npy", VALUES)
            for update in ({"model": "another-model"}, {"provider": "another-provider"},
                           {"dictionary": {"id": "another-dictionary"}}):
                (destination / "metadata.json").write_text(json.dumps({**original, **update}))
                with self.subTest(update=update), self.assertRaisesRegex(ValueError, "설정"):
                    vectors.load_vectors(destination)
            (destination / "metadata.json").write_text("null")
            with self.assertRaisesRegex(ValueError, "JSON 객체"):
                vectors.load_vectors(destination)
            with self.assertRaisesRegex(FileNotFoundError, "--download"):
                vectors.load_vectors(root / "missing")

    def test_api_base64_responses_follow_indices_and_complete_cache_is_reused(self):
        client = fake_client()
        with TemporaryDirectory() as directory, tiny_dictionary():
            destination = Path(directory) / "cache"
            installed = vectors.install_vectors(destination, client=client)
            np.testing.assert_array_equal(installed._vectors, VALUES)
            self.assertEqual(client.embeddings.create.call_count, 3)
            for call in client.embeddings.create.call_args_list:
                self.assertEqual(call.kwargs["model"], vectors.MODEL_ID)
                self.assertEqual(call.kwargs["dimensions"], 2)
                self.assertEqual(call.kwargs["encoding_format"], "base64")
            vectors.install_vectors(destination, client=client)
            self.assertEqual(client.embeddings.create.call_count, 3)
            self.assertFalse((destination.parent / ".cache-partials").exists())

    def test_completed_paid_batches_survive_failure_and_are_reused_on_resume(self):
        def interrupted(**request):
            if request["input"] == list(WORDS[4:]):
                raise RuntimeError("interrupted request")
            return response(request["input"])

        with TemporaryDirectory() as directory, tiny_dictionary(), \
             patch.object(vectors, "ThreadPoolExecutor", side_effect=lambda **_: ThreadPoolExecutor(max_workers=1)):
            destination = Path(directory) / "cache"
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                vectors.install_vectors(destination, client=fake_client(interrupted))
            self.assertFalse(destination.exists())
            partials = destination.parent / ".cache-partials"
            self.assertEqual(len(list(partials.glob("*.npy"))), 2)
            self.assertEqual(len(list(partials.glob("*.json"))), 3)
            resumed = fake_client()
            installed = vectors.install_vectors(destination, client=resumed)
            np.testing.assert_array_equal(installed._vectors, VALUES)
            resumed.embeddings.create.assert_called_once()
            self.assertEqual(resumed.embeddings.create.call_args.kwargs["input"], list(WORDS[4:]))

    def test_zero_vector_response_is_not_cached_and_can_be_retried(self):
        with TemporaryDirectory() as directory, tiny_dictionary(WORDS[:2]):
            destination = Path(directory) / "cache"
            invalid = fake_client(lambda **request: response(request["input"], [[0, 0], [1, 0]]))
            with self.assertRaisesRegex(ValueError, "수치"):
                vectors.install_vectors(destination, client=invalid)
            self.assertFalse(destination.exists())
            partials = destination.parent / ".cache-partials"
            self.assertEqual(list(partials.glob("*.npy")), [])
            self.assertFalse((partials / "000000.json").exists())
            installed = vectors.install_vectors(destination, client=fake_client())
            np.testing.assert_array_equal(installed._vectors, VALUES[:2])

    def test_atomic_json_failure_preserves_the_previous_checkpoint(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            path.write_text('{"previous":true}')
            with patch.object(Path, "replace", side_effect=OSError("interrupted rename")), \
                 self.assertRaisesRegex(OSError, "interrupted"):
                vectors._write_json(path, {"new": True})
            self.assertEqual(json.loads(path.read_text()), {"previous": True})
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_failure_cancels_queued_requests_instead_of_charging_the_whole_queue(self):
        words = tuple(f"단어{index}" for index in range(40))
        another_started, canceled = Event(), Event()
        calls, lock = [], Lock()
        cancel = Future.cancel

        def observe_cancel(future):
            result = cancel(future)
            if result:
                canceled.set()
            return result

        def request(**parameters):
            start = int(parameters["input"][0][2:])
            with lock:
                calls.append(start)
            if start == 0:
                return response(parameters["input"])
            if start == 2:
                self.assertTrue(another_started.wait(3))
                raise RuntimeError("stop queued requests")
            another_started.set()
            self.assertTrue(canceled.wait(3), "queued futures were not canceled")
            return response(parameters["input"])

        with TemporaryDirectory() as directory, tiny_dictionary(words), \
             patch.object(Future, "cancel", new=observe_cancel):
            destination = Path(directory) / "cache"
            with self.assertRaisesRegex(RuntimeError, "stop queued"):
                vectors.install_vectors(destination, client=fake_client(request))
            self.assertTrue(canceled.is_set())
            self.assertLess(len(calls), len(words) // 2)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
