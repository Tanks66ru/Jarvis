"""Приложения, файлы, папки, ссылки."""

import csv
import ctypes
import ctypes.wintypes
import glob
import io
import os
import re
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path

import confirmation
import psutil

from .ui_context import SELF_PROCESS_NAMES


# ============================================================
# Настройки
# ============================================================

_START_MENU_CACHE_TTL = 60.0
_REGISTERED_APPS_CACHE_TTL = 60.0

_FOCUS_TIMEOUT = 2.0
_FOCUS_POLL_INTERVAL = 0.05
_WINDOW_POLL_INTERVAL = 0.25
_APP_WINDOW_TIMEOUT = 8.0
_GAME_WINDOW_TIMEOUT = 45.0

_MIN_WINDOW_W = 120
_MIN_WINDOW_H = 80


# ============================================================
# Вспомогательные функции
# ============================================================


def _entry(
    *candidates: str,
    args: list[str] | None = None,
    console: bool = False,
    timeout: float = _APP_WINDOW_TIMEOUT,
) -> dict:
    return {
        "candidates": list(candidates),
        "args": args or [],
        "console": console,
        "timeout": timeout,
    }


def _normalize_app_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _normalize_for_match(text: str) -> str:
    text = re.sub(
        r"[^a-zа-яё0-9]+", " ", text.lower().strip(), flags=re.IGNORECASE
    )
    return " ".join(text.split())


def _compact(text: str) -> str:
    """'Dota 2' -> 'dota2'. Для строгого сравнения окон/процессов."""
    return re.sub(r"[^a-zа-яё0-9]+", "", text.lower())


# ============================================================
# Известные быстрые пути
# ============================================================

CHROME = _entry(
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
)

DISCORD = _entry(
    os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe"),
    args=["--processStart", "Discord.exe"],
)

# Steam может долго стартовать (обновление, вход), поэтому таймаут больше.
STEAM = _entry(
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Steam\steam.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\Steam\steam.exe"),
    timeout=30.0,
)

APP_ALIASES = {
    "notepad": _entry("notepad.exe"),
    "блокнот": _entry("notepad.exe"),
    "calculator": _entry("calc.exe"),
    "калькулятор": _entry("calc.exe"),
    "explorer": _entry("explorer.exe"),
    "проводник": _entry("explorer.exe"),
    "cmd": _entry("cmd.exe", console=True),
    "powershell": _entry("powershell.exe", console=True),
    "chrome": CHROME,
    "google chrome": CHROME,
    "гугл хром": CHROME,
    "гугл": CHROME,
    "discord": DISCORD,
    "дискорд": DISCORD,
    "steam": STEAM,
    "стим": STEAM,
}

# Игры Steam запускаются только через steam://rungameid/<appid>.
# ключ (нормализованное имя) -> (имя окна/процесса, appid)
STEAM_GAMES = {
    "dota 2": ("Dota 2", 570),
    "dota2": ("Dota 2", 570),
    "dota": ("Dota 2", 570),
    "дота 2": ("Dota 2", 570),
    "дота2": ("Dota 2", 570),
    "дота": ("Dota 2", 570),
}

# Имена приложений, для которых запасной вариант — URI.
URI_FALLBACKS = {
    "steam": "steam://open/main",
    "стим": "steam://open/main",
}


# ============================================================
# Кэш
# ============================================================

_start_menu_cache: list[Path] | None = None
_start_menu_cache_time = 0.0

_registered_apps_cache: list[tuple[str, str]] | None = None
_registered_apps_cache_time = 0.0


def _cache_expired(timestamp: float, ttl: float) -> bool:
    return time.monotonic() - timestamp >= ttl


# ============================================================
# Поиск executable
# ============================================================


def _resolve_executable(candidates: list[str]) -> str | None:
    for candidate in candidates:
        if not candidate:
            continue

        if "*" in candidate or "?" in candidate:
            for match in glob.glob(candidate):
                if os.path.isfile(match):
                    return match
            continue

        if os.path.isfile(candidate):
            return candidate

        found = shutil.which(candidate)
        if found:
            return found

    return None


# ============================================================
# Ярлыки меню Пуск
# ============================================================


