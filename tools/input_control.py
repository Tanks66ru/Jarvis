"""Мышь и клавиатура."""

import json
import math
import time

import pyautogui
import pyperclip

from .ui_context import (
    focus_text_input,
    get_foreground_process_name,
    SELF_PROCESS_NAMES,
)

# --- Координаты ---------------------------------------------

_COORDINATE_MAX = 1000


def _parse_point(
    point,
) -> tuple[float, float] | None:
    """
    Преобразует point в пару чисел.

    Qwen3.5 использует нормализованные координаты
    в диапазоне 0-1000.

    Поддерживает:
        [637, 284]
        (637, 284)
        "[637, 284]"
    """
    if isinstance(point, str):
        try:
            point = json.loads(point)

        except (ValueError, TypeError):
            return None

    if not isinstance(
        point,
        (list, tuple),
    ):
        return None

    if len(point) != 2:
        return None

    try:
        x = float(point[0])
        y = float(point[1])

    except (TypeError, ValueError):
        return None

    if not (
        math.isfinite(x)
        and math.isfinite(y)
    ):
        return None

    return x, y


def _validate_point(
    point,
) -> tuple[int, int] | None:
    """
    Преобразует координаты Qwen3.5 из диапазона 0-1000
    в координаты экрана pyautogui.

    Например:
        point=[592, 310]

        592 / 1000 = 59.2% ширины
        310 / 1000 = 31.0% высоты

    Для экрана 1920x1080:
        x ≈ 1137
        y ≈ 335
    """
    parsed = _parse_point(
        point
    )

    if parsed is None:
        return None

    normalized_x, normalized_y = parsed

    if not (
        0 <= normalized_x <= _COORDINATE_MAX
        and 0 <= normalized_y <= _COORDINATE_MAX
    ):
        return None

    screen_width, screen_height = (
        pyautogui.size()
    )

    if (
        screen_width <= 0
        or screen_height <= 0
    ):
        return None

    # Нормализованные координаты Qwen3.5
    # -> координаты экрана.
    x = round(
        normalized_x
        / _COORDINATE_MAX
        * (screen_width - 1)
    )

    y = round(
        normalized_y
        / _COORDINATE_MAX
        * (screen_height - 1)
    )

    # Защита от выхода за границы.
    x = max(
        0,
        min(
            x,
            screen_width - 1,
        ),
    )

    y = max(
        0,
        min(
            y,
            screen_height - 1,
        ),
    )

    print(
        "[Mouse] "
        f"normalized=({normalized_x:.1f}, "
        f"{normalized_y:.1f}) "
        f"-> "
        f"screen=({x}, {y}) "
        f"screen_size={screen_width}x{screen_height}"
    )

    return x, y


_POINT_ERROR = (
    "Ошибка: point должен быть координатами "
    "[x, y] в диапазоне 0-1000. "
    "Координаты относятся к текущему экрану."
)


# --- Мышь ---------------------------------------------------


def get_mouse_position() -> str:
    """
    Получить текущую позицию курсора.

    Возвращает как реальные координаты экрана,
    так и нормализованные координаты 0-1000.
    """
    x, y = pyautogui.position()

    screen_width, screen_height = (
        pyautogui.size()
    )

    if screen_width <= 1:
        normalized_x = 0
    else:
        normalized_x = round(
            x
            / (screen_width - 1)
            * _COORDINATE_MAX
        )

    if screen_height <= 1:
        normalized_y = 0
    else:
        normalized_y = round(
            y
            / (screen_height - 1)
            * _COORDINATE_MAX
        )

    return (
        f"Позиция мыши: "
        f"x={x}, y={y}; "
        f"normalized=[{normalized_x}, {normalized_y}]"
    )


def move_mouse(
    point: list[int],
) -> str:
    """
    Переместить курсор в точку.

    point:
        [x, y] в диапазоне 0-1000.

    Координаты нормализованы относительно
    текущего экрана.
    """
    normalized = _validate_point(
        point
    )

    if normalized is None:
        return _POINT_ERROR

    x, y = normalized

    try:
        pyautogui.moveTo(
            x,
            y,
            duration=0.15,
        )

    except Exception as e:
        return (
            f"Ошибка перемещения мыши: {e}"
        )

    return (
        f"Мышь перемещена в x={x}, y={y}"
    )


