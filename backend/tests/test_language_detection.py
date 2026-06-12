"""Tests for the language detection cascade in language_service.py.

Covers two bug fixes:
  Bug 1: Keyword tie should return None so Gemini can disambiguate.
  Bug 2: Explicit mentions (e.g. 'RECAP IN HINDI', '[PT]') are detected as a
         new cascade layer between suffix and keyword.
"""
import pytest

from backend.services.language_service import LanguageService


@pytest.fixture
def service():
    return LanguageService()


def _no_gemini(self, text):
    """Default fake Gemini: never called means it returns None to surface bugs early."""
    raise AssertionError(
        f"_detect_by_gemini should NOT have been called for text: {text!r}"
    )


def _fake_gemini_es(self, text):
    return "es"


# ---------------------------------------------------------------------------
# Bug 1: Keyword tie -> None -> Gemini wins
# ---------------------------------------------------------------------------
class TestKeywordTie:
    def test_traicionaron_falls_through_to_gemini(self, service, monkeypatch):
        """The PT/ES tie on 'como'+'todos' must NOT pick PT arbitrarily.
        Gemini (mocked to 'es') should be reached."""
        monkeypatch.setattr(LanguageService, "_detect_by_gemini", _fake_gemini_es)
        title = (
            "Traicionaron a Este FRACASADO y lo Dejaron Morir, "
            "Volvió Como el Ser Más FUERTE de Todos"
        )
        code, method = service.detect_language(title)
        assert (code, method) == ("es", "gemini")

    def test_explicit_tie_minimal(self, service, monkeypatch):
        """Minimal tied input: 'como todos' scores 2 in both PT and ES."""
        monkeypatch.setattr(LanguageService, "_detect_by_gemini", _fake_gemini_es)
        code, method = service.detect_language("como todos")
        assert (code, method) == ("es", "gemini")

    def test_tie_returns_none_from_keyword_layer(self, service):
        """Direct check on the keyword layer: tie -> None."""
        assert service._detect_by_keywords("como todos") is None


# ---------------------------------------------------------------------------
# Bug 2: Explicit mention layer
# ---------------------------------------------------------------------------
class TestExplicitMention:
    def test_recap_in_hindi(self, service, monkeypatch):
        """English content with 'RECAP IN HINDI' suffix => hi via mention.
        Gemini must NOT be called."""
        monkeypatch.setattr(LanguageService, "_detect_by_gemini", _no_gemini)
        title = (
            "They Betrayed This FAILURE, Left Him to Die He Returned as the "
            "STRONGEST RECAP IN HINDI"
        )
        code, method = service.detect_language(title)
        assert (code, method) == ("hi", "mention")

    def test_paren_pt_prefix(self, service, monkeypatch):
        monkeypatch.setattr(LanguageService, "_detect_by_gemini", _no_gemini)
        code, method = service.detect_language("(PT) Aula nova")
        assert (code, method) == ("pt", "mention")

    def test_bracket_hindi(self, service, monkeypatch):
        monkeypatch.setattr(LanguageService, "_detect_by_gemini", _no_gemini)
        code, method = service.detect_language("[HINDI] Some title")
        assert (code, method) == ("hi", "mention")

    def test_trailing_separator_es(self, service, monkeypatch):
        monkeypatch.setattr(LanguageService, "_detect_by_gemini", _no_gemini)
        code, method = service.detect_language("Some title · ES")
        assert (code, method) == ("es", "mention")

    def test_multiple_mentions_last_wins(self, service, monkeypatch):
        """When several mentions exist, the LAST one wins (content indicator)."""
        monkeypatch.setattr(LanguageService, "_detect_by_gemini", _no_gemini)
        code, method = service.detect_language("EN Recap IN HINDI")
        assert (code, method) == ("hi", "mention")


# ---------------------------------------------------------------------------
# Layer-ordering: existing layers still win where they should
# ---------------------------------------------------------------------------
class TestLayerOrdering:
    def test_suffix_still_wins_over_mention(self, service, monkeypatch):
        monkeypatch.setattr(LanguageService, "_detect_by_gemini", _no_gemini)
        code, method = service.detect_language("aula_05_pt.mp4")
        assert (code, method) == ("pt", "suffix")

    def test_unambiguous_keyword_still_works(self, service, monkeypatch):
        """Unambiguous PT text reaches keyword layer (no mention, no suffix)."""
        monkeypatch.setattr(LanguageService, "_detect_by_gemini", _no_gemini)
        code, method = service.detect_language("Aula de português brasil")
        assert (code, method) == ("pt", "keyword")
