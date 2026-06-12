import re
import unicodedata
from pathlib import Path

from backend.config import settings


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


LANGUAGE_SUFFIXES = {
    "pt", "es", "en", "fr", "it", "de", "ja", "ko", "zh",
    "ar", "hi", "ru", "tr", "nl", "pl", "sv", "th", "vi",
    "id", "cs", "ro", "hu", "el", "he", "da", "fi", "no",
}

KEYWORD_MAP: dict[str, list[str]] = {
    "pt": ["aula", "como", "aprenda", "dica", "resumo", "episodio", "tutorial", "historia",
           "receita", "viagem", "musica", "jogo", "filme", "serie", "entrevista", "noticia",
           "português", "brasil", "voce", "isso", "fazer", "pode", "muito", "todos", "essa"],
    "es": ["leccion", "como", "aprende", "consejo", "resumen", "episodio", "tutorial",
           "historia", "receta", "viaje", "musica", "juego", "pelicula", "serie",
           "entrevista", "noticia", "español", "puede", "esto", "hacer", "todos", "esta"],
    "fr": ["lecon", "comment", "apprends", "conseil", "resume", "episode", "tutoriel",
           "histoire", "recette", "voyage", "musique", "jeu", "film", "serie",
           "entretien", "actualite", "français", "faire", "cette", "sont", "avec", "dans"],
    "it": ["lezione", "come", "impara", "consiglio", "riassunto", "episodio", "tutorial",
           "storia", "ricetta", "viaggio", "musica", "gioco", "film", "serie",
           "intervista", "notizia", "italiano", "fare", "questa", "sono", "della", "nella"],
    "en": ["lesson", "how", "learn", "tip", "summary", "episode", "tutorial", "story",
           "recipe", "travel", "music", "game", "movie", "series", "interview", "news",
           "english", "the", "this", "that", "with", "from", "have", "about", "would"],
    "de": ["lektion", "wie", "lernen", "tipp", "zusammenfassung", "episode", "tutorial",
           "geschichte", "rezept", "reise", "musik", "spiel", "film", "serie",
           "interview", "nachricht", "deutsch", "diese", "sind", "werden", "haben", "nicht"],
    "hi": ["sabak", "kaise", "seekho", "sujhav", "saransh", "episode", "tutorial",
           "kahani", "recipe", "yatra", "sangeet", "khel", "film", "series",
           "hindi", "kya", "hai", "yeh", "woh", "aur", "mein", "hum"],
    "ja": ["レッスン", "方法", "学ぶ", "ヒント", "まとめ", "エピソード", "チュートリアル",
           "物語", "レシピ", "旅行", "音楽", "ゲーム", "映画", "シリーズ"],
    "ko": ["레슨", "방법", "배우다", "팁", "요약", "에피소드", "튜토리얼",
           "이야기", "레시피", "여행", "음악", "게임", "영화", "시리즈"],
    "zh": ["课程", "如何", "学习", "提示", "总结", "集", "教程",
           "故事", "食谱", "旅行", "音乐", "游戏", "电影", "系列"],
    "ar": ["درس", "كيف", "تعلم", "نصيحة", "ملخص", "حلقة", "شرح",
           "قصة", "وصفة", "سفر", "موسيقى", "لعبة", "فيلم", "مسلسل"],
    "ru": ["урок", "как", "учить", "совет", "резюме", "эпизод", "туториал",
           "история", "рецепт", "путешествие", "музыка", "игра", "фильм", "сериал"],
    "tr": ["ders", "nasıl", "öğren", "ipucu", "özet", "bölüm", "eğitim",
           "hikaye", "tarif", "seyahat", "müzik", "oyun", "film", "dizi"],
}


LANGUAGE_NAMES: dict[str, str] = {
    # English names + PT names + native names (lowercase, accents stripped via _strip_accents)
    "english": "en", "ingles": "en",
    "portuguese": "pt", "portugues": "pt",
    "spanish": "es", "espanol": "es", "espanhol": "es",
    "french": "fr", "francais": "fr", "frances": "fr",
    "italian": "it", "italiano": "it",
    "german": "de", "deutsch": "de", "alemao": "de",
    "hindi": "hi",
    "japanese": "ja", "japones": "ja",
    "korean": "ko", "coreano": "ko",
    "chinese": "zh", "mandarim": "zh", "zhongwen": "zh",
    "arabic": "ar", "arabe": "ar",
    "russian": "ru", "russo": "ru",
    "turkish": "tr", "turco": "tr",
    "dutch": "nl", "holandes": "nl",
    "polish": "pl", "polones": "pl",
    "swedish": "sv", "sueco": "sv",
    "thai": "th", "tailandes": "th",
    "vietnamese": "vi", "vietnamita": "vi",
    "indonesian": "id",
    "greek": "el", "grego": "el",
    "hebrew": "he", "hebraico": "he",
}


