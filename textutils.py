import re

from config import GOODBYE_PHRASES, CONFIRMATIONS, DENIALS


def normalize_text(text: str) -> str:
    """Нижний регистр, ё->е, без знаков препинания, одинарные пробелы.
    Whisper возвращает «Да.» / «Пока!», поэтому без этого сравнения не работают."""
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_phrase(normalized_text: str, phrase: str) -> bool:
    # Совпадение по целым словам: "пока" НЕ должно срабатывать на "покажи".
    return f" {phrase} " in f" {normalized_text} "


def is_goodbye(text: str) -> bool:
    normalized = normalize_text(text)
    # Только короткие реплики, чтобы "пока я работаю, открой..." не выключало режим.
    if not normalized or len(normalized.split()) > 3:
        return False
    return any(_contains_phrase(normalized, p) for p in GOODBYE_PHRASES)


def is_confirmation(text: str) -> bool:
    words = normalize_text(text).split()
    return bool(words) and all(w in CONFIRMATIONS for w in words)


def is_denial(text: str) -> bool:
    normalized = normalize_text(text)
    return normalized in DENIALS or (
        bool(normalized) and normalized.split()[0] in DENIALS
    )
