"""Windows UI Automation: структурированное состояние активного окна."""

from __future__ import annotations

import ctypes
import ctypes.wintypes

from pywinauto import Desktop


# ============================================================
# Настройки
# ============================================================
# Процессы самого агента / IDE. Их окно не может быть «целевым приложением».
SELF_PROCESS_NAMES = {
    "pycharm64.exe",
    "pycharm.exe",
    "idea64.exe",
    "python.exe",
    "pythonw.exe",
}

MAX_ELEMENTS = 60

INTERACTIVE_TYPES = {
    "Button",
    "CheckBox",
    "ComboBox",
    "Edit",
    "Hyperlink",
    "ListItem",
    "MenuItem",
    "RadioButton",
    "Slider",
    "TabItem",
    "TreeItem",
}


# ============================================================
# Windows
# ============================================================


def _get_foreground_hwnd() -> int:
    """Получить HWND текущего foreground-окна."""
    return int(
        ctypes.windll.user32.GetForegroundWindow()
    )


def _get_window_process_id(hwnd: int) -> int:
    """Получить PID процесса окна."""
    pid = ctypes.wintypes.DWORD()

    ctypes.windll.user32.GetWindowThreadProcessId(
        hwnd,
        ctypes.byref(pid),
    )

    return int(pid.value)


def _get_window_title(hwnd: int) -> str:
    """Получить заголовок окна."""
    user32 = ctypes.windll.user32

    length = user32.GetWindowTextLengthW(
        hwnd
    )

    if length <= 0:
        return ""

    buffer = ctypes.create_unicode_buffer(
        length + 1
    )

    user32.GetWindowTextW(
        hwnd,
        buffer,
        length + 1,
    )

    return buffer.value.strip()


def _get_process_name(pid: int) -> str:
    """Получить имя процесса."""
    try:
        import psutil

        return (
            psutil.Process(pid).name()
            or ""
        )

    except Exception:
        return ""
def get_foreground_process_name() -> str:
    """Имя exe процесса окна переднего плана (в нижнем регистре)."""
    hwnd = _get_foreground_hwnd()

    if not hwnd:
        return ""

    return _get_process_name(
        _get_window_process_id(hwnd)
    ).lower()

# ============================================================
# Helpers
# ============================================================


def _safe_string(value) -> str:
    try:
        return str(value or "").strip()
    except Exception:
        return ""


def _get_control_type(
    element,
) -> str:
    try:
        return _safe_string(
            element.element_info.control_type
        )
    except Exception:
        return ""


def _get_element_name(
    element,
) -> str:
    try:
        return _safe_string(
            element.element_info.name
        )
    except Exception:
        return ""


def _is_visible(
    element,
) -> bool:
    try:
        return bool(
            element.element_info.visible
        )
    except Exception:
        return True


def _is_enabled(
    element,
) -> bool:
    try:
        return bool(
            element.element_info.enabled
        )
    except Exception:
        return True


def _get_element_id(
    element,
) -> str:
    try:
        return _safe_string(
            element.element_info.automation_id
        )
    except Exception:
        return ""


def _get_element_class_name(
    element,
) -> str:
    try:
        return _safe_string(
            element.element_info.class_name
        )
    except Exception:
        return ""


# ============================================================
# Active window
# ============================================================


def _get_active_window_wrapper():
    """
    Вернуть wrapper текущего foreground-окна.
    """
    hwnd = _get_foreground_hwnd()

    if not hwnd:
        return None, None

    try:
        desktop = Desktop(
            backend="uia"
        )

        window = desktop.window(
            handle=hwnd
        )

        return hwnd, window

    except Exception:
        return hwnd, None


# ============================================================
# UI elements
# ============================================================