class LanguageService:
    def detect_language(self, text: str) -> tuple[str | None, str]:
        """
        Detect language of text using 5-layer cascade.
        Returns (language_code, detection_method).
        detection_method is one of: 'suffix', 'mention', 'keyword', 'gemini', 'unknown'
        """
        # Layer 1: Suffix detection
        result = self._detect_by_suffix(text)
        if result:
            return result, "suffix"

        # Layer 2: Explicit mention detection
        result = self._detect_by_explicit_mention(text)
        if result:
            return result, "mention"

        # Layer 3: Keyword detection (tie-aware)
        result = self._detect_by_keywords(text)
        if result:
            return result, "keyword"

        # Layer 4: Gemini API
        result = self._detect_by_gemini(text)
        if result:
            return result, "gemini"

        # Layer 5: Manual (return unknown)
        return None, "unknown"

    def detect_batch(self, texts: list[str]) -> list[tuple[str | None, str]]:
        """Detect language for multiple texts."""
        return [self.detect_language(text) for text in texts]

    def _detect_by_suffix(self, text: str) -> str | None:
        """Check if filename ends with a language code suffix like _pt, _es, etc."""
        # Remove extension if present
        name = Path(text).stem if "." in text else text
        # Check for _XX or -XX suffix
        match = re.search(r"[_\-]([a-z]{2})$", name.lower())
        if match and match.group(1) in LANGUAGE_SUFFIXES:
            return match.group(1)
        return None

    def _detect_by_keywords(self, text: str) -> str | None:
        """Check for language-specific keywords in the text."""
        # Remove extension and clean up
        name = Path(text).stem if "." in text else text
        words = set(re.findall(r"\w+", name.lower()))

        scores: dict[str, int] = {}
        for lang, keywords in KEYWORD_MAP.items():
            score = len(words.intersection(set(kw.lower() for kw in keywords)))
            if score > 0:
                scores[lang] = score

        if not scores:
            return None

        max_score = max(scores.values())
        top_langs = [lang for lang, s in scores.items() if s == max_score]

        if len(top_langs) > 1:
            # Tied — let Gemini disambiguate
            return None

        best_lang = top_langs[0]
        best_score = max_score

        if best_score >= 2:
            return best_lang
        if best_score == 1 and len(scores) == 1:
            return best_lang

        return None

    def _detect_by_explicit_mention(self, text: str) -> str | None:
        """Detect language via explicit mention in the title (e.g. 'RECAP IN HINDI', '[PT]').

        Returns the LAST matched mention's ISO code (the latest in the title is more
        likely the content indicator, e.g. 'EN Recap IN HINDI' -> 'hi').
        """
        name = Path(text).stem if "." in text else text
        normalized = _strip_accents(name).lower()

        # Build a regex alternation of all known language NAMES (longer first to avoid
        # 'german' matching before 'germanic' etc.)
        name_alt = "|".join(sorted(LANGUAGE_NAMES.keys(), key=len, reverse=True))
        code_alt = "|".join(sorted(LANGUAGE_SUFFIXES))

        patterns = [
            # 'recap in hindi', 'dub in portuguese', etc.
            rf"(?:recap|video|dub|dubbed|subbed|version|versao)\s+in\s+({name_alt})\b",
            # generic 'in hindi' at end (must be word-boundary'd)
            rf"\bin\s+({name_alt})\b",
            # '[hindi]', '(hi)', '[pt]'
            rf"[\[\(]\s*({name_alt}|{code_alt})\s*[\]\)]",
            # ' . hindi', '- pt', '| hi' at end of title
            rf"[·\-–—\|]\s*({name_alt}|{code_alt})\s*$",
        ]

        candidates: list[tuple[int, str]] = []  # (end_pos, iso_code)
        for pattern in patterns:
            for m in re.finditer(pattern, normalized):
                token = m.group(1).lower()
                if token in LANGUAGE_NAMES:
                    iso = LANGUAGE_NAMES[token]
                elif token in LANGUAGE_SUFFIXES:
                    iso = token
                else:
                    continue
                candidates.append((m.end(), iso))

        if not candidates:
            return None

        # Last in title wins
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _get_gemini_key(self) -> str:
        """Get Gemini API key from settings.json first, then .env fallback."""
        import json
        settings_file = settings.settings_file
        if settings_file.exists():
            try:
                data = json.loads(settings_file.read_text(encoding="utf-8"))
                key = data.get("gemini_api_key", "")
                if key:
                    return key
            except (json.JSONDecodeError, OSError):
                pass
        return settings.gemini_api_key

    def _detect_by_gemini(self, text: str) -> str | None:
        """Use Gemini API to detect language."""
        api_key = self._get_gemini_key()
        if not api_key:
            return None

        try:
            from google import genai

            client = genai.Client(api_key=api_key)

            # Remove file extension for cleaner detection
            clean_text = Path(text).stem if "." in text else text

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Identify the language of this text. Return ONLY the ISO 639-1 two-letter code (e.g., pt, es, fr, it, en, hi, de, ja, ko, zh, ar, ru, tr). Text: '{clean_text}'",
            )

            result = response.text.strip().lower()
            # Validate it's a 2-letter code
            if re.match(r"^[a-z]{2}$", result):
                return result
            # Try to extract a 2-letter code from the response
            match = re.search(r"\b([a-z]{2})\b", result)
            if match and match.group(1) in LANGUAGE_SUFFIXES:
                return match.group(1)
        except Exception:
            pass

        return None


language_service = LanguageService()
