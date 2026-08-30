"""Tests for the FORGE deterministic V1 tokenizer."""

import unittest

from forge.tokenizer import STOPWORDS, tokenize


class TestTokenizerBasic(unittest.TestCase):
    """Core documented tokenizer behavior."""

    def test_lowercase(self):
        self.assertEqual(tokenize('HELLO WORLD'), ['hello', 'world'])

    def test_mixed_case(self):
        self.assertEqual(tokenize('PyThOn StOrAgE'), ['python', 'storage'])

    def test_punctuation(self):
        self.assertEqual(
            tokenize('Python, Storage & Search!'),
            ['python', 'storage', 'search'],
        )

    def test_example_from_spec(self):
        self.assertEqual(
            tokenize('Python, Storage & Search!'),
            ['python', 'storage', 'search'],
        )

    def test_mixed_punctuation(self):
        self.assertEqual(
            tokenize('Hello... (world)? [test]! {again}'),
            ['hello', 'world', 'test', 'again'],
        )

    def test_repeated_whitespace(self):
        self.assertEqual(
            tokenize('one   two\t\tthree\n\nfour'),
            ['one', 'two', 'three', 'four'],
        )

    def test_numbers(self):
        self.assertEqual(
            tokenize('order 123 item 456'),
            ['order', '123', 'item', '456'],
        )

    def test_numbers_only(self):
        self.assertEqual(tokenize('123 456'), ['123', '456'])

    def test_empty_input(self):
        self.assertEqual(tokenize(''), [])

    def test_punctuation_only(self):
        self.assertEqual(tokenize('!!! ??? --- ...'), [])

    def test_returns_list_of_str(self):
        result = tokenize('hello world')
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(t, str) for t in result))

    def test_non_string_raises(self):
        with self.assertRaises(TypeError):
            tokenize(b'bytes are not allowed')
        with self.assertRaises(TypeError):
            tokenize(123)


class TestTokenizerUnicode(unittest.TestCase):
    """Normal Unicode text must tokenize safely."""

    def test_accented_text(self):
        self.assertEqual(
            tokenize('Héllo Wörld — Café'),
            ['héllo', 'wörld', 'café'],
        )

    def test_unicode_mixed(self):
        self.assertEqual(
            tokenize('Straße, München ✓ 42'),
            ['straße', 'münchen', '42'],
        )

    def test_unicode_emoji_split(self):
        self.assertEqual(
            tokenize('python 🚀 storage'),
            ['python', 'storage'],
        )

    def test_non_ascii_lowercasing(self):
        self.assertEqual(tokenize('PYTHON ΣΤΟΡΑΓΕ'), ['python', 'στοραγε'])


class TestTokenizerStopwords(unittest.TestCase):
    """Stopword removal behavior."""

    def test_stopwords_removed(self):
        self.assertEqual(
            tokenize('the quick brown fox jumps over the lazy dog'),
            ['quick', 'brown', 'fox', 'jumps', 'over', 'lazy', 'dog'],
        )

    def test_stopword_lowercased_before_check(self):
        self.assertEqual(tokenize('THE QUICK BROWN'), ['quick', 'brown'])

    def test_only_stopwords(self):
        self.assertEqual(tokenize('the and of to a an'), [])

    def test_stopwords_interspersed(self):
        self.assertEqual(
            tokenize('python is great, and storage is fast'),
            ['python', 'great', 'storage', 'fast'],
        )

    def test_stopwords_set_contains_common(self):
        for word in ('the', 'and', 'of', 'to', 'a', 'an', 'in', 'is', 'for'):
            self.assertIn(word, STOPWORDS)

    def test_content_words_not_stopwords(self):
        for word in ('python', 'storage', 'search', 'quick', 'fast', 'engine'):
            self.assertNotIn(word, STOPWORDS)


class TestTokenizerDeterminism(unittest.TestCase):
    """Tokenization must be deterministic."""

    def _sample_texts(self):
        return [
            'Python, Storage & Search!',
            'the quick brown fox',
            'Héllo Wörld — Café 123',
            '',
            '!!!',
            'one   two three',
        ]

    def test_same_input_same_output(self):
        for text in self._sample_texts():
            self.assertEqual(tokenize(text), tokenize(text))

    def test_run_twice_yields_same_list(self):
        first = tokenize('Python, Storage & Search!')
        second = tokenize('Python, Storage & Search!')
        self.assertEqual(first, second)
        self.assertEqual(first, ['python', 'storage', 'search'])


if __name__ == '__main__':
    unittest.main()