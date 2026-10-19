import unittest

import textkit


class TestTextkit(unittest.TestCase):
    def test_placeholder(self) -> None:
        self.assertTrue(callable(textkit.count_vowels))
        self.assertTrue(callable(textkit.reverse_words))
