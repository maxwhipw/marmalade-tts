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

    def test_ex(self):
        result = preprocess("This works, ex. this sentence.", rules=["abbreviation"])
        assert "for example" in result.lower()

    def test_no_match_inside_words(self):
        # Abbreviations must not fire on word endings: Rolex./craft./catalyst.
        for text in ("I sold my Rolex. It was old.",
                     "Nice craft. Very good.",
                     "The catalyst. failed."):
            assert preprocess(text, rules=["abbreviation"]) == text


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


# ── Emoji ────────────────────────────────────────────────────────────────────

class TestEmoji:
    def test_single_emoji_stripped(self):
        # Without this rule, espeak-backed engines would say "loudly crying face".
        result = preprocess("I miss you 😭", rules=["emoji"])
        assert "😭" not in result
        assert "I miss you" in result

    def test_multiple_emojis_stripped(self):
        result = preprocess("Hello 🤣 world 😡 again", rules=["emoji"])
        assert "🤣" not in result and "😡" not in result
        assert "Hello world again" == result

    def test_zwj_sequence_fully_stripped(self):
        # ZWJ-joined family emoji (👨‍👩‍👧) — every codepoint must go.
        result = preprocess("our \U0001F468‍\U0001F469‍\U0001F467 here",
                            rules=["emoji"])
        for ch in ("\U0001F468", "\U0001F469", "\U0001F467", "‍"):
            assert ch not in result
        assert "our here" == result

    def test_dingbats_stripped(self):
        # ☀ ★ ✓ live in the misc-symbols/dingbats range.
        result = preprocess("sunny ☀ day", rules=["emoji"])
        assert "☀" not in result
        assert "sunny day" == result

    def test_flag_pair_stripped(self):
        # Regional indicator halves that combine into country flags.
        result = preprocess("hello \U0001F1FA\U0001F1F8 world", rules=["emoji"])
        for ch in ("\U0001F1FA", "\U0001F1F8"):
            assert ch not in result
        assert "hello world" == result

    def test_no_emoji_left_untouched(self):
        assert preprocess("plain ascii only", rules=["emoji"]) == "plain ascii only"

    def test_emoji_at_start_and_end_trimmed(self):
        result = preprocess("🤣 middle 😭", rules=["emoji"])
        assert result == "middle"

    def test_emoji_only_text_collapses_to_empty(self):
        # Caller has to decide what to do with empty text — preprocess just
        # returns the empty string.
        assert preprocess("🤣😭", rules=["emoji"]) == ""


# ── Markdown ─────────────────────────────────────────────────────────────────