def _collect_interactive_elements(
    window,
) -> list[dict]:
    """
    Собрать интерактивные элементы активного окна.

    Данные специально ограничены, чтобы не засовывать
    в контекст модели гигантское UI-дерево.
    """
    elements: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    try:
        descendants = window.descendants()

    except Exception:
        return elements

    for element in descendants:
        control_type = _get_control_type(
            element
        )

        if control_type not in INTERACTIVE_TYPES:
            continue

        if not _is_visible(element):
            continue

        name = _get_element_name(
            element
        )

        if not name:
            continue

        automation_id = _get_element_id(
            element
        )

        key = (
            control_type,
            name.casefold(),
            automation_id,
        )

        if key in seen:
            continue

        seen.add(key)

        elements.append(
            {
                "name": name,
                "type": control_type,
                "enabled": _is_enabled(
                    element
                ),
                "automation_id": automation_id,
            }
        )

        if len(elements) >= MAX_ELEMENTS:
            break

    return elements


# ============================================================
# Public UI context tool
# ============================================================


def get_ui_context() -> str:
    """
    Получить структурированное состояние
    текущего активного окна Windows.

    Используется вместо screenshot там, где приложение
    предоставляет нормальный UI Automation tree.
    """
    hwnd, window = (
        _get_active_window_wrapper()
    )

    if not hwnd:
        return (
            "[UI_CONTEXT]\n"
            "Foreground window не найдено."
        )

    title = _get_window_title(
        hwnd
    )

    pid = _get_window_process_id(
        hwnd
    )

    process_name = _get_process_name(
        pid
    )

    lines = [
        "[UI_CONTEXT]",
        f"Window: {title or '(без заголовка)'}",
        f"Process: {process_name or '(unknown)'}",
        f"PID: {pid}",
    ]
    if process_name.lower() in SELF_PROCESS_NAMES:
        lines.append(
            "[HINT] В фокусе окно самого агента/IDE, а не целевое "
            "приложение. Целевое приложение НЕ открыто. Не кликай и не "
            "печатай в это окно. Используй open_app."
        )

        return "\n".join(lines)

    if window is None:
        lines.extend(
            [
                "UI Automation: недоступен.",
                "Используй screenshot(), "
                "если нужно визуально осмотреть окно.",
            ]
        )

        return "\n".join(lines)

    elements = (
        _collect_interactive_elements(
            window
        )
    )

    if not elements:
        lines.extend(
            [
                "Interactive controls: не найдены.",
                "Для визуального интерфейса "
                "используй screenshot().",
            ]
        )

        return "\n".join(lines)

    lines.append(
        f"Interactive controls: {len(elements)}"
    )

    for index, element in enumerate(
        elements,
        start=1,
    ):
        state = (
            "enabled"
            if element["enabled"]
            else "disabled"
        )

        automation_id = (
            f"; automation_id={element['automation_id']}"
            if element["automation_id"]
            else ""
        )

        lines.append(
            f"{index}. "
            f"{element['type']}: "
            f"\"{element['name']}\" "
            f"[{state}{automation_id}]"
        )

    return "\n".join(lines)


# ============================================================
# Finding elements
# ============================================================


def _get_descendants(
    window,
):
    try:
        return window.descendants()
    except Exception:
        return []


def _find_ui_element(
    name: str,
    control_type: str | None = None,
):
    """
    Найти UI-элемент по точному имени.

    Fuzzy-поиск здесь намеренно запрещён:
    неправильное совпадение может привести к клику
    не по тому контролу.
    """
    _, window = (
        _get_active_window_wrapper()
    )

    if window is None:
        return None

    wanted_name = (
        name.strip().casefold()
    )

    wanted_type = (
        control_type.strip().casefold()
        if control_type
        else None
    )

    for element in _get_descendants(
        window
    ):
        element_name = _get_element_name(
            element
        )

        if (
            element_name.casefold()
            != wanted_name
        ):
            continue

        element_type = _get_control_type(
            element
        )

        if (
            wanted_type
            and element_type.casefold()
            != wanted_type
        ):
            continue

        if not _is_visible(element):
            continue

        if not _is_enabled(element):
            return None

        return element

    return None