def _start_menu_roots() -> list[Path]:
    candidates = [
        Path(os.path.expandvars(
            r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")),
        Path(os.path.expandvars(
            r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs")),
    ]
    return [p for p in candidates if p.is_dir()]


def _load_start_menu_cache() -> list[Path]:
    global _start_menu_cache, _start_menu_cache_time

    if (
        _start_menu_cache is not None
        and not _cache_expired(_start_menu_cache_time, _START_MENU_CACHE_TTL)
    ):
        return _start_menu_cache

    shortcuts: list[Path] = []
    for root in _start_menu_roots():
        try:
            shortcuts.extend(root.rglob("*.lnk"))
        except OSError:
            continue

    _start_menu_cache = shortcuts
    _start_menu_cache_time = time.monotonic()
    return shortcuts


def _score_text_match(requested_name: str, candidate_name: str) -> int:
    """Нечёткая оценка. Используется ТОЛЬКО для ярлыков и списка приложений."""
    requested = _normalize_for_match(requested_name)
    candidate = _normalize_for_match(candidate_name)

    if not requested or not candidate:
        return 0
    if candidate == requested:
        return 1000
    if candidate.startswith(requested):
        return 850
    if requested.startswith(candidate):
        return 800
    if requested in candidate:
        return 700
    if candidate in requested:
        return 650

    requested_set = set(requested.split())
    candidate_set = set(candidate.split())

    if requested_set and requested_set.issubset(candidate_set):
        return 600

    common = requested_set & candidate_set
    if common and len(common) / len(requested_set) >= 0.5:
        return 450

    return 0


def _find_start_menu_shortcut(name: str) -> Path | None:
    best_path: Path | None = None
    best_score = 0

    for shortcut in _load_start_menu_cache():
        score = _score_text_match(name, shortcut.stem)
        if score > best_score:
            best_score = score
            best_path = shortcut
            if score >= 1000:
                break

    return best_path


# ============================================================
# Registered Windows Apps
# ============================================================


def _load_registered_start_apps() -> list[tuple[str, str]]:
    global _registered_apps_cache, _registered_apps_cache_time

    if (
        _registered_apps_cache is not None
        and not _cache_expired(
            _registered_apps_cache_time, _REGISTERED_APPS_CACHE_TTL
        )
    ):
        return _registered_apps_cache

    try:
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "[Console]::OutputEncoding = "
                "[System.Text.Encoding]::UTF8; "
                "Get-StartApps | Select-Object Name, AppID | "
                "ConvertTo-Csv -NoTypeInformation"
            ),
        ]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if completed.returncode != 0:
            return []

        output = completed.stdout.strip()
        if not output:
            return []

        result: list[tuple[str, str]] = []
        for row in csv.DictReader(io.StringIO(output)):
            name = (row.get("Name") or "").strip()
            app_id = (row.get("AppID") or "").strip()
            if name and app_id:
                result.append((name, app_id))

        _registered_apps_cache = result
        _registered_apps_cache_time = time.monotonic()
        return result

    except (OSError, subprocess.SubprocessError, ValueError):
        return []


def _find_registered_start_app(name: str) -> tuple[str, str] | None:
    best_match: tuple[str, str] | None = None
    best_score = 0

    for display_name, app_id in _load_registered_start_apps():
        score = _score_text_match(name, display_name)
        if score > best_score:
            best_score = score
            best_match = (display_name, app_id)
            if score >= 1000:
                break

    return best_match


def _launch_registered_app(app_id: str) -> bool:
    try:
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


# ============================================================
# Окна Windows
# ============================================================

user32 = ctypes.windll.user32

_EnumWindowsProc = ctypes.WINFUNCTYPE(
    ctypes.wintypes.BOOL,
    ctypes.wintypes.HWND,
    ctypes.wintypes.LPARAM,
)

# Классы служебных окон (рабочий стол, панель задач).
_IGNORED_WINDOW_CLASSES = {
    "progman",
    "workerw",
    "shell_traywnd",
    "shell_secondarytraywnd",
    "tooltips_class32",
}

# У этих процессов заголовок окна НЕ считается признаком приложения
# (вкладка браузера «Steam Community» — не Steam, проект IDE — не игра).
_TITLE_MATCH_BLOCKED = (
    {
        "explorer.exe",
        "firefox.exe",
        "chrome.exe",
        "msedge.exe",
        "opera.exe",
        "brave.exe",
        "vivaldi.exe",
        "yandex.exe",
        "browser.exe",
        "code.exe",
        "windowsterminal.exe",
    }
    | set(SELF_PROCESS_NAMES)
)

# Предки текущего процесса, окна которых нельзя считать «целевым приложением».
_SELF_HOST_NAMES = set(SELF_PROCESS_NAMES) | {"windowsterminal.exe"}


def _self_pids() -> set[int]:
    """PID агента и его хоста (PyCharm / терминал)."""
    pids = {os.getpid()}
    try:
        for parent in psutil.Process(os.getpid()).parents():
            try:
                if (parent.name() or "").lower() in _SELF_HOST_NAMES:
                    pids.add(parent.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return pids


def _enum_windows() -> list[int]:
    result: list[int] = []

    def callback(hwnd, _lparam) -> bool:
        result.append(hwnd)
        return True

    user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return result


def _get_window_process_id(hwnd: int) -> int:
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _get_window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value.strip()


def _get_window_class(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def _is_cloaked(hwnd: int) -> bool:
    """Скрытые окна UWP/виртуальных рабочих столов: «видимы», но не на экране."""
    value = ctypes.wintypes.DWORD(0)
    try:
        hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            ctypes.wintypes.HWND(hwnd),
            14,  # DWMWA_CLOAKED
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        return False
    return hr == 0 and value.value != 0


def _is_real_app_window(hwnd: int) -> bool:
    """
    Настоящее окно приложения, которое пользователь реально видит.

    Отсеивает невидимые, cloaked, дочерние/owned, tool-окна,
    рабочий стол/панель задач и крошечные служебные окна.
    """
    if not user32.IsWindowVisible(hwnd):
        return False
    if _is_cloaked(hwnd):
        return False
    if user32.GetWindow(hwnd, 4):  # GW_OWNER
        return False

    ex_style = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
    if (ex_style & 0x80) and not (ex_style & 0x40000):
        # WS_EX_TOOLWINDOW без WS_EX_APPWINDOW
        return False

    if _get_window_class(hwnd).lower() in _IGNORED_WINDOW_CLASSES:
        return False

    if user32.IsIconic(hwnd):
        return True

    rect = ctypes.wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False

    return (
        rect.right - rect.left >= _MIN_WINDOW_W
        and rect.bottom - rect.top >= _MIN_WINDOW_H
    )


def _process_name_for_pid(pid: int, cache: dict[int, str]) -> str:
    if pid in cache:
        return cache[pid]
    try:
        name = psutil.Process(pid).name() or ""
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        name = ""
    cache[pid] = name
    return name


def _score_window(req: str, title: str, process_name: str) -> int:
    """
    Строгая оценка окна. req — результат _compact().

    Совпадение только по имени процесса или по заголовку
    (целиком / начало / конец). Никаких «общих слов» и подстрок.
    """
    stem = _compact(Path(process_name).stem)

    if stem and stem == req:
        return 1000

    if (
        len(req) >= 4
        and len(stem) >= 4
        and (stem.startswith(req) or req.startswith(stem))
    ):
        return 900

    if process_name.lower() not in _TITLE_MATCH_BLOCKED:
        t = _compact(title)
        if t and t == req:
            return 800
        if t and len(req) >= 4 and (t.startswith(req) or t.endswith(req)):
            return 700

    return 0


def _find_window_for_pid(pid: int) -> int | None:
    """Настоящее окно конкретного процесса."""
    if pid <= 0:
        return None

    for hwnd in _enum_windows():
        if _get_window_process_id(hwnd) != pid:
            continue
        if _is_real_app_window(hwnd):
            return hwnd

    return None


def _find_matching_window(
    name: str,
    alt_names: tuple[str, ...] | list[str] = (),
) -> int | None:
    """Найти настоящее окно приложения по имени (строго)."""
    reqs = [r for r in (_compact(n) for n in (name, *alt_names)) if r]
    if not reqs:
        return None

    self_pids = _self_pids()
    pid_names: dict[int, str] = {}

    best_hwnd: int | None = None
    best_score = 0

    for hwnd in _enum_windows():
        if not _is_real_app_window(hwnd):
            continue

        pid = _get_window_process_id(hwnd)
        if pid <= 0 or pid in self_pids:
            continue

        process_name = _process_name_for_pid(pid, pid_names)
        if not process_name:
            continue

        title = _get_window_title(hwnd)

        for req in reqs:
            score = _score_window(req, title, process_name)
            if score > best_score:
                best_score = score
                best_hwnd = hwnd

    return best_hwnd


def _find_matching_process(name: str) -> tuple[int, str] | None:
    """Существующий процесс (может работать без окна, например в трее)."""
    req = _compact(name)
    if not req:
        return None

    self_pids = _self_pids()
    best: tuple[int, str] | None = None
    best_score = 0

    try:
        processes = psutil.process_iter(["pid", "name"])
    except Exception:
        return None

    for process in processes:
        try:
            pid = process.info.get("pid")
            process_name = process.info.get("name") or ""
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

        if not pid or not process_name or pid in self_pids:
            continue

        stem = _compact(Path(process_name).stem)

        if stem == req:
            score = 1000
        elif (
            len(req) >= 4
            and len(stem) >= 4
            and (stem.startswith(req) or req.startswith(stem))
        ):
            score = 900
        else:
            score = 0

        if score > best_score:
            best_score = score
            best = (pid, process_name)

    return best


# ------------------------------------------------------------
# Фокус
# ------------------------------------------------------------


def _foreground_hwnd() -> int:
    return int(user32.GetForegroundWindow() or 0)


def _is_foreground_window(hwnd: int) -> bool:
    return bool(hwnd) and _foreground_hwnd() == int(hwnd)


def _foreground_description() -> str:
    """Что реально на переднем плане. Попадает в ответ tool как доказательство."""
    hwnd = _foreground_hwnd()
    if not hwnd:
        return "нет активного окна"

    title = _get_window_title(hwnd) or "(без заголовка)"
    process_name = _process_name_for_pid(_get_window_process_id(hwnd), {})
    return f"'{title}' ({process_name or 'unknown'})"


def _wait_foreground(hwnd: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_foreground_window(hwnd):
            return True
        time.sleep(_FOCUS_POLL_INTERVAL)
    return _is_foreground_window(hwnd)


def _focus_window(hwnd: int) -> bool:
    """
    Вывести окно на передний план.

    True только если окно действительно стало foreground.
    Окно разворачивается только если оно свёрнуто
    (максимизированное не «разворачивается» обратно).
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if not user32.IsWindowVisible(hwnd):
        return False
    if _is_foreground_window(hwnd):
        return True

    SW_SHOW = 5
    SW_RESTORE = 9

    # Попытка 1: обычная.
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)

    if _wait_foreground(hwnd, 0.6):
        return True

    # Попытка 2: AttachThreadInput + «тап» Alt, чтобы Windows
    # разрешила смену foreground.
    foreground = _foreground_hwnd()
    foreground_thread = (
        user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    )
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)

    attached = False
    try:
        if (
            foreground_thread
            and target_thread
            and foreground_thread != target_thread
        ):
            attached = bool(
                user32.AttachThreadInput(
                    foreground_thread, target_thread, True
                )
            )

        user32.keybd_event(0x12, 0, 0, 0)  # Alt down
        user32.keybd_event(0x12, 0, 2, 0)  # Alt up

        user32.ShowWindow(
            hwnd, SW_RESTORE if user32.IsIconic(hwnd) else SW_SHOW
        )
        user32.BringWindowToTop(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)
        user32.SetForegroundWindow(hwnd)

        return _wait_foreground(hwnd, _FOCUS_TIMEOUT)

    finally:
        if attached:
            user32.AttachThreadInput(
                foreground_thread, target_thread, False
            )


def _wait_for_window(
    name: str,
    timeout: float = _APP_WINDOW_TIMEOUT,
    preferred_pid: int | None = None,
    alt_names: tuple[str, ...] | list[str] = (),
) -> int | None:
    deadline = time.monotonic() + timeout

    while True:
        if preferred_pid:
            hwnd = _find_window_for_pid(preferred_pid)
            if hwnd is not None:
                return hwnd

        hwnd = _find_matching_window(name, alt_names)
        if hwnd is not None:
            return hwnd

        if time.monotonic() >= deadline:
            return None

        time.sleep(_WINDOW_POLL_INTERVAL)


def _activate_existing_app(
    name: str,
    alt_names: tuple[str, ...] | list[str] = (),
) -> bool:
    hwnd = _find_matching_window(name, alt_names)
    if hwnd is None:
        return False
    return _focus_window(hwnd)


def _finish_launch(
    label: str,
    hwnd: int | None,
    how: str = "",
) -> tuple[bool, str]:
    """Единый итог запуска: окно найдено? стало ли foreground?"""
    if hwnd is None:
        return (
            False,
            f"Приложение '{label}' запущено{how}, но его окно не найдено.",
        )

    if _focus_window(hwnd):
        return (
            True,
            f"Приложение '{label}' запущено{how} и выведено на передний "
            f"план. Активное окно: {_foreground_description()}.",
        )

    return (
        False,
        f"Приложение '{label}' запущено{how}, но окно не удалось вывести "
        f"на передний план. Активное окно: {_foreground_description()}.",
    )


# ------------------------------------------------------------
# Запуск разными способами
# ------------------------------------------------------------


def _launch_executable_and_focus(
    name: str,
    executable: str,
    args: list[str] | None = None,
    console: bool = False,
    timeout: float = _APP_WINDOW_TIMEOUT,
) -> tuple[bool, str]:
    try:
        kwargs = {}
        if console and hasattr(subprocess, "CREATE_NEW_CONSOLE"):
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE

        process = subprocess.Popen([executable, *(args or [])], **kwargs)

    except Exception as e:
        return False, f"Ошибка запуска '{executable}': {e}"

    hwnd = _wait_for_window(
        name,
        timeout=timeout,
        preferred_pid=process.pid,
        alt_names=[Path(executable).stem],
    )

    return _finish_launch(name, hwnd)


def _launch_uri_and_focus(
    name: str,
    uri: str,
    timeout: float,
) -> tuple[bool, str]:
    try:
        os.startfile(uri)
    except Exception as e:
        return False, f"Ошибка запуска {uri}: {e}"

    hwnd = _wait_for_window(name, timeout=timeout)
    return _finish_launch(name, hwnd, f" через {uri}")


def _launch_shortcut_and_focus(
    name: str,
    shortcut: Path,
) -> tuple[bool, str]:
    try:
        os.startfile(str(shortcut))
    except Exception as e:
        return False, f"Ошибка открытия ярлыка '{shortcut}': {e}"

    hwnd = _wait_for_window(name)
    return _finish_launch(name, hwnd, f" через ярлык '{shortcut.stem}'")


def _launch_registered_and_focus(
    name: str,
    display_name: str,
    app_id: str,
) -> tuple[bool, str]:
    if not _launch_registered_app(app_id):
        return (
            False,
            f"Ошибка запуска зарегистрированного приложения "
            f"'{display_name}'.",
        )

    hwnd = _wait_for_window(display_name, alt_names=[name])
    return _finish_launch(display_name, hwnd)


def _open_steam_game(display_name: str, appid: int) -> str:
    """
    Игры Steam: если окно уже есть — фокусируем,
    иначе запускаем через steam://rungameid (поднимет и Steam).
    """
    hwnd = _find_matching_window(display_name)

    if hwnd is not None and _focus_window(hwnd):
        return (
            f"Игра '{display_name}' уже запущена и выведена на передний "
            f"план. Активное окно: {_foreground_description()}."
        )

    uri = f"steam://rungameid/{appid}"

    try:
        os.startfile(uri)
    except Exception as e:
        return f"Ошибка: не удалось отправить {uri}: {e}"

    hwnd = _wait_for_window(display_name, timeout=_GAME_WINDOW_TIMEOUT)

    if hwnd is None:
        # Не ошибка: игра просто долго грузится.
        return (
            f"Запуск '{display_name}' отправлен через Steam ({uri}). "
            "Игра загружается, окно пока не появилось. "
            "Подожди через wait(10) и проверь get_ui_context. "
            "Не запускай повторно."
        )

    success, message = _finish_launch(display_name, hwnd, " через Steam")
    return message if success else f"Ошибка: {message}"


# ============================================================
# Запуск / переключение приложений
# ============================================================


def open_app(
    name: str,
) -> str:
    """
    Запустить приложение или переключиться на открытое окно.

    Результат всегда проверяется по реальному foreground-окну.
    В ответе указывается, какое окно фактически активно.
    Если приложение открыть не удалось, ответ начинается с 'Ошибка:'.

    Порядок:
    1. Игры Steam (steam://rungameid).
    2. Уже открытое окно.
    3. Быстрый known-путь (APP_ALIASES).
    4. PATH.
    5. Ярлык меню Пуск.
    6. Зарегистрированное приложение Windows.
    7. URI-запасной вариант (Steam).
    """
    normalized_name = _normalize_app_name(name)

    if not normalized_name:
        return "Ошибка: имя приложения пустое."

    key = _normalize_for_match(name)

    # 1. Игры Steam.
    game = STEAM_GAMES.get(key)
    if game is not None:
        return _open_steam_game(*game)

    entry = APP_ALIASES.get(normalized_name)
    alt_names: list[str] = []
    if entry is not None:
        resolved = _resolve_executable(entry["candidates"])
        if resolved:
            alt_names.append(Path(resolved).stem)

    last_error = ""

    # 2. Уже открытое окно.
    if _activate_existing_app(normalized_name, alt_names):
        return (
            f"Приложение '{name}' уже запущено и выведено на передний "
            f"план. Активное окно: {_foreground_description()}."
        )

    # Процесс есть, а окна нет (свёрнут в трей) — даём короткое время.
    existing = _find_matching_process(normalized_name)

    if existing is not None:
        existing_pid, process_name = existing
        print(
            f"[Apps] Найден процесс '{process_name}' (PID {existing_pid}), "
            "активного окна пока нет."
        )

        hwnd = _wait_for_window(
            normalized_name,
            timeout=2.0,
            preferred_pid=existing_pid,
            alt_names=alt_names,
        )

        if hwnd is not None and _focus_window(hwnd):
            return (
                f"Приложение '{name}' уже запущено и выведено на передний "
                f"план. Активное окно: {_foreground_description()}."
            )

    # 3. Известный быстрый путь.
    if entry is not None:
        executable = _resolve_executable(entry["candidates"])

        if executable is not None:
            success, message = _launch_executable_and_focus(
                normalized_name,
                executable,
                entry["args"],
                entry["console"],
                entry["timeout"],
            )
            if success:
                return message
            last_error = message
            print(f"[Apps] {message}")

    # 4. PATH.
    for exe_name in (
        normalized_name,
        f"{normalized_name}.exe"
        if not normalized_name.endswith(".exe")
        else "",
    ):
        if not exe_name:
            continue

        executable = shutil.which(exe_name)
        if executable is None:
            continue

        success, message = _launch_executable_and_focus(
            normalized_name, executable
        )
        if success:
            return message
        last_error = message
        print(f"[Apps] {message}")

    # 5. Ярлык меню Пуск.
    shortcut = _find_start_menu_shortcut(normalized_name)

    if shortcut is not None:
        success, message = _launch_shortcut_and_focus(
            normalized_name, shortcut
        )
        if success:
            return message
        last_error = message
        print(f"[Apps] {message}")

    # 6. Зарегистрированное приложение Windows.
    registered_app = _find_registered_start_app(normalized_name)

    if registered_app is not None:
        display_name, app_id = registered_app
        success, message = _launch_registered_and_focus(
            normalized_name, display_name, app_id
        )
        if success:
            return message
        last_error = message
        print(f"[Apps] {message}")

    # 7. URI-запасной вариант.
    uri = URI_FALLBACKS.get(key)

    if uri is not None:
        timeout = entry["timeout"] if entry is not None else 30.0
        success, message = _launch_uri_and_focus(
            normalized_name, uri, timeout
        )
        if success:
            return message
        last_error = message
        print(f"[Apps] {message}")

    if last_error:
        return f"Ошибка: не удалось открыть '{name}'. {last_error}"

    return (
        f"Ошибка: приложение '{name}' не найдено среди установленных "
        "приложений."
    )


# ============================================================
# Закрытие приложений
# ============================================================


def close_app(
    name: str,
) -> str:
    """
    Закрыть найденное окно приложения.

    Потребует подтверждения пользователя.
    """
    normalized_name = _normalize_app_name(name)

    if not normalized_name:
        return "Ошибка: имя приложения пустое."

    hwnd = _find_matching_window(normalized_name)

    if hwnd is None:
        return f"Приложение '{name}' не имеет подходящего открытого окна."

    pid = _get_window_process_id(hwnd)

    if pid <= 0:
        return f"Ошибка: не удалось определить процесс для '{name}'."

    try:
        process_name = psutil.Process(pid).name() or f"PID {pid}"
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        process_name = f"PID {pid}"

    confirmation.set_pending(
        "close_app",
        f"закрыть приложение {name}",
        name=process_name,
    )

    return (
        f"Требуется подтверждение пользователя: "
        f"закрыть приложение {name}."
    )


# ============================================================
# Файлы
# ============================================================


def open_file(
    path: str,
) -> str:
    """
    Открыть файл или папку программой по умолчанию.

    Args:
        path:
            Путь к файлу или папке.
            Можно использовать %переменные% и ~.
    """
    try:
        target = Path(os.path.expandvars(path)).expanduser()

        if not target.exists():
            return f"Файл или папка не найдены: {target}"

        if target.is_file() and target.suffix.lower() == ".exe":
            success, message = _launch_executable_and_focus(
                target.stem, str(target)
            )
            return message if success else f"Ошибка: {message}"

        os.startfile(str(target))
        return f"Открыто: {target}"

    except Exception as e:
        return f"Ошибка открытия: {e}"


# ============================================================
# URL
# ============================================================


def open_url(
    url: str,
) -> str:
    """
    Открыть URL в браузере по умолчанию.

    Args:
        url:
            Адрес, начинающийся с http:// или https://.
    """
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return "Ошибка: URL должен начинаться с http:// или https://"

    try:
        webbrowser.open(url)
        return f"Открыт URL: {url}"
    except Exception as e:
        return f"Ошибка открытия URL: {e}"


# ============================================================
# Папки
# ============================================================


def list_directory(
    path: str = ".",
) -> str:
    """
    Показать содержимое папки.

    Args:
        path:
            Путь к папке.
    """
    try:
        target = Path(os.path.expandvars(path)).expanduser()

        if not target.exists():
            return f"Путь не найден: {target}"

        items = []

        for item in sorted(
            target.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        ):
            prefix = "[DIR]" if item.is_dir() else "[FILE]"
            items.append(f"{prefix} {item.name}")

        if not items:
            return "Папка пустая."

        return "\n".join(items[:200])

    except Exception as e:
        return f"Ошибка чтения папки: {e}"


# ============================================================
# Поиск файлов
# ============================================================


def find_file(
    name: str,
    root: str = "",
) -> str:
    """
    Найти файл по части имени.

    Args:
        name:
            Часть имени файла.

        root:
            Папка для поиска.

            Если пусто:
            Desktop, Documents, Downloads.
    """
    filename = name.strip()

    if not filename:
        return "Ошибка: имя файла пустое."

    if root.strip():
        roots = [Path(os.path.expandvars(root)).expanduser()]
    else:
        home = Path.home()
        roots = [home / "Desktop", home / "Documents", home / "Downloads"]

    ignored_dirs = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "$recycle.bin",
    }

    results = []

    for search_root in roots:
        if not search_root.exists():
            continue

        try:
            for current_root, dirs, files in os.walk(search_root):
                dirs[:] = [
                    d for d in dirs if d.lower() not in ignored_dirs
                ]

                for file in files:
                    if filename.lower() in file.lower():
                        results.append(os.path.join(current_root, file))

                        if len(results) >= 50:
                            return "Найдено:\n" + "\n".join(results)

        except Exception:
            continue

    if not results:
        return f"Файл '{filename}' не найден."

    return "Найдено:\n" + "\n".join(results)