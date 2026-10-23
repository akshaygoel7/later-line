import json
import unittest

from later_line import (
    accept,
    first_words,
    parse_model_line,
    shrink_one,
    shrink_pile,
    split_pile,
)


SOURCE = (
    "Reply to Meera about the menu site. She wrote that the logo is still missing "
    "and the invoice should be split into two payments."
)


class AcceptTests(unittest.TestCase):
    def test_keeps_a_shorter_line_that_names_the_subject(self):
        self.assertTrue(accept(SOURCE, "Reply to Meera about the invoice"))

    def test_rejects_a_line_that_is_not_shorter(self):
        short = "Reply to Meera about the invoice"
        self.assertFalse(accept(short, short + " tomorrow"))

    def test_rejects_a_line_that_drops_every_concrete_word(self):
        self.assertFalse(accept(SOURCE, "Do the small thing tomorrow"))

    def test_rejects_a_line_that_pretends_the_task_is_done(self):
        self.assertFalse(accept(SOURCE, "Meera invoice addressed"))

    def test_rejects_more_than_twelve_words(self):
        line = "Reply Meera menu logo invoice payment extra words keep going past limit now"
        self.assertGreater(len(line.split()), 12)
        self.assertFalse(accept(SOURCE, line))


class ParseTests(unittest.TestCase):
    def test_reads_json(self):
        self.assertEqual(parse_model_line('{"line":"Reply to Meera"}'), "Reply to Meera")

    def test_reads_json_wrapped_in_prose(self):
        self.assertEqual(
            parse_model_line('Sure. {"line":"Reply to Meera"} thanks'),
            "Reply to Meera",
        )

    def test_empty_when_there_is_no_line(self):
        self.assertEqual(parse_model_line("not json"), "")
        self.assertEqual(parse_model_line('{"note":"hi"}'), "")


class ShrinkTests(unittest.TestCase):
    def test_does_not_ask_when_the_task_is_already_short(self):
        asked = []

        def ask(source):
            asked.append(source)
            return "unused"

        row = shrink_one("Book the dentist", ask)
        self.assertEqual(asked, [])
        self.assertEqual(row["path"], "already_short")
        self.assertEqual(row["line"], "Book the dentist")

    def test_throws_away_a_longer_model_line(self):
        def ask(source):
            return source + " and also write a full plan for next week"

        row = shrink_one(SOURCE, ask)
        self.assertEqual(row["path"], "fallback")
        self.assertEqual(row["line"], first_words(SOURCE))
        self.assertIn("longer than 12 words", row["reason"])

    def test_keeps_a_model_line_that_passes(self):
        def ask(source):
            return "Reply to Meera about the invoice"

        row = shrink_one(SOURCE, ask)
        self.assertEqual(row["path"], "model")
        self.assertEqual(row["line_words"], 6)
        self.assertLess(row["line_words"], row["source_words"])

    def test_pile_counts_words_you_skip(self):
        def ask(source):
            return "Reply to Meera about the invoice"

        report = shrink_pile([SOURCE, "Book the dentist"], ask)
        self.assertEqual(report["model_kept"], 1)
        self.assertEqual(report["already_short"], 1)
        self.assertGreater(report["words_not_reread"], 0)

    def test_unreachable_model_falls_back(self):
        def ask(source):
            raise TimeoutError("ollama down")

        row = shrink_one(SOURCE, ask)
        self.assertEqual(row["path"], "fallback")
        self.assertIn("unreachable", row["reason"])


class PileTests(unittest.TestCase):
    def test_blank_lines_split_tasks(self):
        text = "First task is long enough.\n\nSecond task is also here.\n"
        self.assertEqual(
            split_pile(text),
            ["First task is long enough.", "Second task is also here."],
        )


if __name__ == "__main__":
    unittest.main()