# ============================================================
# Text input focus
# ============================================================


def _is_edit_element(
    element,
) -> bool:
    return (
        _get_control_type(element)
        == "Edit"
        and _is_visible(element)
        and _is_enabled(element)
    )


def _looks_like_search_input(
    element,
) -> bool:
    """
    Определить, похоже ли Edit-поле
    на поиск / адресную строку / запрос.
    """
    name = (
        _get_element_name(element)
        .casefold()
    )

    automation_id = (
        _get_element_id(element)
        .casefold()
    )

    class_name = (
        _get_element_class_name(element)
        .casefold()
    )

    search_markers = (
        "search",
        "searchbox",
        "searchtextbox",
        "omnibox",
        "query",
        "find",
        "поиск",
        "поле поиска",
        "адрес",
        "address",
        "url",
    )

    text = (
        f"{name} "
        f"{automation_id} "
        f"{class_name}"
    )

    return any(
        marker in text
        for marker in search_markers
    )


def _get_focused_element(
    window,
):
    """
    Попытаться получить элемент,
    на котором сейчас находится keyboard focus.
    """
    try:
        focused = window.get_focus()

    except Exception:
        return None

    if focused is None:
        return None

    if not _is_edit_element(
        focused
    ):
        return None

    return focused


def _get_edit_elements(
    window,
) -> list:
    """
    Получить все доступные Edit-поля
    текущего foreground-окна.
    """
    edits = []

    for element in _get_descendants(
        window
    ):
        if not _is_edit_element(
            element
        ):
            continue

        edits.append(element)

    return edits


def _choose_text_input(
    edits: list,
):
    """
    Выбрать наиболее вероятное текстовое поле.

    Приоритет:

    1. Единственное поле.
    2. Явное search/address/query поле.
    3. Единственный лучший кандидат.

    При неоднозначности возвращает None.
    """
    if not edits:
        return None

    if len(edits) == 1:
        return edits[0]

    search_candidates = [
        element
        for element in edits
        if _looks_like_search_input(
            element
        )
    ]

    if len(search_candidates) == 1:
        return search_candidates[0]

    # Более точный поиск по AutomationId.
    exact_id_candidates = []

    for element in edits:
        automation_id = (
            _get_element_id(element)
            .casefold()
        )

        if automation_id in {
            "searchtextbox",
            "searchbox",
            "omnibox",
        }:
            exact_id_candidates.append(
                element
            )

    if len(exact_id_candidates) == 1:
        return exact_id_candidates[0]

    return None


