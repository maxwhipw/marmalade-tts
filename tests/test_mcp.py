"""Tests for the MCP server's pure helpers.

We don't try to start the stdio MCP server in tests — that requires the
`mcp` SDK and a peer process. Instead we unit-test the pure functions that
do the actual work: ``list_voices_data`` and ``find_voice_matches``. These
import without the mcp SDK installed.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from marmalade_tts.mcp_server import (
    VOICE_DESCRIPTIONS,
    find_voice_matches,
    list_voices_data,
)


# ── list_voices_data ────────────────────────────────────────────────────────

class TestListVoicesData:
    def test_returns_all_voices_when_no_engine(self):
        voices = list_voices_data()
        assert len(voices) == len(VOICE_DESCRIPTIONS)
        assert all(isinstance(v, dict) for v in voices)

    def test_voice_shape(self):
        voices = list_voices_data()
        v = voices[0]
        assert set(v.keys()) == {"name", "engine", "language", "description"}
        assert all(isinstance(v[k], str) for k in v)

    def test_filter_to_kokoro(self):
        voices = list_voices_data("kokoro")
        assert voices  # non-empty
        assert all(v["engine"] == "kokoro" for v in voices)
        names = {v["name"] for v in voices}
        # Spot-check a few canonical kokoro voices.
        assert {"heart", "george", "alpha", "xiaobei"}.issubset(names)

    def test_filter_to_kitten(self):
        voices = list_voices_data("kitten")
        assert voices
        assert all(v["engine"] == "kitten" for v in voices)
        names = {v["name"] for v in voices}
        # Kitten ships these eight; if upstream adds more, update VOICE_DESCRIPTIONS.
        assert {"Bella", "Jasper", "Luna", "Bruno",
                "Rosie", "Hugo", "Kiki", "Leo"}.issubset(names)

    def test_filter_to_pocket(self):
        voices = list_voices_data("pocket")
        names = {v["name"] for v in voices}
        assert {"alba", "marius", "javert", "jean",
                "fantine", "cosette", "eponine", "azelma"}.issubset(names)

    def test_filter_to_emojivoice(self):
        voices = list_voices_data("emojivoice")
        names = {v["name"] for v in voices}
        assert names == {"paige"}

    def test_piper_and_coqui_omitted(self):
        # Voices are user-installed model paths, not bare names — exposing
        # them via MCP doesn't make sense.
        assert list_voices_data("piper") == []
        assert list_voices_data("coqui") == []
        assert list_voices_data("matcha") == []

    def test_unknown_engine_filter_is_empty(self):
        assert list_voices_data("not-a-real-engine") == []


# ── find_voice_matches ──────────────────────────────────────────────────────

class TestFindVoiceMatches:
    def test_warm_british_male_finds_george(self):
        matches = find_voice_matches("warm British male")
        assert matches  # non-empty
        top_names = [(m["engine"], m["name"]) for m in matches]
        assert ("kokoro", "george") in top_names
        # george matches all three terms; should be the top hit.
        assert matches[0]["engine"] == "kokoro"
        assert matches[0]["name"] == "george"

    def test_japanese_female_finds_alpha_or_gongitsune(self):
        matches = find_voice_matches("Japanese female")
        assert matches
        top = matches[0]
        assert top["engine"] == "kokoro"
        assert top["name"] in {"alpha", "gongitsune"}

    def test_expressive_emoji_finds_paige(self):
        matches = find_voice_matches("expressive emoji")
        assert matches
        assert matches[0]["engine"] == "emojivoice"
        assert matches[0]["name"] == "paige"

    def test_returns_at_most_three(self):
        # Even with a very generic query, we cap at top 3.
        matches = find_voice_matches("female")
        assert len(matches) <= 3

    def test_why_field_lists_matched_terms(self):
        matches = find_voice_matches("warm British male")
        assert matches
        why = matches[0]["why"]
        assert why.startswith("matched:")
        # All three should match for george.
        for term in ("warm", "british", "male"):
            assert term in why

    def test_score_is_descending(self):
        matches = find_voice_matches("warm British male narrator")
        scores = [m["score"] for m in matches]
        assert scores == sorted(scores, reverse=True)

    def test_synonym_man_resolves_to_male(self):
        # "British man" should still find george (man → male synonym).
        matches = find_voice_matches("British man")
        top_names = [(m["engine"], m["name"]) for m in matches]
        assert any(eng == "kokoro" and name in {"george", "lewis"}
                   for eng, name in top_names)

    # ── word-token regression guards ────────────────────────────────────────
    # Substring scoring used to make "male" match inside "female", which
    # ranked female voices (Bella, paige) at the top of male-only queries.
    # Tokenizing both sides on word characters drops that false positive.

    def test_soothing_male_top_is_actually_male(self):
        # Known male voices across the shipped engines. "soothing" isn't in
        # any description, so only "male" should match — and it must NOT
        # match inside "female".
        male_voices = {
            "george", "adam", "michael", "lewis", "kumo", "yunjian",
            "marius", "javert", "jean",
            "Jasper", "Bruno", "Hugo", "Leo",
        }
        matches = find_voice_matches("soothing male")
        assert matches
        top = matches[0]
        assert top["name"] in male_voices, (
            f"top result {top['engine']}/{top['name']} is not a male voice"
        )
        # And explicitly: Bella (kitten female) must not appear anywhere —
        # she was the headline false positive under the old substring rule.
        names = {m["name"] for m in matches}
        assert "Bella" not in names
        assert "paige" not in names

    def test_mandarin_man_prefers_male_over_female(self):
        # Under substring scoring xiaobei (female) and yunjian (male) tied
        # at 2 for "mandarin man" → "mandarin" + "male"-in-"female".
        # Tokenization makes yunjian win outright; xiaobei drops to "mandarin"
        # only, or off the list entirely.
        matches = find_voice_matches("mandarin man")
        assert matches
        top = matches[0]
        assert (top["engine"], top["name"]) == ("kokoro", "yunjian")
        # And the score gap must exist (no tie at the top).
        if len(matches) > 1:
            assert matches[0]["score"] > matches[1]["score"]

    def test_voice_name_in_haystack_matches(self):
        # The haystack includes the voice name token, so a bare name query
        # finds the voice. (Regression guard for the tokenizer covering
        # name as well as description.)
        matches = find_voice_matches("kiki")
        assert matches
        assert (matches[0]["engine"], matches[0]["name"]) == ("kitten", "Kiki")

    def test_empty_description_returns_nothing(self):
        assert find_voice_matches("") == []
        assert find_voice_matches("   ") == []

    def test_only_stopwords_returns_nothing(self):
        # Pure stopwords / fluff with no scorable terms.
        assert find_voice_matches("a voice please") == []

    def test_no_matches_returns_empty(self):
        # A term that genuinely doesn't appear anywhere in the table.
        assert find_voice_matches("klingon") == []

    def test_match_shape(self):
        matches = find_voice_matches("warm British male")
        m = matches[0]
        assert set(m.keys()) == {"name", "engine", "score", "why"}
        assert isinstance(m["name"], str)
        assert isinstance(m["engine"], str)
        assert isinstance(m["score"], float)
        assert isinstance(m["why"], str)
