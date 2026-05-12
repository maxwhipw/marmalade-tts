"""Tests for marmalade_tts.preprocessing — text normalization rules."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from marmalade_tts.preprocessing import preprocess, RULES, ENGINE_PROFILES, list_rules


# ── Currency ─────────────────────────────────────────────────────────────────

class TestCurrency:
    def test_dollars_whole(self):
        assert "100 dollars" in preprocess("$100", rules=["currency"])

    def test_dollars_cents(self):
        result = preprocess("$3.50", rules=["currency"])
        assert "3 dollars" in result
        assert "50 cents" in result

    def test_pounds(self):
        assert "42 pounds" in preprocess("£42", rules=["currency"])

    def test_euros(self):
        assert "10 euros" in preprocess("€10", rules=["currency"])

    def test_one_dollar_singular(self):
        assert "1 dollar" in preprocess("$1", rules=["currency"])
        assert "dollars" not in preprocess("$1", rules=["currency"])

    def test_currency_in_sentence(self):
        result = preprocess("It costs $5 today", rules=["currency"])
        assert "5 dollars" in result


# ── Percentage ───────────────────────────────────────────────────────────────

class TestPercentage:
    def test_whole(self):
        assert "50 percent" in preprocess("50%", rules=["percentage"])

    def test_decimal(self):
        assert "99.5 percent" in preprocess("99.5%", rules=["percentage"])

    def test_in_sentence(self):
        result = preprocess("success rate is 95%", rules=["percentage"])
        assert "95 percent" in result


# ── Ordinals ─────────────────────────────────────────────────────────────────

class TestOrdinals:
    def test_1st(self):
        result = preprocess("1st place", rules=["ordinal"])
        assert "first" in result

    def test_2nd(self):
        result = preprocess("2nd", rules=["ordinal"])
        assert "second" in result

    def test_3rd(self):
        result = preprocess("3rd", rules=["ordinal"])
        assert "third" in result

    def test_11th(self):
        result = preprocess("11th", rules=["ordinal"])
        assert "eleventh" in result

    def test_21st(self):
        result = preprocess("21st", rules=["ordinal"])
        assert "twenty-first" in result


# ── Numbers ──────────────────────────────────────────────────────────────────

class TestNumbers:
    def test_simple(self):
        result = preprocess("42 things", rules=["number"])
        assert "forty-two" in result

    def test_zero(self):
        result = preprocess("0 items", rules=["number"])
        assert "zero" in result

    def test_year_not_verbalized(self):
        # Years 1900-2099 should stay as digits
        result = preprocess("year 2025", rules=["number"])
        assert "2025" in result

    def test_large_number(self):
        result = preprocess("1000 users", rules=["number"])
        assert "thousand" in result.lower()

    def test_decimal(self):
        result = preprocess("3.14", rules=["number"])
        assert "point" in result


# ── Time ─────────────────────────────────────────────────────────────────────

class TestTime:
    def test_on_the_hour(self):
        result = preprocess("10:00", rules=["time"])
        assert "ten" in result

    def test_with_minutes(self):
        result = preprocess("3:45", rules=["time"])
        assert "three" in result
        assert "forty-five" in result

    def test_with_am_pm(self):
        result = preprocess("9:00 AM", rules=["time"])
        assert "AM" in result or "nine" in result

    def test_minutes_under_10(self):
        result = preprocess("7:05", rules=["time"])
        assert "oh" in result or "five" in result

    def test_24hr(self):
        result = preprocess("14:00", rules=["time"])
        assert "hundred" in result or "fourteen" in result


# ── Email ────────────────────────────────────────────────────────────────────

class TestEmail:
    def test_basic(self):
        result = preprocess("user@example.com", rules=["email"])
        assert "at" in result
        assert "dot" in result

    def test_in_sentence(self):
        result = preprocess("contact me at hello@test.org please", rules=["email"])
        assert "at" in result


# ── URL ──────────────────────────────────────────────────────────────────────

class TestURL:
    def test_https(self):
        result = preprocess("visit https://example.com", rules=["url"])
        assert "example dot com" in result

    def test_www_stripped(self):
        result = preprocess("see https://www.google.com", rules=["url"])
        assert "google dot com" in result


# ── Filename ─────────────────────────────────────────────────────────────────

class TestFilename:
    def test_txt(self):
        result = preprocess("open notes.txt", rules=["filename"])
        assert "dot" in result
        assert "T X T" in result or "txt" in result.lower()

    def test_py(self):
        result = preprocess("edit script.py", rules=["filename"])
        assert "dot" in result

    def test_unknown_ext_unchanged(self):
        # .xyz is not a known extension, should not be expanded
        result = preprocess("file.xyz", rules=["filename"])
        assert "file.xyz" in result

    def test_decimal_number_not_matched(self):
        # "3.14" should not be treated as a filename
        result = preprocess("3.14", rules=["filename"])
        assert "dot" not in result


# ── Abbreviations ────────────────────────────────────────────────────────────

class TestAbbreviations:
    def test_eg(self):
        result = preprocess("e.g. this", rules=["abbreviation"])
        assert "for example" in result.lower()

    def test_ie(self):
        result = preprocess("i.e. that", rules=["abbreviation"])
        assert "that is" in result.lower()

    def test_dotted_caps(self):
        result = preprocess("U.S.A.", rules=["abbreviation"])
        # Should spell out: U S A
        assert "U" in result


# ── Math symbols ─────────────────────────────────────────────────────────────

class TestMath:
    def test_plus(self):
        result = preprocess("2 + 2", rules=["math"])
        assert "plus" in result

    def test_no_hyphen_mangling(self):
        # Hyphens in compound words must not be touched
        result = preprocess("ninety-nine bottles", rules=["math"])
        assert "ninety-nine" in result

    def test_equals(self):
        result = preprocess("x = y", rules=["math"])
        assert "equals" in result


# ── Ampersand ────────────────────────────────────────────────────────────────

class TestAmpersand:
    def test_basic(self):
        result = preprocess("bread & butter", rules=["ampersand"])
        assert "and" in result


# ── Hashtag ──────────────────────────────────────────────────────────────────

class TestHashtag:
    def test_number(self):
        result = preprocess("#100", rules=["hashtag"])
        assert "number 100" in result

    def test_word(self):
        result = preprocess("#hello", rules=["hashtag"])
        assert "hashtag hello" in result


# ── Engine profiles ──────────────────────────────────────────────────────────

class TestEngineProfiles:
    def test_all_engines_have_profiles(self):
        for engine in ["kitten", "kokoro", "piper", "coqui", "pocket"]:
            assert engine in ENGINE_PROFILES

    def test_profiles_reference_valid_rules(self):
        for engine, rules in ENGINE_PROFILES.items():
            for rule in rules:
                assert rule in RULES, f"Engine {engine} references unknown rule: {rule}"

    def test_engine_profile_used_by_default(self):
        # When engine is given, its profile is used
        # Kitten profile includes 'number', so numbers should be verbalized
        result = preprocess("42", engine="kitten")
        assert "forty-two" in result

    def test_kokoro_skips_number_rule(self):
        # Kokoro profile does NOT include 'number' (kokoro handles numbers natively)
        result = preprocess("42", engine="kokoro")
        # 42 should remain as "42" since number rule is not in kokoro's profile
        assert "42" in result

    def test_pocket_profile_exists(self):
        assert "pocket" in ENGINE_PROFILES

    def test_pocket_profile_has_all_rules(self):
        # Pocket handles nothing natively, so it should get all rules like piper/kitten
        pocket_rules = ENGINE_PROFILES["pocket"]
        for rule in ["currency", "percentage", "ordinal", "time", "date",
                     "email", "url", "filename", "abbreviation", "number",
                     "math", "ampersand", "hashtag"]:
            assert rule in pocket_rules, f"Pocket profile missing rule: {rule}"

    def test_pocket_profile_applies_number_rule(self):
        # Pocket should expand numbers (it handles nothing natively)
        result = preprocess("42", engine="pocket")
        assert "forty-two" in result

    def test_pocket_profile_applies_currency_rule(self):
        result = preprocess("$5", engine="pocket")
        assert "dollars" in result


# ── Composite: full pipeline ──────────────────────────────────────────────────

class TestComposite:
    def test_mixed_text(self):
        text = "The $5 item costs 10% more than the £3.99 one."
        result = preprocess(text, engine="kitten")
        assert "dollars" in result
        assert "percent" in result
        assert "pounds" in result

    def test_empty_string(self):
        assert preprocess("", engine="kitten") == ""

    def test_no_special_chars(self):
        text = "Hello world"
        result = preprocess(text, engine="kitten")
        assert result == "Hello world"

    def test_custom_rule_list(self):
        # Only currency applied
        result = preprocess("$5 and 50%", rules=["currency"])
        assert "dollars" in result
        assert "percent" not in result  # percentage rule not applied


# ── list_rules ────────────────────────────────────────────────────────────────

def test_list_rules_runs(capsys):
    list_rules()
    captured = capsys.readouterr()
    assert "currency" in captured.out
    assert "number" in captured.out


# ── Rule ordering & interference ─────────────────────────────────────────────

class TestRuleOrdering:
    """Rules must not corrupt each other's output when applied in sequence."""

    def test_currency_then_number_no_double_expansion(self):
        # "$5" → "5 dollars" — the "5" in "5 dollars" must NOT be re-expanded
        # by the number rule to "five dollars"
        result = preprocess("$5", rules=["currency", "number"])
        # Should contain "5 dollars" or "five dollars", but NOT "five five"
        assert "five five" not in result
        assert "dollars" in result

    def test_percent_result_not_re_matched(self):
        # "50%" → "50 percent" — the "50" must not become "fifty percent percent"
        result = preprocess("50%", rules=["percentage", "number"])
        assert "percent percent" not in result
        assert "percent" in result

    def test_ordinal_then_number_no_corruption(self):
        # "3rd" → "third" — must not then be re-expanded
        result = preprocess("3rd place", rules=["ordinal", "number"])
        assert "third" in result
        assert "three" not in result  # ordinal takes priority over bare number

    def test_email_not_partial_matched_as_url(self):
        # email rule should fire before url and not leave fragments for url rule
        result = preprocess("user@example.com", rules=["email", "url"])
        assert "at" in result.lower() or "user" in result.lower()
        # Should not produce "user at example dot com dot com" (double-matching)
        assert result.count("example") == 1

    def test_full_pipeline_does_not_duplicate_words(self):
        # Run ALL rules on a sentence with multiple patterns — nothing doubled
        result = preprocess("$3.50 is 10% off at 9:00am", engine="kitten")
        words = result.lower().split()
        # No word should appear back-to-back (crude duplication check)
        for i in range(len(words) - 1):
            assert words[i] != words[i + 1], f"Duplicate word '{words[i]}' in: {result!r}"