def focus_text_input(
    target: str | None = None,
) -> str:
    """
    Установить keyboard focus на текстовое поле
    текущего foreground-окна.

    Если target указан, используется точное имя
    UI-элемента.

    Без target:
    - используется уже сфокусированный Edit;
    - затем ищется явное поле поиска;
    - затем единственное доступное Edit.

    Если подходящее поле нельзя определить однозначно,
    случайный Edit не выбирается.
    """
    try:
        _, window = (
            _get_active_window_wrapper()
        )

        if window is None:
            return (
                "Ошибка: UI Automation недоступен "
                "для активного окна."
            )

        # ----------------------------------------------------
        # 1. Явно указанное поле.
        # ----------------------------------------------------

        if target:
            element = _find_ui_element(
                target,
                "Edit",
            )

            if element is None:
                return (
                    f"Ошибка: текстовое поле "
                    f"'{target}' не найдено."
                )

            try:
                element.set_focus()

                return (
                    f"Фокус установлен на "
                    f"'{target}'."
                )

            except Exception as e:
                return (
                    f"Ошибка установки focus "
                    f"на '{target}': {e}"
                )

        # ----------------------------------------------------
        # 2. Уже сфокусированный Edit.
        # ----------------------------------------------------

        focused = _get_focused_element(
            window
        )

        if focused is not None:
            name = _get_element_name(
                focused
            )

            return (
                "Текстовое поле уже имеет focus"
                + (
                    f": '{name}'."
                    if name
                    else "."
                )
            )

        # ----------------------------------------------------
        # 3. Ищем доступные Edit.
        # ----------------------------------------------------

        edits = _get_edit_elements(
            window
        )

        if not edits:
            return (
                "Ошибка: в активном окне "
                "текстовое поле не найдено."
            )

        target_element = _choose_text_input(
            edits
        )

        if target_element is None:
            descriptions = []

            for element in edits[:10]:
                name = (
                    _get_element_name(element)
                    or "(без имени)"
                )

                automation_id = (
                    _get_element_id(element)
                )

                if automation_id:
                    descriptions.append(
                        f"Edit: {name} "
                        f"[automation_id={automation_id}]"
                    )
                else:
                    descriptions.append(
                        f"Edit: {name}"
                    )

            return (
                "Ошибка: найдено несколько "
                "текстовых полей, но нужное нельзя "
                "определить однозначно. "
                "Используй click_ui_element() "
                "для выбора нужного поля.\n"
                + "\n".join(descriptions)
            )

        # ----------------------------------------------------
        # 4. Устанавливаем focus.
        # ----------------------------------------------------

        try:
            target_element.set_focus()

        except Exception as e:
            name = (
                _get_element_name(
                    target_element
                )
                or "(без имени)"
            )

            return (
                f"Ошибка установки focus "
                f"на '{name}': {e}"
            )

        name = (
            _get_element_name(
                target_element
            )
            or "(без имени)"
        )

        return (
            f"Фокус установлен на "
            f"текстовом поле '{name}'."
        )

    except Exception as e:
        return (
            f"Ошибка установки focus "
            f"на текстовое поле: {e}"
        )


# ============================================================
# UI click
# ============================================================


def click_ui_element(
    name: str,
    control_type: str | None = None,
) -> str:
    """
    Нажать UI-элемент по его имени.

    Предпочтительнее координатной click(),
    если элемент доступен через UI Automation.

    Args:
        name:
            Точное имя UI-элемента.

        control_type:
            Необязательно.
            Например:
            Button, MenuItem, CheckBox, TabItem.
    """
    element = _find_ui_element(
        name,
        control_type,
    )

    if element is None:
        return (
            f"Ошибка: UI-элемент "
            f"'{name}' не найден в активном окне."
        )

    element_type = _get_control_type(
        element
    )

    try:
        # Для Edit сначала явно устанавливаем
        # keyboard focus.
        if element_type == "Edit":
            element.set_focus()

            return (
                f"UI-элемент '{name}' "
                f"({element_type}) получил focus."
            )

        # Button и некоторые другие controls
        # могут поддерживать InvokePattern.
        if hasattr(element, "invoke"):
            try:
                element.invoke()

                return (
                    f"UI-элемент '{name}' "
                    f"({element_type}) активирован."
                )

            except Exception:
                pass

        element.click_input()

        return (
            f"UI-элемент '{name}' "
            f"({element_type}) нажат."
        )

    except Exception as e:
        return (
            f"Ошибка нажатия UI-элемента "
            f"'{name}': {e}"
        )


# ============================================================
# UI element information
# ============================================================


def get_ui_element(
    name: str,
    control_type: str | None = None,
) -> str:
    """Получить информацию о конкретном UI-элементе."""
    element = _find_ui_element(
        name,
        control_type,
    )

    if element is None:
        return (
            f"UI-элемент '{name}' не найден."
        )

    element_type = _get_control_type(
        element
    )

    automation_id = _get_element_id(
        element
    )

    return (
        f"UI-элемент: {name}\n"
        f"Тип: {element_type}\n"
        f"Enabled: {_is_enabled(element)}\n"
        f"Visible: {_is_visible(element)}\n"
        f"AutomationId: "
        f"{automation_id or '(none)'}"
    )