class TestMarkdown:
    def test_bold_stars_stripped(self):
        assert preprocess("**hello**", rules=["markdown"]) == "hello"

    def test_bold_underscores_stripped(self):
        assert preprocess("__hello__", rules=["markdown"]) == "hello"

    def test_italic_stars_stripped(self):
        assert preprocess("*italic*", rules=["markdown"]) == "italic"

    def test_italic_underscores_stripped(self):
        assert preprocess("_italic_", rules=["markdown"]) == "italic"

    def test_snake_case_identifier_not_italicised(self):
        # snake_case_var must not be eaten by the italic-underscore rule.
        result = preprocess("call snake_case_var here", rules=["markdown"])
        assert "snake_case_var" in result

    def test_inline_code_stripped(self):
        assert preprocess("run `npm install`", rules=["markdown"]) == "run npm install"

    def test_strikethrough_stripped(self):
        assert preprocess("~~gone~~", rules=["markdown"]) == "gone"

    def test_link_text_kept_target_dropped(self):
        # [text](url) → text — link target must NOT appear in output.
        result = preprocess("see [the docs](https://example.com/docs)",
                            rules=["markdown"])
        assert "the docs" in result
        assert "example.com" not in result
        assert "https" not in result

    def test_image_alt_kept_target_dropped(self):
        result = preprocess("![a cat](https://example.com/cat.png)",
                            rules=["markdown"])
        assert "a cat" in result
        assert "example.com" not in result

    def test_heading_hashes_stripped(self):
        result = preprocess("# Title\n## Subtitle\n### Sub-sub",
                            rules=["markdown"])
        assert "#" not in result
        assert "Title" in result
        assert "Subtitle" in result
        assert "Sub-sub" in result

    def test_blockquote_marker_stripped(self):
        result = preprocess("> quoted line", rules=["markdown"])
        assert ">" not in result
        assert "quoted line" in result

    def test_bullet_dash_stripped(self):
        result = preprocess("- first\n- second", rules=["markdown"])
        assert "first" in result
        assert "second" in result
        # Leading bullet markers gone (an interior "-" in a word is fine).
        assert "- first" not in result

    def test_bullet_asterisk_stripped(self):
        result = preprocess("* item one\n* item two", rules=["markdown"])
        assert "item one" in result
        assert "item two" in result

    def test_bullet_plus_stripped(self):
        result = preprocess("+ a\n+ b", rules=["markdown"])
        assert "a" in result and "b" in result

    def test_fenced_code_block_content_kept(self):
        text = "```python\nprint('hi')\n```"
        result = preprocess(text, rules=["markdown"])
        assert "```" not in result
        assert "print" in result

    def test_unbalanced_tokens_do_not_crash(self):
        # A stray "*" or "**" should not blow up; we just leave it alone.
        for sample in ("**unbalanced", "lone * star", "left __ right",
                       "trailing `", "[broken](", "![no close"):
            result = preprocess(sample, rules=["markdown"])
            assert isinstance(result, str)

    def test_link_target_not_verbalized_full_pipeline(self):
        # Through the full engine pipeline, markdown must beat url — the
        # link target should never reach the url rule.
        result = preprocess("read [the post](https://example.com/x)",
                            engine="kitten")
        assert "the post" in result
        assert "example dot com" not in result

    # ── Python dunders must survive the bold-underscore rule ────────────
    # Regression: `(?<!\w)__(...)__(?!\w)` alone happily matches `__init__`
    # and friends (boundaries are satisfied at string/whitespace edges),
    # rewriting them to `init`, `name`, `main`, `repr` in any prose that
    # discusses Python internals. The rule keeps a denylist of well-known
    # dunder identifiers so the whole `__name__` token is left intact.

    def test_dunder_init_not_bolded(self):
        assert preprocess("__init__", rules=["markdown"]) == "__init__"

    def test_dunder_name_not_bolded(self):
        assert preprocess("__name__", rules=["markdown"]) == "__name__"

    def test_dunder_main_not_bolded(self):
        assert preprocess("__main__", rules=["markdown"]) == "__main__"

    def test_dunder_repr_not_bolded(self):
        assert preprocess("__repr__", rules=["markdown"]) == "__repr__"

    def test_dunder_in_sentence_survives(self):
        result = preprocess("Use the __init__ method to construct.",
                            rules=["markdown"])
        assert "__init__" in result
        assert "init method" not in result

    def test_multiple_dunders_in_one_line(self):
        result = preprocess("Override __eq__ and __hash__ together.",
                            rules=["markdown"])
        assert "__eq__" in result
        assert "__hash__" in result

    def test_bold_hello_still_works(self):
        # Baseline: non-dunder bold-underscore still strips to inner text.
        assert preprocess("__hello__", rules=["markdown"]) == "hello"

    def test_bold_important_still_works(self):
        # Common markdown emphasis word — not a dunder, must strip.
        assert preprocess("__important__", rules=["markdown"]) == "important"

    def test_single_underscore_italic_still_works(self):
        # The italic rule is unrelated to the dunder fix; confirm it
        # didn't get caught in the crossfire.
        assert preprocess("_single_", rules=["markdown"]) == "single"

    def test_triple_underscore_left_alone(self):
        # `___three___` is malformed for both bold and italic — neither
        # rule should fire. The behavior we document: no change.
        assert preprocess("___three___", rules=["markdown"]) == "___three___"


# ── HTML ─────────────────────────────────────────────────────────────────────

class TestHTML:
    def test_simple_tags_stripped(self):
        assert preprocess("<p>hi</p>", rules=["html"]) == "hi"

    def test_adjacent_tags_get_a_space(self):
        # <p>a</p><p>b</p> → "a b", not "ab".
        result = preprocess("<p>a</p><p>b</p>", rules=["html"])
        assert result == "a b"

    def test_attributes_dropped(self):
        result = preprocess('<a href="x">link</a>', rules=["html"])
        assert result == "link"

    def test_entity_amp(self):
        assert preprocess("Tom &amp; Jerry", rules=["html"]) == "Tom & Jerry"

    def test_entity_nbsp(self):
        result = preprocess("a&nbsp;b", rules=["html"])
        # &nbsp; decodes to U+00A0; that's still a space character — the
        # final whitespace-collapse turns it into a regular space.
        assert "a" in result and "b" in result

    def test_entity_numeric(self):
        # &#39; → '
        assert preprocess("it&#39;s", rules=["html"]) == "it's"

    def test_entity_lt_gt_not_re_stripped(self):
        # Tag-strip first, THEN unescape, so &lt;script&gt; survives as <script>
        # in output (the entity-form was the author's intent, not a real tag).
        result = preprocess("write &lt;script&gt; tags", rules=["html"])
        assert "<script>" in result


# ── Pronunciation dictionary ─────────────────────────────────────────────────

