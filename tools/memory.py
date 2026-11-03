"""Долговременная память в .md файлах."""
import re
from datetime import datetime
from pathlib import Path

from config import MEMORY_DIR


def _sanitize_filename(title: str) -> str:
    title = re.sub(r'[<>:"/\\|?*]', "_", title.strip())
    title = re.sub(r"\s+", "_", title).strip("._ ")
    return (title or "memory")[:80]


def save_memory(title: str, content: str) -> str:
    """Сохранить важную информацию в долговременную память.

    Args:
        title: Короткий заголовок записи.
        content: Что нужно запомнить.
    """
    title = title.strip() or "Без названия"
    content = content.strip() or "Пустая запись."

    now = datetime.now()
    filename = f"{now:%Y-%m-%d_%H-%M-%S}_{_sanitize_filename(title)}.md"
    text = (
        f"# {title}\n\n"
        f"Дата: {now:%Y-%m-%d}\n"
        f"Время: {now:%H:%M:%S}\n\n"
        f"{content}\n"
    )
    (MEMORY_DIR / filename).write_text(text, encoding="utf-8")
    return f"Память сохранена: {filename}"


def list_memories(limit: int = 30) -> str:
    """Показать последние записи долговременной памяти.

    Args:
        limit: Сколько файлов показать (1-100).
    """
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 30

    files = sorted(MEMORY_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return "Долговременная память пустая."
    return "Файлы памяти:\n" + "\n".join(p.name for p in files[:limit])


def read_memory(filename: str) -> str:
    """Прочитать запись памяти.

    Args:
        filename: Имя файла из list_memories().
    """
    safe_name = Path(filename).name
    path = MEMORY_DIR / safe_name
    if not path.exists():
        return f"Память не найдена: {safe_name}"

    try:
        content = path.read_text(encoding="utf-8")
        if len(content) > 8000:
            content = content[:8000] + "\n[Memory truncated]"
        return content
    except Exception as e:
        return f"Ошибка чтения памяти: {e}"


def search_memory(query: str, limit: int = 5) -> str:
    """Искать в долговременной памяти по словам.

    Args:
        query: Поисковый запрос.
        limit: Максимум результатов (1-10).
    """
    query = query.strip().lower()
    if not query:
        return "Ошибка: поисковый запрос пуст."

    terms = [t for t in re.findall(r"[а-яёa-z0-9_]+", query) if len(t) > 2] or [query]

    matches = []
    for path in MEMORY_DIR.glob("*.md"):
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        lower = content.lower()
        score = sum(lower.count(t) for t in terms)
        if score > 0:
            matches.append((score, path.stat().st_mtime, path, content))

    try:
        limit = max(1, min(int(limit), 10))
    except (TypeError, ValueError):
        limit = 5

    if not matches:
        return "В памяти ничего не найдено."

    matches.sort(key=lambda m: (m[0], m[1]), reverse=True)
    return "\n\n".join(
        f"--- {path.name} ---\n{content[:1800]}"
        for _, _, path, content in matches[:limit]
    )
