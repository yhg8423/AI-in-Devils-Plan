from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from .vectors import WordVectors, install_vectors, load_vectors, read_tsv


class WordVectorsTest(unittest.TestCase):
    def test_raw_cosine_including_negative_values_and_unknown_words(self):
        vectors = WordVectors(["바다", "해양", "연필", "반대"], [[1, 0], [3, 4], [0, 1], [-1, 0]])
        self.assertEqual(vectors.similarity("바다", "바다"), 100)
        self.assertAlmostEqual(vectors.similarity("바다", "해양"), 60)
        self.assertEqual(vectors.similarity("바다", "연필"), 0)
        self.assertEqual(vectors.similarity("바다", "반대"), -100)
        self.assertEqual(vectors.similarity("해양", "바다"), vectors.similarity("바다", "해양"))
        with self.assertRaises(KeyError):
            vectors.similarity("바다", "없는단어")
        self.assertNotIn("없는단어", vectors)
        for values in ([[0, 0]], [[float("nan"), 1]], [[float("inf"), 1]], [[]], []):
            with self.subTest(values=values), self.assertRaises(ValueError):
                WordVectors(["바다"], values)

    def test_multiline_published_text_format_is_parsed_as_data(self):
        words, values = read_tsv(StringIO("0\t바다\t[3\n4]\n1\t해양\t[-2 0]\n"), 2)
        self.assertEqual(words, ["바다", "해양"])
        np.testing.assert_array_equal(values, [[3, 4], [-2, 0]])
        for text in ("1\t바다\t[1 2]\n", "0\t바다\t[1]\n", "0\t바다\t[1 2", "0\t바다\t[1 2 rubbish]\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                read_tsv(StringIO(text), 2)

    def test_cached_vectors_are_checked_before_use(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.npz"
            words, values = ["바다", "해양"], np.asarray([[1, 0], [3, 4]], dtype="<f4")
            expected = WordVectors(words, values, {"id": "fixture"})
            metadata = np.asarray(json.dumps(expected.metadata))
            np.savez(path, words=np.asarray(words), vectors=values, metadata=metadata)
            loaded = load_vectors(path)
            self.assertEqual(loaded.metadata, expected.metadata)
            self.assertAlmostEqual(loaded.similarity(*words), 60)
            values[0, 1] = 2
            np.savez(path, words=np.asarray(words), vectors=values, metadata=metadata)
            with self.assertRaisesRegex(ValueError, "체크섬"):
                load_vectors(path)
            np.savez(path, words=np.asarray(words), vectors=values, metadata=np.asarray("null"))
            with self.assertRaisesRegex(ValueError, "JSON 객체"):
                load_vectors(path)
            path.write_bytes(b"not a model")
            with self.assertRaisesRegex(ValueError, "읽을 수 없습니다"):
                load_vectors(path)

    def test_unverified_download_does_not_replace_an_existing_cache(self):
        with TemporaryDirectory() as directory:
            archive, destination = Path(directory) / "ko.zip", Path(directory) / "vectors.npz"
            archive.write_bytes(b"unexpected download")
            destination.write_bytes(b"previous model")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                install_vectors(archive, destination)
            self.assertEqual(destination.read_bytes(), b"previous model")
            with self.assertRaisesRegex(FileNotFoundError, "--download"):
                load_vectors(Path(directory) / "missing.npz")


if __name__ == "__main__":
    unittest.main()