class TestPronounce:
    """The `pronounce` rule reads a user YAML and does whole-word, case-
    insensitive substitution. All tests share a fixture that points the
    loader at a tmp file and resets the module-level cache."""

    @pytest.fixture(autouse=True)
    def _reset_cache(self, monkeypatch, tmp_path):
        import marmalade_tts.preprocessing as pp
        self.path = tmp_path / "pronunciations.yaml"
        monkeypatch.setattr(pp, "PRONUNCIATIONS_PATH", str(self.path))
        monkeypatch.setattr(pp, "_PRONUNCIATIONS", None)
        monkeypatch.setattr(pp, "_PRONOUNCE_RE", None)
        yield
        # Restore None after test so the next test gets a fresh load.
        monkeypatch.setattr(pp, "_PRONUNCIATIONS", None)
        monkeypatch.setattr(pp, "_PRONOUNCE_RE", None)

    def _write(self, body: str):
        self.path.write_text(body)

    def test_basic_replacement(self):
        self._write("kubectl: kube-cuttle\n")
        result = preprocess("run kubectl now", rules=["pronounce"])
        assert "kube-cuttle" in result
        assert "kubectl" not in result

    def test_case_insensitive(self):
        self._write("regex: REE-jex\n")
        result = preprocess("Regex and REGEX and regex", rules=["pronounce"])
        # All three forms get replaced with the verbatim value.
        assert result.count("REE-jex") == 3

    def test_word_boundary_no_partial_match(self):
        # "regex" must NOT match inside "regexp".
        self._write("regex: REE-jex\n")
        result = preprocess("regexp is not regex", rules=["pronounce"])
        assert "regexp" in result
        assert "REE-jex" in result

    def test_hyphenated_key_matches(self):
        self._write("marmalade-tts: marmalade T T S\n")
        result = preprocess("install marmalade-tts today", rules=["pronounce"])
        assert "marmalade T T S" in result
        assert "marmalade-tts" not in result

    def test_longest_first_ordering(self):
        # "marmalade-tts" must win over "marmalade" when both are keys.
        self._write("marmalade: jam\nmarmalade-tts: marmalade T T S\n")
        result = preprocess("marmalade-tts is great", rules=["pronounce"])
        assert "marmalade T T S" in result
        # The "marmalade" key must not have eaten the prefix first.
        assert "jam-tts" not in result

    def test_missing_file_is_noop(self):
        # No file at the path → rule does nothing, text untouched.
        assert not self.path.exists()
        text = "kubectl regex marmalade-tts"
        assert preprocess(text, rules=["pronounce"]) == text

    def test_empty_file_is_noop(self):
        self._write("")
        text = "anything goes here"
        assert preprocess(text, rules=["pronounce"]) == text

    def test_engine_profile_includes_pronounce(self):
        # Every engine profile lists `pronounce`.
        for engine, rules in ENGINE_PROFILES.items():
            assert "pronounce" in rules, f"{engine} missing pronounce rule"

    # ── Bug 2: hyphenated keys must not bleed into longer compounds ─────
    # `\b` treats `-` as a non-word char, so a key like "marmalade-tts"
    # would also match inside "marmalade-tts-cli" — turning the compound
    # into "marmalade T T S-cli". The boundary is now widened to
    # `(?<![\w-])...(?![\w-])`, so a hyphenated key matches only when it
    # stands alone as a whole token.

    def test_hyphenated_key_alone_still_matches(self):
        self._write("marmalade-tts: marmalade T T S\n")
        result = preprocess("marmalade-tts is great", rules=["pronounce"])
        assert "marmalade T T S" in result
        assert "marmalade-tts" not in result

    def test_hyphenated_key_inside_compound_not_matched(self):
        # `marmalade-tts-cli` is a different token; the shorter key must
        # NOT eat the prefix and leave a dangling "-cli".
        self._write("marmalade-tts: marmalade T T S\n")
        result = preprocess("the marmalade-tts-cli tool", rules=["pronounce"])
        assert result == "the marmalade-tts-cli tool"
        assert "marmalade T T S" not in result

    def test_unhyphenated_key_inside_hyphen_compound_not_matched(self):
        # Same principle, key with no hyphen: `kubectl` should not match
        # inside `kubectl-prod`. Users wanting that substitution must add
        # the compound as its own key.
        self._write("kubectl: kube-cuttle\n")
        result = preprocess("run kubectl-prod now", rules=["pronounce"])
        assert result == "run kubectl-prod now"
        assert "kube-cuttle" not in result

    def test_unhyphenated_key_alone_still_matches(self):
        self._write("kubectl: kube-cuttle\n")
        result = preprocess("run kubectl now", rules=["pronounce"])
        assert "kube-cuttle" in result

    def test_unhyphenated_key_followed_by_punctuation_matches(self):
        # Punctuation other than `-` or word chars is a clean boundary.
        self._write("kubectl: kube-cuttle\n")
        result = preprocess("use kubectl, please.", rules=["pronounce"])
        assert "kube-cuttle" in result

    # ── Bug 3: empty / non-string YAML keys must not garble output ──────
    # An empty-string key produces an alternation branch matching every
    # zero-width position in the input, replacing it with the value and
    # silently scrambling every utterance until the user notices. PyYAML
    # can also emit non-string keys (ints, bools); those would get
    # coerced to literal strings like "42" or "True" and substitute on
    # any digit/word match — also unintended. Both are now filtered out.

    def test_empty_string_key_ignored(self):
        # The empty-string key must be dropped; the real key still works.
        self._write('"": bogus\nkubectl: kube-cuttle\n')
        result = preprocess("run kubectl now", rules=["pronounce"])
        assert result == "run kube-cuttle now"
        # And on input with no real-key match, the empty key must not
        # have garbled anything.
        plain = preprocess("plain text here", rules=["pronounce"])
        assert plain == "plain text here"
        assert "bogus" not in plain

    def test_empty_string_key_alone_is_noop(self):
        # If the empty-string key is the ONLY entry, the loader must end
        # up with no compiled regex at all — text passes through verbatim.
        self._write('"": bogus\n')
        text = "anything could be here"
        assert preprocess(text, rules=["pronounce"]) == text

    def test_non_string_key_ignored(self):
        # PyYAML happily parses `42: number` as `{42: "number"}`. The
        # integer key must be dropped (str(42) would otherwise turn every
        # "42" in the input into "number"). Real string keys still work.
        self._write("42: number\nkubectl: kube-cuttle\n")
        result_nums = preprocess("we have 42 things", rules=["pronounce"])
        assert "42" in result_nums
        assert "number" not in result_nums
        result_kube = preprocess("run kubectl now", rules=["pronounce"])
        assert "kube-cuttle" in result_kube

    def test_null_key_ignored(self):
        # `~: foo` in YAML parses to `{None: "foo"}`. Defensive filter
        # drops it — without crashing the loader.
        self._write("~: foo\nkubectl: kube-cuttle\n")
        result = preprocess("run kubectl now", rules=["pronounce"])
        assert "kube-cuttle" in result
        assert "foo" not in result


