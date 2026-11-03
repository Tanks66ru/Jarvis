"""Буфер обмена, информация о системе, процессы, питание."""
import ctypes
import os
import platform

import psutil
import pyperclip

import confirmation


# --- Буфер обмена -------------------------------------------

def get_clipboard() -> str:
    """Прочитать текст из буфера обмена."""
    try:
        content = pyperclip.paste()
        if len(content) > 5000:
            content = content[:5000] + "\n[Clipboard truncated]"
        return f"Буфер обмена:\n{content}"
    except Exception as e:
        return f"Ошибка clipboard: {e}"


def set_clipboard(text: str) -> str:
    """Записать текст в буфер обмена.

    Args:
        text: Текст для копирования.
    """
    try:
        pyperclip.copy(text)
        return "Буфер обмена обновлён."
    except Exception as e:
        return f"Ошибка clipboard: {e}"


# --- Информация ---------------------------------------------

def get_active_window() -> str:
    """Получить заголовок активного окна."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        buffer = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buffer, 512)
        return f"Активное окно: {buffer.value.strip()}"
    except Exception as e:
        return f"Ошибка получения активного окна: {e}"


def get_system_info() -> str:
    """Общая информация о компьютере: ОС, процессор, память, диск."""
    try:
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
        return (
            f"OS: {platform.platform()}\n"
            f"CPU: {platform.processor()}\n"
            f"CPU cores: {psutil.cpu_count(logical=True)}\n"
            f"RAM total: {ram.total / 1024**3:.1f} GB\n"
            f"RAM used: {ram.percent:.1f}%\n"
            f"Disk used: {disk.percent:.1f}%\n"
            f"Hostname: {platform.node()}"
        )
    except Exception as e:
        return f"Ошибка system info: {e}"


def get_cpu_usage() -> str:
    """Текущая загрузка процессора в процентах."""
    try:
        return f"Загрузка CPU: {psutil.cpu_percent(interval=0.3):.1f}%"
    except Exception as e:
        return f"Ошибка CPU: {e}"


def get_ram_usage() -> str:
    """Текущее использование оперативной памяти."""
    try:
        m = psutil.virtual_memory()
        return (
            f"RAM: {m.percent:.1f}% "
            f"({m.used / 1024**3:.1f} / {m.total / 1024**3:.1f} GB)"
        )
    except Exception as e:
        return f"Ошибка RAM: {e}"


def get_disk_usage(path: str = "C:\\") -> str:
    """Использование диска.

    Args:
        path: Корень диска, например "C:\\" или "D:\\".
    """
    try:
        d = psutil.disk_usage(path)
        return (
            f"Диск {path}: {d.percent:.1f}% занято "
            f"({d.used / 1024**3:.1f} / {d.total / 1024**3:.1f} GB)"
        )
    except Exception as e:
        return f"Ошибка диска: {e}"


def get_processes(filter_text: str = "", limit: int = 20) -> str:
    """Список процессов, отсортированный по использованию памяти.

    Args:
        filter_text: Часть имени процесса для фильтра (необязательно).
        limit: Сколько процессов показать (1-50).
    """
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 20

    needle = filter_text.lower().strip()
    processes = []

    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            name = process.info["name"] or ""
            if needle and needle not in name.lower():
                continue
            mem = process.info["memory_info"]
            processes.append((mem.rss if mem else 0, process.info["pid"], name))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    processes.sort(reverse=True)
    if not processes:
        return "Процессы не найдены."

    return "\n".join(
        f"PID={pid} {name} RAM={memory / 1024**2:.0f} MB"
        for memory, pid, name in processes[:limit]
    )


# --- Опасные действия (с подтверждением) --------------------

def terminate_process(pid: int) -> str:
    """Завершить процесс по PID (потребует подтверждения пользователя).

    Args:
        pid: Идентификатор процесса из get_processes().
    """
    try:
        pid = int(pid)
        if pid == os.getpid():
            return "Ошибка: нельзя завершить сам процесс Jarvis."
        name = psutil.Process(pid).name()
        confirmation.set_pending(
            "terminate_process",
            f"завершить процесс {name} (PID {pid})",
            pid=pid,
        )
        return f"Требуется подтверждение пользователя: завершить процесс {name} (PID {pid})."
    except Exception as e:
        return f"Ошибка процесса: {e}"


def lock_pc() -> str:
    """Заблокировать компьютер."""
    try:
        if ctypes.windll.user32.LockWorkStation() == 0:
            return "Не удалось заблокировать компьютер."
        return "Компьютер заблокирован."
    except Exception as e:
        return f"Ошибка блокировки: {e}"


def shutdown_pc() -> str:
    """Выключить компьютер (потребует подтверждения пользователя)."""
    confirmation.set_pending("shutdown", "выключить компьютер")
    return "Требуется подтверждение пользователя: выключить компьютер."


def restart_pc() -> str:
    """Перезагрузить компьютер (потребует подтверждения пользователя)."""
    confirmation.set_pending("restart", "перезагрузить компьютер")
    return "Требуется подтверждение пользователя: перезагрузить компьютер."
