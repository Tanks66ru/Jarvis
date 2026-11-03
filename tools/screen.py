"""Скриншоты и OCR."""

import os
import shutil
import tempfile

import numpy as np
import pyautogui
import pytesseract
from pytesseract import Output

from config import (
    SCREENSHOT_MAX_WIDTH,
    TESSERACT_LANG,
    TESSERACT_CMD,
    SCREEN_CHANGE_THRESHOLD,
)


_screenshot_files: list[str] = []
_latest_screenshot_path: str | None = None

# Фактический размер сохранённого изображения,
# которое передаётся vision-модели.
_latest_screenshot_size: tuple[int, int] | None = None

_last_signature: np.ndarray | None = None
_last_changed: bool | None = None


# --- Tesseract ----------------------------------------------


TESSERACT_INSTALL_HINT = (
    "Установи Tesseract (Windows-сборка UB Mannheim: "
    "https://github.com/UB-Mannheim/tesseract/wiki), при установке "
    "отметь язык Russian. Затем перезапусти терминал или укажи путь "
    "к tesseract.exe в config.py (TESSERACT_CMD)."
)


def _find_tesseract() -> str | None:
    candidates = [
        TESSERACT_CMD or None,
        os.environ.get("TESSERACT_PATH"),
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(
            r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"
        ),
        os.path.expandvars(
            r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"
        ),
    ]

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    return None


TESSERACT_PATH = _find_tesseract()
OCR_AVAILABLE = TESSERACT_PATH is not None

_available_languages: list[str] = []


if OCR_AVAILABLE:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

    print(
        f"Tesseract найден: {TESSERACT_PATH}"
    )

    try:
        _available_languages = (
            pytesseract.get_languages(config="")
        )

        print(
            "Языки Tesseract: "
            f"{', '.join(_available_languages)}"
        )

        if "rus" not in _available_languages:
            print(
                "Предупреждение: нет языка 'rus' — "
                "русский текст не распознается. "
                "Переустанови Tesseract с языком Russian "
                "или добавь rus.traineddata в tessdata."
            )

    except Exception as e:
        print(
            "Предупреждение: не удалось получить список "
            f"языков Tesseract: {e}"
        )

else:
    print(
        "Предупреждение: Tesseract не найден. "
        "OCR недоступен."
    )
    print(TESSERACT_INSTALL_HINT)


def _filter_languages(
    language: str,
) -> str | None:
    """Оставляет только установленные языки."""
    if not _available_languages:
        return language

    wanted = [
        lang
        for lang in language.split("+")
        if lang
    ]

    usable = [
        lang
        for lang in wanted
        if lang in _available_languages
    ]

    return (
        "+".join(usable)
        if usable
        else None
    )


# --- Файлы скриншотов ---------------------------------------


def get_latest_screenshot() -> str | None:
    """Вернуть путь к последнему сохранённому скриншоту."""
    return _latest_screenshot_path


def get_latest_screenshot_size() -> tuple[int, int] | None:
    """
    Вернуть фактический размер последнего сохранённого
    изображения, которое получает vision-модель.

    Например:
        (1280, 720)
    """
    return _latest_screenshot_size


def screen_changed() -> bool | None:
    """
    Изменился ли экран по сравнению с предыдущим скриншотом.

    None — сравнивать пока не с чем.
    """
    return _last_changed


def cleanup_screenshots() -> None:
    """Удалить временные файлы старых скриншотов."""
    for path in _screenshot_files:
        try:
            os.remove(path)
        except OSError:
            pass

    _screenshot_files.clear()


