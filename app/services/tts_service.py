import httpx
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# List of supported languages in the TTS engine
SUPPORTED_LANGS = {
    "as", "bn", "brx", "doi", "gu", "hi", "kn", "kok", "ks", "mai", "ml", "mni",
    "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur", "ar", "de",
    "en", "es", "fr", "it", "ja", "ko", "nl", "pl", "pt", "ru", "tr", "zh"
}

async def synthesize(text: str, voice: str, format: str) -> bytes:
    """Proxies the TTS generation request to the underlying TTS engine."""
    # Try to extract language from voice name, e.g. "en-US-female-1" -> "en"
    lang = "en"
    if voice:
        parts = voice.replace("_", "-").split("-")
        if parts:
            possible_lang = parts[0].lower()
            if possible_lang in SUPPORTED_LANGS:
                lang = possible_lang

    # Translate the opaque voice ID to a natural-language description that
    # Parler-TTS (Indic-Parler-TTS) can actually condition on.  Without this,
    # the model receives a meaningless string like "hi-female-1" as its voice
    # prompt, which produces an incoherent speaker embedding and causes the
    # tone/voice to shift between sentences.
    parler_voice = _resolve_parler_voice(voice, lang)

    logger.info(f"Proxying TTS request to engine: language={lang}, voice={voice}, parler_voice={parler_voice!r:.80}")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.tts_engine_url.rstrip('/')}{settings.tts_engine_path}",
            json={
                "text": text,
                "language": lang,
                "voice": parler_voice,
            },
            timeout=settings.engine_timeout_seconds,
        )
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# Voice-ID -> Parler natural-language description map
# ---------------------------------------------------------------------------
# Parler-TTS conditions its codec decoder on a *text description* of the
# desired speaker, not on a voice-preset ID.  Passing an opaque ID such as
# "hi-female-1" produces an incoherent conditioning embedding and makes the
# voice shift between chunks of the same utterance.
#
# Keys follow the pattern "<lang>-<gender>-<index>" used by this gateway.
# Add entries as needed; unknown IDs fall back to language-appropriate defaults.
# ---------------------------------------------------------------------------

_FEMALE_CLEAR = (
    "A female speaker delivers a slightly expressive and animated speech "
    "with a moderate speed and pitch. The recording is of very high quality, "
    "with the speaker's voice sounding clear and very close up."
)
_MALE_CLEAR = (
    "A male speaker delivers a clear and neutral speech with a moderate speed "
    "and pitch. The recording is of very high quality, with the speaker's voice "
    "sounding clear and very close up."
)
_FEMALE_SLOW = (
    "A female speaker delivers calm, slow, and clearly articulated speech. "
    "The recording is of very high quality, with the speaker's voice sounding "
    "clear and very close up."
)
_MALE_SLOW = (
    "A male speaker delivers calm, slow, and clearly articulated speech. "
    "The recording is of very high quality, with the speaker's voice sounding "
    "clear and very close up."
)

VOICE_DESCRIPTIONS: dict[str, str] = {
    # Hindi
    "hi-female-1": _FEMALE_CLEAR,
    "hi-female-2": _FEMALE_SLOW,
    "hi-male-1":   _MALE_CLEAR,
    "hi-male-2":   _MALE_SLOW,
    # Bengali
    "bn-female-1": _FEMALE_CLEAR,
    "bn-male-1":   _MALE_CLEAR,
    # Tamil
    "ta-female-1": _FEMALE_CLEAR,
    "ta-male-1":   _MALE_CLEAR,
    # Telugu
    "te-female-1": _FEMALE_CLEAR,
    "te-male-1":   _MALE_CLEAR,
    # Kannada
    "kn-female-1": _FEMALE_CLEAR,
    "kn-male-1":   _MALE_CLEAR,
    # Malayalam
    "ml-female-1": _FEMALE_CLEAR,
    "ml-male-1":   _MALE_CLEAR,
    # Gujarati
    "gu-female-1": _FEMALE_CLEAR,
    "gu-male-1":   _MALE_CLEAR,
    # Marathi
    "mr-female-1": _FEMALE_CLEAR,
    "mr-male-1":   _MALE_CLEAR,
    # Punjabi
    "pa-female-1": _FEMALE_CLEAR,
    "pa-male-1":   _MALE_CLEAR,
    # Urdu
    "ur-female-1": _FEMALE_CLEAR,
    "ur-male-1":   _MALE_CLEAR,
    # English (Bark handles these, but included for completeness)
    "en-female-1": _FEMALE_CLEAR,
    "en-male-1":   _MALE_CLEAR,
}

# Default descriptions by gender when no exact voice ID match exists
_DEFAULT_BY_GENDER: dict[str, str] = {
    "female": _FEMALE_CLEAR,
    "male":   _MALE_CLEAR,
}


def _resolve_parler_voice(voice: str | None, lang: str) -> str:
    """Translate a gateway voice ID to a Parler-TTS natural-language description.

    Resolution order:
    1. Exact match in VOICE_DESCRIPTIONS.
    2. Gender extracted from the voice string (contains 'female' or 'male').
    3. Language-appropriate default (female clear voice).
    """
    if not voice:
        return _FEMALE_CLEAR

    # Normalise: lowercase, replace underscores
    key = voice.strip().lower().replace("_", "-")

    # 1. Exact match
    if key in VOICE_DESCRIPTIONS:
        return VOICE_DESCRIPTIONS[key]

    # 2. Gender-based fallback
    if "female" in key:
        return _DEFAULT_BY_GENDER["female"]
    if "male" in key:
        return _DEFAULT_BY_GENDER["male"]

    # 3. Final fallback - return the voice string as-is only when it looks like
    #    a real Parler description (i.e. it's a long sentence, not an ID).
    if len(voice) > 40:
        return voice

    return _FEMALE_CLEAR