# ── Engine profiles ──────────────────────────────────────────────────────────

class TestEngineProfiles:
    def test_all_engines_have_profiles(self):
        for engine in ["kitten", "kokoro", "piper", "coqui", "pocket",
                       "matcha", "emojivoice"]:
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
                     "math", "ampersand", "hashtag", "emoji"]:
            assert rule in pocket_rules, f"Pocket profile missing rule: {rule}"

    def test_pocket_profile_applies_number_rule(self):
        # Pocket should expand numbers (it handles nothing natively)
        result = preprocess("42", engine="pocket")
        assert "forty-two" in result

    def test_pocket_profile_applies_currency_rule(self):
        result = preprocess("$5", engine="pocket")
        assert "dollars" in result

    def test_matcha_profile_has_all_rules(self):
        matcha_rules = ENGINE_PROFILES["matcha"]
        for rule in ["currency", "percentage", "ordinal", "time", "date",
                     "email", "url", "filename", "abbreviation", "number",
                     "math", "ampersand", "hashtag", "emoji"]:
            assert rule in matcha_rules, f"Matcha profile missing rule: {rule}"

    def test_emojivoice_profile_has_all_non_emoji_rules(self):
        ev_rules = ENGINE_PROFILES["emojivoice"]
        for rule in ["currency", "percentage", "ordinal", "time", "date",
                     "email", "url", "filename", "abbreviation", "number",
                     "math", "ampersand", "hashtag"]:
            assert rule in ev_rules, f"EmojiVoice profile missing rule: {rule}"

    def test_emoji_rule_in_every_engine_profile_except_emojivoice(self):
        # Default-on emoji stripping for every espeak/phonemizer-backed engine,
        # off for emojivoice (which consumes the emoji to set the emotion).
        for engine, rules in ENGINE_PROFILES.items():
            if engine == "emojivoice":
                assert "emoji" not in rules, "emojivoice must NOT strip its own emoji"
            else:
                assert "emoji" in rules, f"{engine} profile missing the emoji rule"

    def test_kokoro_strips_emoji_by_default(self):
        # Regression: without the emoji rule, espeak verbalizes 😭 as
        # "loudly crying face" — the bug that motivated adding this rule.
        result = preprocess("hello 😭 world", engine="kokoro")
        assert "😭" not in result
        assert "hello world" in result

    def test_emojivoice_preprocessing_preserves_emoji(self):
        # The emotion emoji must survive preprocessing so the engine can use it.
        result = preprocess("It costs $5 🤣", engine="emojivoice")
        assert "🤣" in result
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
