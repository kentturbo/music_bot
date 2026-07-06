"""Mozilla Fluent-based translator.

Loads every locales/{lang}.ftl at startup into a FluentLocalization bundle.
`Translator` is a thin per-request wrapper bound to one language with a
graceful fallback chain: requested lang -> default -> raw key.
"""
from __future__ import annotations

from pathlib import Path

from fluent.runtime import FluentLocalization, FluentResourceLoader

from bot.config import SUPPORTED_LANGUAGES, settings

_LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"


class I18n:
    def __init__(self) -> None:
        loader = FluentResourceLoader(str(_LOCALES_DIR / "{locale}"))
        self._bundles: dict[str, FluentLocalization] = {}
        for lang in SUPPORTED_LANGUAGES:
            # Each language falls back to the default language, then English.
            fallbacks = [lang, settings.default_language, "en"]
            seen: list[str] = []
            for f in fallbacks:
                if f not in seen:
                    seen.append(f)
            self._bundles[lang] = FluentLocalization(seen, ["main.ftl"], loader)

    def normalize(self, lang: str | None) -> str:
        """Map a Telegram language_code (e.g. 'ru-RU') to a supported code."""
        if not lang:
            return settings.default_language
        base = lang.lower().split("-")[0]
        return base if base in SUPPORTED_LANGUAGES else settings.default_language

    def get(self, lang: str) -> "Translator":
        lang = self.normalize(lang)
        return Translator(self._bundles[lang], lang)


class Translator:
    def __init__(self, bundle: FluentLocalization, lang: str) -> None:
        self._bundle = bundle
        self.lang = lang

    def __call__(self, key: str, /, **kwargs: object) -> str:
        """Translate a message id, interpolating Fluent variables.

        Returns the key itself if the message is missing so the UI degrades
        loudly-but-safely instead of raising.
        """
        value = self._bundle.format_value(key, kwargs or None)
        return value if value != key else key


i18n = I18n()