def click(
    point: list[int],
    button: str = "left",
) -> str:
    """
    Кликнуть мышью в точке.

    Args:
        point:
            [x, y] в диапазоне 0-1000.

        button:
            left, right или middle.
    """
    normalized = _validate_point(
        point
    )

    if normalized is None:
        return _POINT_ERROR

    if button not in (
        "left",
        "right",
        "middle",
    ):
        return (
            "Ошибка: неизвестная кнопка мыши."
        )

    x, y = normalized

    try:
        pyautogui.click(
            x=x,
            y=y,
            button=button,
        )

    except Exception as e:
        return (
            f"Ошибка клика мыши: {e}"
        )

    return (
        f"Клик {button} в x={x}, y={y}"
    )


def double_click(
    point: list[int],
) -> str:
    """
    Двойной клик левой кнопкой.

    point:
        [x, y] в диапазоне 0-1000.
    """
    normalized = _validate_point(
        point
    )

    if normalized is None:
        return _POINT_ERROR

    x, y = normalized

    try:
        pyautogui.doubleClick(
            x=x,
            y=y,
            interval=0.1,
        )

    except Exception as e:
        return (
            f"Ошибка двойного клика: {e}"
        )

    return (
        f"Двойной клик в x={x}, y={y}"
    )


def scroll(
    amount: int,
) -> str:
    """
    Прокрутить колесо мыши.

    Положительное число — вверх.
    Отрицательное — вниз.
    """
    try:
        amount = int(amount)

    except (TypeError, ValueError):
        return (
            "Ошибка: amount должен быть числом."
        )

    try:
        pyautogui.scroll(
            amount
        )

    except Exception as e:
        return (
            f"Ошибка прокрутки: {e}"
        )

    return (
        f"Прокрутка: {amount}"
    )


# --- Клавиатура ---------------------------------------------


def press_key(
    key: str,
) -> str:
    """
    Нажать одну клавишу.

    Например:
        enter
        esc
        tab
        win
        f5
        left
    """
    try:
        pyautogui.press(
            key
        )

        return (
            f"Нажата клавиша: {key}"
        )

    except Exception as e:
        return (
            f"Ошибка нажатия клавиши: {e}"
        )


def hotkey(
    keys: str,
) -> str:
    """
    Нажать комбинацию клавиш.

    Клавиши разделяются знаком +.

    Например:
        ctrl+c
        alt+tab
        ctrl+shift+esc
    """
    try:
        key_list = [
            key.strip()
            for key in keys.split("+")
            if key.strip()
        ]

        if not key_list:
            return (
                "Ошибка: пустая комбинация."
            )

        pyautogui.hotkey(
            *key_list
        )

        return (
            f"Нажата комбинация: {keys}"
        )

    except Exception as e:
        return (
            f"Ошибка hotkey: {e}"
        )


def type_text(
    text: str,
    target: str | None = None,
) -> str:
    """
    Ввести текст через буфер обмена. Поддерживает кириллицу.

    Если поле удалось найти через UI Automation, фокус ставится на него.
    Если UIA не видит поле (Win+R, поиск Windows, игры, Steam),
    текст вставляется в окно с текущим фокусом.
    Если в фокусе окно самого агента/IDE, ввод отменяется.
    """
    try:
        blind = False

        focus_result = focus_text_input(target=target)

        if focus_result.startswith("Ошибка"):
            # Явно указанное поле или неоднозначный выбор — не гадаем.
            if target or "несколько" in focus_result:
                return focus_result

            if get_foreground_process_name() in SELF_PROCESS_NAMES:
                return (
                    "Ошибка: в фокусе окно самого агента/IDE, ввод отменён, "
                    "чтобы не испортить код. Сначала открой нужное "
                    "приложение."
                )

            blind = True
            print(
                f"[Keyboard] {focus_result} "
                "Вставляю в окно с текущим фокусом."
            )
        else:
            print(f"[Keyboard] {focus_result}")

        try:
            old_clipboard = pyperclip.paste()
        except Exception:
            old_clipboard = None

        try:
            pyperclip.copy(text)
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.5)
        finally:
            if old_clipboard is not None:
                try:
                    pyperclip.copy(old_clipboard)
                except Exception:
                    pass

        if blind:
            return (
                "Вставка выполнена в окно с текущим фокусом. "
                "Целевое текстовое поле не было подтверждено."
            )

        return (
            "Вставка выполнена. UI Automation подтвердила фокус поля, "
            "но не проверяла вставленное содержимое."
        )

    except Exception as e:
        return f"Ошибка ввода текста: {e}"


def wait(
    seconds: float = 1.0,
) -> str:
    """
    Подождать заданное количество секунд.

    Допустимый диапазон:
    0.5-10 секунд.
    """
    try:
        seconds = max(
            0.5,
            min(
                10.0,
                float(seconds),
            ),
        )

    except (TypeError, ValueError):
        seconds = 1.0

    time.sleep(
        seconds
    )

    return (
        f"Ожидание {seconds:.1f} сек."
    )
