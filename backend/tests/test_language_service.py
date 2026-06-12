import pytest
from backend.services.language_service import LanguageService


@pytest.fixture
def service():
    return LanguageService()


class TestSuffixDetection:
    def test_underscore_suffix(self, service):
        code, method = service.detect_language("aula_05_pt.mp4")
        assert code == "pt"
        assert method == "suffix"

    def test_dash_suffix(self, service):
        code, method = service.detect_language("video-es.mp4")
        assert code == "es"
        assert method == "suffix"

    def test_no_suffix(self, service):
        # Should fall through to keywords or later layers
        code, method = service.detect_language("random_video.mp4")
        assert method != "suffix" or code is None

    def test_various_languages(self, service):
        assert service._detect_by_suffix("lesson_en.mp4") == "en"
        assert service._detect_by_suffix("lezione_it.mp4") == "it"
        assert service._detect_by_suffix("lecon_fr.mp4") == "fr"
        assert service._detect_by_suffix("ders_tr.mp4") == "tr"


class TestKeywordDetection:
    def test_portuguese_keywords(self, service):
        code, method = service.detect_language("como fazer receita de bolo.mp4")
        assert code == "pt"
        assert method == "keyword"

    def test_spanish_keywords(self, service):
        code, method = service.detect_language("como hacer receta de pastel.mp4")
        assert code == "es"
        assert method == "keyword"

    def test_english_keywords(self, service):
        code, method = service.detect_language("how to learn this tutorial.mp4")
        assert code == "en"
        assert method == "keyword"

    def test_french_keywords(self, service):
        code, method = service.detect_language("comment faire cette recette.mp4")
        assert code == "fr"
        assert method == "keyword"

    def test_no_keywords(self, service):
        result = service._detect_by_keywords("xyz123.mp4")
        assert result is None


class TestDetectBatch:
    def test_batch(self, service):
        results = service.detect_batch(["aula_pt.mp4", "lesson_en.mp4", "xyz.mp4"])
        assert len(results) == 3
        assert results[0] == ("pt", "suffix")
        assert results[1] == ("en", "suffix")