def _save_screenshot(image) -> str:
    """
    Сохраняет скриншот и сравнивает его с предыдущим.

    При необходимости изображение уменьшается до
    SCREENSHOT_MAX_WIDTH с сохранением пропорций.

    _latest_screenshot_size всегда содержит размер
    именно сохранённого PNG-файла, который передаётся
    vision-модели.
    """
    global _latest_screenshot_path
    global _latest_screenshot_size
    global _last_signature
    global _last_changed

    cleanup_screenshots()

    # Сигнатура считается по исходному изображению.
    # Это позволяет сравнивать изменения независимо
    # от последующего уменьшения изображения.
    signature = np.asarray(
        image.convert("L").resize((64, 36)),
        dtype=np.float32,
    )

    if _last_signature is None:
        _last_changed = None
    else:
        diff = float(
            np.mean(
                np.abs(
                    signature - _last_signature
                )
            )
        )

        _last_changed = (
            diff >= SCREEN_CHANGE_THRESHOLD
        )

    _last_signature = signature

    # Готовим именно то изображение,
    # которое будет отправлено модели.
    small = image

    if small.width > SCREENSHOT_MAX_WIDTH:
        ratio = (
            SCREENSHOT_MAX_WIDTH
            / small.width
        )

        new_width = SCREENSHOT_MAX_WIDTH
        new_height = round(
            small.height * ratio
        )

        small = small.resize(
            (new_width, new_height)
        )

    small = small.convert("RGB")

    # Очень важно:
    # сохраняем фактический размер PNG.
    _latest_screenshot_size = (
        small.width,
        small.height,
    )

    fd, path = tempfile.mkstemp(
        suffix=".png"
    )
    os.close(fd)

    small.save(path)

    _screenshot_files.append(path)
    _latest_screenshot_path = path

    print(
        "[Screen] "
        f"original={image.width}x{image.height}, "
        f"saved={small.width}x{small.height}"
    )

    return path


# --- Tools --------------------------------------------------


def screenshot() -> str:
    """
    Сделать скриншот всего экрана и показать его модели.

    Returns:
        Путь к файлу скриншота.
    """
    path = _save_screenshot(
        pyautogui.screenshot()
    )

    print(
        f"[Tool] screenshot -> {path}"
    )

    return path


def ocr_screen(
    language: str = TESSERACT_LANG,
) -> str:
    """
    Распознать текст на экране.

    Для каждого найденного текста возвращает:
        point=[x, y]

    Координаты нормализованы в диапазон 0-1000
    относительно исходного скриншота.

    Args:
        language:
            Языки Tesseract, например "rus+eng".
    """
    if not OCR_AVAILABLE:
        return (
            "Ошибка: Tesseract OCR не установлен. "
            "Используй screenshot()."
        )

    language = _filter_languages(
        language
    )

    if language is None:
        return (
            "Ошибка: нужные языки Tesseract "
            "не установлены."
        )

    try:
        image = pyautogui.screenshot()

        image_path = _save_screenshot(
            image
        )

        data = pytesseract.image_to_data(
            image,
            lang=language,
            output_type=Output.DICT,
            config="--psm 6",
        )

        results = []

        for i in range(len(data["text"])):
            text = data["text"][i].strip()

            if not text:
                continue

            try:
                confidence = float(
                    data["conf"][i]
                )
            except (
                TypeError,
                ValueError,
            ):
                confidence = -1

            if confidence < 25:
                continue

            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])

            # Центр найденного текста.
            center_x = x + w / 2
            center_y = y + h / 2

            # Координаты OCR в диапазоне 0-1000.
            point_x = round(
                center_x
                / image.width
                * 1000
            )

            point_y = round(
                center_y
                / image.height
                * 1000
            )

            results.append(
                f"{text} "
                f"[point=[{point_x}, {point_y}], "
                f"conf={confidence:.0f}]"
            )

        if not results:
            return (
                "OCR не нашёл читаемого текста."
            )

        output = "\n".join(results)

        if len(output) > 6000:
            output = (
                output[:6000]
                + "\n[OCR output truncated]"
            )

        return (
            "Результат OCR:\n"
            f"{output}\n"
            f"Скриншот: {image_path}"
        )

    except Exception as e:
        return f"Ошибка OCR: {e}"
