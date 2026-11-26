import base64
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unicodedata
import unittest
from unittest.mock import Mock, patch

import numpy as np

from . import vectors


WORDS = ("바다", "해양", "연필")
VALUES = np.asarray([[1, 0], [0, 1], [1, 1]], dtype="<f4")


def model(values=VALUES, *, model_name=vectors.MODEL_ID):
    return vectors.WordVectors(WORDS, np.asarray(values, dtype="<f4").copy(), {
        "id": "fixture-embeddings", "model": model_name,
        "input_protocol": vectors.INPUT_PROTOCOL, "out_of_vocabulary": "reject"})


def client_for(base, *, hint=(3, 4), anchor=None, response_model=None, indices=(0, 1), error=None):
    def create(**request):
        if error is not None:
            raise error
        values = (hint, base._vectors[0] if anchor is None else anchor)
        rows = [SimpleNamespace(index=index, embedding=base64.b64encode(
            np.asarray(value, dtype="<f4").tobytes()).decode("ascii"))
            for index, value in zip(indices, values)]
        return SimpleNamespace(model=response_model or request["model"], data=list(reversed(rows)))

    return SimpleNamespace(embeddings=SimpleNamespace(create=Mock(side_effect=create)))


class HintEmbeddingsTest(unittest.TestCase):
    def test_in_dictionary_hint_never_calls_api(self):
        base = model()
        client = client_for(base, error=AssertionError("must stay offline"))
        with TemporaryDirectory() as directory:
            self.assertEqual(base.hint_similarity("바다", "연필", client=client, cache_dir=Path(directory)),
                             base.similarity("바다", "연필"))
            client.embeddings.create.assert_not_called()
            self.assertEqual(list(Path(directory).rglob("*.json")), [])

    def test_one_embedding_serves_multiple_secrets_instances_and_normalized_spelling(self):
        base = model()
        client = client_for(base)
        decomposed = "  " + unicodedata.normalize("NFD", "시장경제") + "  "
        with TemporaryDirectory() as directory:
            cache = Path(directory)
            self.assertAlmostEqual(base.hint_similarity("바다", decomposed, client=client, cache_dir=cache), 60)
            self.assertAlmostEqual(base.hint_similarity("해양", "시장경제", client=client, cache_dir=cache), 80)
            fresh = model()
            offline = client_for(fresh, error=AssertionError("must reuse persistent embedding"))
            self.assertAlmostEqual(fresh.hint_similarity("바다", "시장경제", client=offline, cache_dir=cache), 60)
            client.embeddings.create.assert_called_once()
            offline.embeddings.create.assert_not_called()
            request = client.embeddings.create.call_args.kwargs
            self.assertEqual(request["input"], ["시장경제", "바다"])
            self.assertEqual(request["model"], vectors.MODEL_ID)
            self.assertEqual(request["dimensions"], 2)
            self.assertEqual(request["encoding_format"], "base64")
            self.assertEqual(len(list(cache.rglob("*.json"))), 1)

    def test_changed_base_model_or_protocol_gets_a_separate_cache_entry(self):
        changed = VALUES.copy()
        changed[1] = [1, 2]
        models = (model(), model(changed), model(model_name="fixture-other-model"))
        with TemporaryDirectory() as directory:
            cache = Path(directory)
            for base in models:
                client = client_for(base)
                base.hint_similarity("바다", "시장경제", client=client, cache_dir=cache)
                client.embeddings.create.assert_called_once()
            with patch.object(vectors, "HINT_INPUT_PROTOCOL", "fixture-other-protocol"):
                fresh = model()
                client = client_for(fresh)
                fresh.hint_similarity("바다", "시장경제", client=client, cache_dir=cache)
                client.embeddings.create.assert_called_once()
            self.assertEqual(len(list(cache.rglob("*.json"))), len(models) + 1)

    def test_failed_or_malformed_response_is_not_cached_and_can_be_retried(self):
        cases = {
            "failed request": {"error": RuntimeError("temporary failure")},
            "wrong model": {"response_model": "wrong-model"},
            "duplicate indices": {"indices": (0, 0)},
            "wrong dimension": {"hint": (1, 2, 3)},
            "nonfinite": {"hint": (float("nan"), 1)},
            "zero hint": {"hint": (0, 0)},
            "zero anchor": {"anchor": (0, 0)},
            "changed anchor": {"anchor": (-1, 0)},
        }
        for name, options in cases.items():
            with self.subTest(case=name), TemporaryDirectory() as directory:
                base, cache = model(), Path(directory)
                with self.assertRaises((ValueError, RuntimeError)):
                    base.hint_similarity("바다", "시장경제", client=client_for(base, **options), cache_dir=cache)
                self.assertEqual(list(cache.rglob("*.json")), [])
                valid = client_for(base)
                self.assertAlmostEqual(base.hint_similarity("바다", "시장경제", client=valid, cache_dir=cache), 60)
                valid.embeddings.create.assert_called_once()

    def test_oov_hint_does_not_change_fixed_vocabulary_nearest_or_base_metadata(self):
        base = model()
        before = deepcopy(base.metadata)
        fixed_nearest = base.nearest("바다")
        with TemporaryDirectory() as directory:
            score = base.hint_similarity("바다", "시장경제", client=client_for(base, hint=(1, 0)),
                                         cache_dir=Path(directory))
        self.assertEqual(score, 100)
        self.assertGreater(score, fixed_nearest["similarity"])
        self.assertEqual(base.nearest("바다"), fixed_nearest)
        self.assertEqual(base._words, WORDS)
        np.testing.assert_array_equal(base._vectors, VALUES)
        self.assertNotIn("시장경제", base)
        self.assertEqual(base.metadata, before)
        scoring = vectors.scorer_metadata(base)
        self.assertEqual(scoring["sha256"], before["sha256"])
        self.assertEqual(scoring["out_of_vocabulary"], "embed_on_demand")
        scoring["out_of_vocabulary"] = "changed"
        self.assertEqual(base.metadata, before)

    def test_tampered_persistent_vector_is_rejected_without_api_call(self):
        base = model()
        with TemporaryDirectory() as directory:
            cache = Path(directory)
            base.hint_similarity("바다", "시장경제", client=client_for(base), cache_dir=cache)
            paths = list(cache.rglob("*.json"))
            self.assertEqual(len(paths), 1)
            path = paths[0]
            entry = json.loads(path.read_text())
            key = next(key for key in ("vector", "values", "embedding") if key in entry)
            entry[key][0] += 1
            path.write_text(json.dumps(entry))
            fresh = model()
            offline = client_for(fresh, error=AssertionError("must reject corrupt cache"))
            with self.assertRaises(ValueError):
                fresh.hint_similarity("바다", "시장경제", client=offline, cache_dir=cache)
            offline.embeddings.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
