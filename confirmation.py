"""Подтверждение опасных действий (выключение, закрытие процессов и т.д.)."""
import subprocess

import psutil

_pending: dict | None = None


def set_pending(action: str, description: str, **extra) -> None:
    global _pending
    _pending = {"action": action, "description": description, **extra}


def clear_pending() -> None:
    global _pending
    _pending = None


def has_pending() -> bool:
    return _pending is not None


def pending_description() -> str:
    return _pending["description"] if _pending else ""


def execute_pending() -> str:
    global _pending

    if _pending is None:
        return "Нет ожидающего подтверждения."

    pending = _pending
    action = pending["action"]

    try:
        if action == "shutdown":
            subprocess.run(["shutdown", "/s", "/t", "0"], check=False)
            return "Компьютер выключается."

        if action == "restart":
            subprocess.run(["shutdown", "/r", "/t", "0"], check=False)
            return "Компьютер перезагружается."

        if action == "terminate_process":
            pid = int(pending["pid"])
            process = psutil.Process(pid)
            name = process.name()
            process.terminate()
            return f"Процесс {name} (PID {pid}) завершён."

        if action == "close_app":
            name = pending["name"]
            result = subprocess.run(
                ["taskkill", "/IM", name, "/F"],
                check=False, capture_output=True, text=True,
            )
            if result.returncode != 0:
                return f"Не удалось закрыть {name}: возможно, он не запущен."
            return f"Приложение {name} закрыто."

        return "Неизвестное подтверждённое действие."

    except Exception as e:
        return f"Ошибка выполнения подтверждённого действия: {e}"

    finally:
        _pending = None