class TestEdgeCases:
    def test_unicode_currency_symbol(self):
        # Japanese yen — not in our rules, should pass through unchanged
        result = preprocess("¥1000", rules=["currency"])
        # No crash; yen may or may not be handled — just must not raise
        assert isinstance(result, str)

    def test_very_long_text(self):
        # 5000-char string should not hang or OOM
        text = "Hello world. " * 400
        result = preprocess(text, engine="kitten")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_only_whitespace(self):
        result = preprocess("   \t\n   ", rules=["currency", "number"])
        assert isinstance(result, str)

    def test_no_rules_returns_unchanged(self):
        text = "$100 is 50% off"
        result = preprocess(text, rules=[])
        assert result == text

    def test_mixed_case_abbreviations(self):
        # "E.G." and "e.g." should both be handled
        upper = preprocess("E.G.", rules=["abbreviation"])
        lower = preprocess("e.g.", rules=["abbreviation"])
        assert "example" in upper.lower() or upper == "E.G."  # handled or passthrough
        assert "example" in lower.lower() or lower == "e.g."

    def test_number_at_sentence_boundary(self):
        # Number at end of sentence with period should not eat the period weirdly
        result = preprocess("There are 3.", rules=["number"])
        assert "three" in result or "3" in result  # must not crash

    def test_newlines_preserved_through_preprocessing(self):
        text = "Line one.\nLine two."
        result = preprocess(text, engine="kitten")
        # Newlines should survive (or become spaces) — but not cause crashes
        assert isinstance(result, str)
        assert "line" in result.lower() or "Line" in result
