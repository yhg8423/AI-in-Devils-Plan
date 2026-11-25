from io import StringIO
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from .vectors import WordVectors, install_vectors, load_vectors, read_fasttext


class WordVectorsTest(unittest.TestCase):
    def test_nearest_search_excludes_answer_non_nouns_and_proper_names(self):
        vectors = WordVectors(["바다", "학교의", "라인강", "sea", "쉘부르의", "살윈", "바닷", "해양", "대양"],
                              [[1, 0], [1, 0], [1, 0], [1, 0], [1, 0], [1, 0], [1, 0], [3, 4], [0, 1]])
        closest = vectors.nearest("바다")
        self.assertEqual(closest["word"], "해양")
        self.assertAlmostEqual(closest["similarity"], 60)
        self.assertTrue(vectors.is_hint(closest["word"]))
        for word in ("학교의", "라인강", "sea", "쉘부르의", "살윈", "바닷", "없는단어", None, ["해양"]):
            with self.subTest(word=word):
                self.assertFalse(vectors.is_hint(word))
        closest["word"] = "변경"
        self.assertEqual(vectors.nearest("바다")["word"], "해양")
        tied = WordVectors(["바다", "대양", "해양"], [[1, 0], [-1, 0], [-1, 0]])
        self.assertEqual(tied.nearest("바다"), {"word": "대양", "similarity": -100})
        with self.assertRaises(KeyError):
            vectors.nearest("없는단어")
        with self.assertRaisesRegex(ValueError, "다른 명사"):
            WordVectors(["바다", "학교의"], [[1, 0], [1, 0]]).nearest("바다")

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

    def test_official_text_format_is_complete_and_memory_mapped(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.npy"
            words, values = read_fasttext(StringIO("2 2\n바다 3 4\n해양 -2 0\n"), path, dimensions=2, vocabulary=2)
            self.assertEqual(words, ["바다", "해양"])
            self.assertIsInstance(values, np.memmap)
            np.testing.assert_array_equal(values, [[3, 4], [-2, 0]])
            for text in ("2 3\n", "2 2\n바다 1\n", "2 2\n바다 1 2\n", "2 2\n바다 1 2 rubbish\n해양 2 3\n",
                         "2 2\n바다 1 2\n해양 2 3\n추가 4 5\n"):
                with self.subTest(text=text), self.assertRaises(ValueError):
                    read_fasttext(StringIO(text), path, dimensions=2, vocabulary=2)

    def test_nearest_and_validation_cross_chunk_boundaries(self):
        with patch("games.hidden_word.vectors.BLOCK_ROWS", 1):
            vectors = WordVectors(["바다", "연필", "해양"], [[1, 0], [0, 1], [3, 4]])
            self.assertEqual(vectors.nearest("바다")["word"], "해양")
            self.assertAlmostEqual(vectors.similarity("바다", "해양"), 60)
            with self.assertRaises(ValueError):
                WordVectors(["바다", "연필"], [[1, 0], [float("nan"), 1]])

    def test_cached_vectors_are_checked_before_use(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model"
            path.mkdir()
            words, values = ["바다", "해양"], np.asarray([[1, 0], [3, 4]], dtype="<f4")
            expected = WordVectors(words, values, {"id": "fixture"})
            (path / "metadata.json").write_text(json.dumps(expected.metadata))
            (path / "words.json").write_text(json.dumps(words))
            np.save(path / "vectors.npy", values)
            loaded = load_vectors(path)
            self.assertEqual(loaded.metadata, expected.metadata)
            self.assertAlmostEqual(loaded.similarity(*words), 60)
            self.assertIsInstance(loaded._vectors.base, np.memmap)
            self.assertFalse(loaded._vectors.flags.writeable)
            values = values.copy()
            values[0, 1] = 2
            np.save(path / "vectors.npy", values)
            with self.assertRaisesRegex(ValueError, "체크섬"):
                load_vectors(path)
            (path / "metadata.json").write_text("null")
            with self.assertRaisesRegex(ValueError, "JSON 객체"):
                load_vectors(path)
            (path / "metadata.json").write_text("not a model")
            with self.assertRaisesRegex(ValueError, "읽을 수 없습니다"):
                load_vectors(path)

    def test_verified_archive_installation_and_corruption_leave_cache_atomic(self):
        with TemporaryDirectory() as directory:
            archive, destination = Path(directory) / "model.gz", Path(directory) / "model"
            archive.write_bytes(gzip.compress("3 2\n바다 1 0\n해양 3 4\n".encode() + b"\xed\xa0\x80 0 1\n"))
            with patch("games.hidden_word.vectors.ARCHIVE_SHA256", sha256(archive.read_bytes()).hexdigest()), \
                 patch("games.hidden_word.vectors.DIMENSIONS", 2), patch("games.hidden_word.vectors.VOCABULARY", 3):
                installed = install_vectors(archive, destination)
                loaded = load_vectors(destination)
                self.assertEqual(installed.metadata, loaded.metadata)
                self.assertAlmostEqual(loaded.similarity("바다", "해양"), 60)
                self.assertEqual(loaded.metadata["out_of_vocabulary"], "reject")
                self.assertEqual(loaded.metadata["vocabulary"], 3)
                self.assertEqual(loaded._words[-1].encode("utf-8", errors="surrogateescape"), b"\xed\xa0\x80")
                self.assertEqual(loaded.nearest("바다")["word"], "해양")
                with patch("games.hidden_word.vectors.urlopen", side_effect=AssertionError("must reuse cache")):
                    self.assertEqual(install_vectors(destination=destination).metadata, installed.metadata)
            broken = Path(directory) / "broken"
            archive.write_bytes(gzip.compress("2 2\n바다 1 0\n해양 nan 4\n".encode()))
            with patch("games.hidden_word.vectors.ARCHIVE_SHA256", sha256(archive.read_bytes()).hexdigest()), \
                 patch("games.hidden_word.vectors.DIMENSIONS", 2), patch("games.hidden_word.vectors.VOCABULARY", 2):
                with self.assertRaisesRegex(ValueError, "유한"):
                    install_vectors(archive, broken)
                self.assertFalse(broken.exists())
                self.assertEqual(list(Path(directory).glob(".fasttext-*")), [])

    def test_unverified_download_does_not_replace_an_existing_cache(self):
        with TemporaryDirectory() as directory:
            archive, destination = Path(directory) / "model.gz", Path(directory) / "cache"
            archive.write_bytes(b"unexpected download")
            destination.write_bytes(b"previous model")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                install_vectors(archive, destination)
            self.assertEqual(destination.read_bytes(), b"previous model")
            with self.assertRaisesRegex(FileNotFoundError, "--download"):
                load_vectors(Path(directory) / "missing")


if __name__ == "__main__":
    unittest.main()
