"""Агентный цикл: LLM + tools + зрение."""

import json
import re
import time
from collections.abc import Mapping

from ollama import chat

import confirmation
from config import (
    OLLAMA_MODEL,
    CONTEXT_SIZE,
    MAX_AGENT_STEPS,
    AGENT_RECENT_MESSAGES,
    DEFAULT_ACTION_DELAY,
)

from history import get_history_copy
from prompts import COMPACT_NOTE

from tools import (
    AVAILABLE_TOOLS,
    AVAILABLE_FUNCTIONS,
    TOOL_DELAYS,
    screenshot,
    get_latest_screenshot,
    screen_changed,
    get_ui_context,
)


SCREEN_KEYWORDS = [
    "экран",
    "на экране",
    "скрин",
    "скриншот",
    "что видно",
    "что отображается",
    "что открыто",
    "посмотри",
    "найди кнопку",
    "нажми кнопку",
    "кликни",
    "нажми на",
    "где находится",
    "где кнопка",
    "что за окно",
    "какое окно",
]


# Основы слов: «открой», «открою», «откроем», «открыть» и т.д.
COMPUTER_ACTION_PATTERNS = [
    r"\bоткр\w*",
    r"\bзапуск\w*",
    r"\bзапуст\w*",
    r"\bпереключ\w*",
    r"\bзакр\w*",
    r"\bнажм\w*",
    r"\bклик\w*",
    r"\bввед\w*",
    r"\bнапечат\w*",
    r"\bнапиш\w*",
    r"\bзайд\w*",
    r"\bнайд\w*",
    r"\bнайт\w*",
    r"\bищ\w*",
    r"\bпоищ\w*",
    r"\bпокаж\w*",
    r"\bвключ\w*",
    r"\bвыключ\w*",
    r"\bпостав\w*",
    r"\bизмени\w*",
    r"\bудал\w*",
    r"\bсоздай\w*",
    r"\bскача\w*",
    r"\bустанов\w*",
    r"\bотправ\w*",
    r"\bпоигра\w*",
    r"\bсыгра\w*",
]


# Голосовой ввод даёт русские названия — они обязательны.
COMPUTER_OBJECT_PATTERNS = [
    r"\bприложен\w*",
    r"\bпрограм\w*",
    r"\bбраузер\w*",
    r"\bпроводник\b",
    r"\bфайл\w*",
    r"\bпапк\w*",
    r"\bокн\w*",
    r"\bкнопк\w*",
    r"\bпуск\b",
    r"\bкомпьютер\w*",
    r"\bсистем\w*",
    r"\bсайт\w*",
    r"\bвкладк\w*",
    r"\bигр(?:а|у|ы|е)\b",
    # латиница
    r"\bsteam\b",
    r"\bdota\b",
    r"\broblox\b",
    r"\bdiscord\b",
    r"\bchrome\b",
    r"\btelegram\b",
    r"\bspotify\b",
    r"\byoutube\b",
    # русские названия (с окончаниями, чтобы не ловить «стимул» и т.п.)
    r"\bстим(?:а|е|у|ом)?\b",
    r"\bдот(?:а|у|ы|е|ой)\b",
    r"\bроблокс\w*",
    r"\bдискорд\w*",
    r"\bхром(?:а|е|у|ом)?\b",
    r"\bтелеграм\w*",
    r"\bспотифай\w*",
    r"\bютуб(?:а|е|у|ом)?\b",
]


COMPUTER_STATE_PATTERNS = [
    r"\bчто\s+сейчас\s+открыто\b",
    r"\bкакое\s+окно\s+активно\b",
    r"\bчто\s+сейчас\s+на\s+экране\b",
    r"\bчто\s+ты\s+сейчас\s+видишь\b",
    r"\bчто\s+происходит\s+на\s+экране\b",
]


# Эти tools только читают состояние. Их повторение оправдано
# после изменения интерфейса, поэтому защита от повторов их не трогает.
STATE_READ_TOOLS = {
    "screenshot",
    "get_ui_context",
    "get_active_window",
    "get_system_info",
    "get_cpu_usage",
    "get_ram_usage",
    "get_disk_usage",
    "get_processes",
    "get_mouse_position",
    "get_clipboard",
    "ocr_screen",
}


# Внутренний маркер завершения задачи. Пользователь его не видит.
TASK_COMPLETE_MARKER = "[TASK_COMPLETE]"

REPEAT_LIMIT = 3


# ============================================================
# Routing
# ============================================================


def user_needs_screen(text: str) -> bool:
    text = text.lower()
    return any(keyword in text for keyword in SCREEN_KEYWORDS)


def user_needs_computer_task(text: str) -> bool:
    """
    Определяет, является ли запрос компьютерной задачей.

    Для обычного разговора UI tools не используются.
    Для действий над компьютером включается режим
    обязательного продолжения задачи.
    """
    text = text.lower().strip()

    if not text:
        return False

    if user_needs_screen(text):
        return True

    if any(
        re.search(p, text, flags=re.IGNORECASE)
        for p in COMPUTER_STATE_PATTERNS
    ):
        return True

    has_action = any(
        re.search(p, text, flags=re.IGNORECASE)
        for p in COMPUTER_ACTION_PATTERNS
    )

    if not has_action:
        return False

    return any(
        re.search(p, text, flags=re.IGNORECASE)
        for p in COMPUTER_OBJECT_PATTERNS
    )


def build_agent_rules(
    task_active: bool,
) -> str:
    """
    Короткие динамические правила текущего шага.

    Основные правила уже находятся в SYSTEM_PROMPT.
    """
    if task_active:
        return """
[EXECUTION_MODE]
Активна компьютерная задача пользователя.

Конечная цель ещё не подтверждена, пока результат не проверен.

Если цель НЕ достигнута:
- не отвечай пользователю обычным текстом;
- вызови ОДИН следующий подходящий tool;
- если текущий способ не работает, измени способ;
- продолжай выполнение задачи.

Не кликай по координатам, пока в свежем screenshot не видишь цель.
Не утверждай, что окно или приложение открыто, если этого нет
в tool result или UI_CONTEXT.
Игры Steam (например Dota 2) открывай через open_app с названием игры.
Если open_app сообщил, что запуск отправлен и игра загружается,
не запускай её повторно: используй wait и проверяй get_ui_context.

Обычный текст без tool call НЕ считается завершением задачи.

Если конечная цель полностью достигнута и проверена,
ответь с маркером:
[TASK_COMPLETE]
после которого можно дать короткий финальный ответ.

Не используй [TASK_COMPLETE], если результат не подтверждён.
""".strip()

    return """
[EXECUTION_MODE]
Активного компьютерного действия нет.

На обычный разговор отвечай нормально.
Не используй computer tools без необходимости.
""".strip()


# ============================================================
# Работа с сообщениями
# ============================================================


def remove_all_images(
    messages: list[dict],
) -> None:
    """В контексте остаётся только один актуальный screenshot."""
    for message in messages:
        if isinstance(message, dict):
            message.pop("images", None)


def count_images(
    messages: list[dict],
) -> int:
    return sum(
        1
        for message in messages
        if isinstance(message, dict) and message.get("images")
    )


def screen_instruction(
    header: str,
) -> str:
    """Текст рядом со screenshot."""
    changed = screen_changed()

    if changed is None:
        change_note = ""

    elif changed:
        change_note = (
            "Экран изменился по сравнению с предыдущим screenshot."
        )

    else:
        change_note = (
            "ВНИМАНИЕ: screenshot не показывает изменения экрана "
            "по сравнению с предыдущим. Действие могло не сработать "
            "или результат ещё не успел отобразиться."
        )

    return (
        "[CURRENT_SCREEN]\n"
        f"{header}\n"
        f"{change_note}\n"
        "Проверь текущую цель пользователя и уже выполненные действия.\n"
        "Ориентируйся на фактический tool result "
        "и текущее состояние экрана.\n"
        "Не выдумывай состояние компьютера.\n"
        "Если цель НЕ подтверждена как достигнутая, "
        "вызови ОДИН следующий tool.\n"
        "Если цель полностью достигнута и проверена, "
        f"используй {TASK_COMPLETE_MARKER}."
    )


def attach_current_screen(
    all_messages: list[dict],
    body: list[dict],
    screen_path: str,
    instruction: str,
) -> None:
    """
    Добавляет новый актуальный screenshot.
    Перед этим удаляет изображения из старых сообщений.
    """
    remove_all_images(all_messages)

    body.append(
        {
            "role": "user",
            "content": instruction,
            "images": [screen_path],
        }
    )


def trim_body(
    body: list[dict],
) -> tuple[list[dict], bool]:
    """Оставляет последние сообщения текущего агентного цикла."""
    if len(body) <= AGENT_RECENT_MESSAGES:
        return body, False

    start = len(body) - AGENT_RECENT_MESSAGES

    while (
        start > 0
        and isinstance(body[start], dict)
        and body[start].get("role") == "tool"
    ):
        start -= 1

    return body[start:], True


def progress_message(
    action_log: list[str],
    compacted: bool,
) -> list[dict]:
    """Краткая фактическая история текущей задачи."""
    parts = []

    if compacted:
        parts.append(COMPACT_NOTE)

    if action_log:
        parts.append(
            "Фактический журнал действий этой задачи.\n"
            "Учитывай его при выборе следующего действия.\n"
            "Не повторяй неработающий способ без причины.\n"
            + "\n".join(action_log[-12:])
        )

    if not parts:
        return []

    return [{"role": "system", "content": "\n".join(parts)}]


def ui_context_message(
    task_active: bool,
) -> dict | None:
    """
    Получает состояние foreground-окна через UIA.

    Нужен только во время компьютерной задачи. Подсказку про окно
    самого агента добавляет сам get_ui_context.
    """
    if not task_active:
        return None

    try:
        context = get_ui_context()

    except Exception as e:
        context = f"[UI_CONTEXT]\nОшибка получения UI context: {e}"

    return {"role": "system", "content": context}


def add_action_log(
    action_log: list[str],
    function_name: str,
    arguments,
    result: str,
) -> None:
    """Добавляет короткую запись фактического результата."""
    try:
        short_args = json.dumps(
            normalize_arguments(arguments),
            ensure_ascii=False,
            sort_keys=True,
        )[:120]

    except Exception:
        short_args = str(arguments)[:120]

    short_result = str(result).replace("\n", " ")[:160]

    status = "ОШИБКА" if str(result).startswith("Ошибка") else "OK"

    action_log.append(
        f"{len(action_log) + 1}. "
        f"{status}: {function_name}({short_args}) -> {short_result}"
    )


def continuation_message() -> dict:
    """
    Сообщение контроллера, когда модель пытается
    завершить активную компьютерную задачу обычным текстом.
    """
    return {
        "role": "system",
        "content": (
            "Задача пользователя ещё не завершена "
            "с точки зрения исполнительного контроллера.\n"
            "Твой предыдущий ответ был обычным текстом "
            "вместо tool call.\n\n"
            "НЕ ОСТАНАВЛИВАЙСЯ.\n"
            "НЕ ОБЪЯВЛЯЙ ЗАДАЧУ ВЫПОЛНЕННОЙ.\n"
            "Не объясняй, что собираешься делать.\n"
            "Немедленно вызови ОДИН подходящий tool "
            "для следующего шага.\n"
            "Если предыдущий план неверен, выбери другой способ.\n"
            "Продолжай до фактически подтверждённого результата.\n"
            f"Только после полного подтверждения цели используй "
            f"{TASK_COMPLETE_MARKER}."
        ),
    }


def clean_completion_text(
    content: str,
) -> str:
    """Убирает внутренний маркер завершения из ответа пользователю."""
    return content.replace(TASK_COMPLETE_MARKER, "").strip()


# ============================================================
# Tools
# ============================================================


def normalize_arguments(
    arguments,
) -> dict:
    """Приводит аргументы tool call к обычному dict."""
    if arguments is None:
        return {}

    if isinstance(arguments, Mapping):
        return dict(arguments)

    if isinstance(arguments, str):
        arguments = arguments.strip()

        if not arguments:
            return {}

        try:
            parsed = json.loads(arguments)

        except json.JSONDecodeError:
            raise ValueError(
                f"Аргументы tool не являются валидным JSON: {arguments}"
            )

        if not isinstance(parsed, dict):
            raise ValueError(
                f"Аргументы tool должны быть JSON-объектом: {parsed}"
            )

        return parsed

    raise ValueError(
        f"Неожиданный тип аргументов tool: {type(arguments).__name__}"
    )


def execute_tool(
    name: str,
    arguments,
) -> str:
    function = AVAILABLE_FUNCTIONS.get(name)

    if function is None:
        return f"Ошибка: неизвестный tool '{name}'."

    try:
        return str(function(**normalize_arguments(arguments)))

    except Exception as e:
        return f"Ошибка выполнения {name}: {e}"


def call_signature(
    name: str,
    arguments,
) -> str:
    try:
        return (
            name
            + ":"
            + json.dumps(
                normalize_arguments(arguments),
                sort_keys=True,
                ensure_ascii=False,
            )
        )

    except Exception:
        return name + ":" + str(arguments)


def get_tool_call_info(
    tool_call,
):
    """Безопасно достаёт name и arguments."""
    if isinstance(tool_call, dict):
        function = tool_call.get("function", {}) or {}
        name = function.get("name", "")
        arguments = function.get("arguments", {})

    else:
        function = getattr(tool_call, "function", None)

        if function is None:
            return "", {}

        name = getattr(function, "name", "")
        arguments = getattr(function, "arguments", {})

    return name, arguments


def make_assistant_tool_message(
    response_message,
) -> dict:
    """Собирает assistant message с tool calls. Текст модели сохраняется."""
    tool_calls = []

    for tool_call in response_message.tool_calls or []:
        function_name, arguments = get_tool_call_info(tool_call)

        tool_calls.append(
            {
                "type": "function",
                "function": {
                    "name": function_name,
                    "arguments": arguments,
                },
            }
        )

    return {
        "role": "assistant",
        "content": response_message.content or "",
        "tool_calls": tool_calls,
    }


# ============================================================
# Основной цикл
# ============================================================


def _run_agent_core(
    user_text: str,
) -> str:
    prefix = get_history_copy()

    current_user_message = {"role": "user", "content": user_text}

    prefix.append(current_user_message)

    body: list[dict] = []
    action_log: list[str] = []

    compacted = False
    used_tools = False

    # Главный флаг: пользователь действительно поставил
    # компьютерную задачу.
    task_active = user_needs_computer_task(user_text)

    recent_calls: list[str] = []

    # Screenshot сразу нужен только для явно визуальных запросов.
    if user_needs_screen(user_text):
        print("[Vision] Создаю начальный screenshot...")
        current_user_message["images"] = [screenshot()]

    for step in range(MAX_AGENT_STEPS):
        body, was_trimmed = trim_body(body)

        compacted = compacted or was_trimmed

        execution_mode = task_active or used_tools

        messages = prefix + progress_message(action_log, compacted)

        messages.append(
            {
                "role": "system",
                "content": build_agent_rules(execution_mode),
            }
        )

        current_ui_context = ui_context_message(execution_mode)

        if current_ui_context is not None:
            messages.append(current_ui_context)

        messages.extend(body)

        print(
            f"[Agent] Шаг {step + 1}/{MAX_AGENT_STEPS} "
            f"(сообщений: {len(messages)}, "
            f"с картинкой: {count_images(messages)})"
        )

        try:
            response = chat(
                model=OLLAMA_MODEL,
                messages=messages,
                tools=AVAILABLE_TOOLS,
                think=False,
                keep_alive="10m",
                options={"num_ctx": CONTEXT_SIZE},
            )

        except Exception as e:
            return f"Ошибка связи с Ollama: {e}"

        content = (response.message.content or "").strip()

        tool_calls = response.message.tool_calls or []

        if content:
            print(f"[Model] {content}")

        # ----------------------------------------------------
        # Нет tool calls.
        # ----------------------------------------------------

        if not tool_calls:
            if execution_mode:
                # Явный финал разрешён только после
                # хотя бы одного реально выполненного tool.
                if TASK_COMPLETE_MARKER in content and used_tools:
                    return clean_completion_text(content) or "Готово."

                # Мысли модели храним в истории задачи,
                # но пользователю не отдаём.
                if content:
                    body.append({"role": "assistant", "content": content})

                body.append(continuation_message())

                continue

            # Обычный разговор.
            if content:
                return content

            return "Готово." if used_tools else "Не понял задачу."

        used_tools = True
        task_active = True

        # ----------------------------------------------------
        # Assistant tool call.
        # ----------------------------------------------------

        body.append(make_assistant_tool_message(response.message))

        tool_call = tool_calls[0]

        function_name, arguments = get_tool_call_info(tool_call)

        if not function_name:
            body.append(
                {
                    "role": "tool",
                    "content": "Ошибка: модель не указала имя tool.",
                    "tool_name": "unknown",
                }
            )

            action_log.append(
                f"{len(action_log) + 1}. "
                "ОШИБКА: неизвестный tool — отклонён"
            )

            continue

        # ----------------------------------------------------
        # Repeat protection (tools чтения состояния не блокируются).
        # ----------------------------------------------------

        signature = call_signature(function_name, arguments)

        if function_name not in STATE_READ_TOOLS:
            recent_calls.append(signature)

            recent_calls[:] = recent_calls[-6:]

            if recent_calls.count(signature) >= REPEAT_LIMIT:
                print("[Agent] Обнаружен повтор одного действия.")

                body.append(
                    {
                        "role": "tool",
                        "content": (
                            "Ошибка: это действие уже выполнялось "
                            "несколько раз без прогресса. "
                            "Выбери другой способ."
                        ),
                        "tool_name": function_name,
                    }
                )

                action_log.append(
                    f"{len(action_log) + 1}. "
                    f"ОШИБКА: {function_name} — "
                    "ПОВТОР, действие отклонено"
                )

                attach_current_screen(
                    prefix + body,
                    body,
                    screenshot(),
                    screen_instruction(
                        "Ты несколько раз повторил одно и то же "
                        "действие без прогресса. Используй этот "
                        "свежий screenshot и выбери другой способ."
                    ),
                )

                recent_calls.clear()
                continue

        print(f"[Agent] {function_name}({arguments})")

        # ----------------------------------------------------
        # Выполнение tool.
        # ----------------------------------------------------

        result = execute_tool(function_name, arguments)

        print(f"[Tool result] {result}")

        body.append(
            {
                "role": "tool",
                "content": result,
                "tool_name": function_name,
            }
        )

        # Несколько tool calls: выполняем только первый.
        if len(tool_calls) > 1:
            for extra_call in tool_calls[1:]:
                extra_name, _extra_args = get_tool_call_info(extra_call)

                body.append(
                    {
                        "role": "tool",
                        "content": (
                            "Пропущено: агент выполняет не более "
                            "одного физического действия за итерацию."
                        ),
                        "tool_name": extra_name or "unknown",
                    }
                )

        add_action_log(action_log, function_name, arguments, result)

        # ----------------------------------------------------
        # Confirmation.
        # ----------------------------------------------------

        if (
            confirmation.has_pending()
            and "Требуется подтверждение" in result
        ):
            return (
                f"Подтверждаешь: {confirmation.pending_description()}? "
                f"Скажи «да» или «нет»."
            )

        # ----------------------------------------------------
        # Ошибка tool.
        # ----------------------------------------------------

        if result.startswith("Ошибка"):
            time.sleep(0.2)

            attach_current_screen(
                prefix + body,
                body,
                screenshot(),
                screen_instruction(
                    f"При выполнении {function_name} возникла ошибка. "
                    "Учитывай error result и уже выполненные действия. "
                    "Измени план и выбери следующий tool."
                ),
            )

            continue

        # ----------------------------------------------------
        # Delay.
        # ----------------------------------------------------

        delay = TOOL_DELAYS.get(function_name, DEFAULT_ACTION_DELAY)

        if delay > 0:
            print(f"[Agent] Жду {delay:.1f} сек. после {function_name}...")

            time.sleep(delay)

        # ----------------------------------------------------
        # Явный screenshot.
        # ----------------------------------------------------

        if function_name == "screenshot":
            current_screen = get_latest_screenshot() or result

            if current_screen:
                attach_current_screen(
                    prefix + body,
                    body,
                    current_screen,
                    screen_instruction(
                        "Это свежий screenshot, "
                        "который только что запросил агент."
                    ),
                )

            continue

        # ----------------------------------------------------
        # OCR.
        # ----------------------------------------------------

        if function_name == "ocr_screen":
            current_screen = get_latest_screenshot()

            if current_screen:
                attach_current_screen(
                    prefix + body,
                    body,
                    current_screen,
                    screen_instruction(
                        "Это текущий экран после OCR. "
                        "Используй OCR-текст и изображение вместе."
                    ),
                )

            continue

        # Автоматический screenshot после click/open_app/press_key
        # не делаем: на следующей итерации добавится свежий UI_CONTEXT.

    return f"Не удалось завершить задачу за {MAX_AGENT_STEPS} шагов."


# ============================================================
# Память незавершённой задачи
# ============================================================

FOLLOWUP_PATTERNS = [
    r"^\W*(да|давай|ну давай|ага|ок|окей|пробуй)\W*$",
    r"\b(ещё|еще)\s+раз\b",
    r"\bповтор\w*",
    r"\bпродолж\w*",
    r"\bпопробуй\w*",
    r"\bснова\b",
    r"\bдоделай\w*",
]

_pending_task: str | None = None


def _is_followup(text: str) -> bool:
    t = text.lower().strip()

    return len(t.split()) <= 8 and any(
        re.search(p, t) for p in FOLLOWUP_PATTERNS
    )


def run_agent(
    user_text: str,
) -> str:
    """
    Публичная точка входа.

    Если прошлая компьютерная задача не завершилась, короткие реплики
    вроде «давай» или «попробуй ещё раз» продолжают её, а не теряются.
    """
    global _pending_task

    effective = user_text

    if (
        _pending_task
        and _is_followup(user_text)
        and not user_needs_computer_task(user_text)
    ):
        effective = (
            f"{_pending_task}\n"
            f"(Пользователь просит продолжить: «{user_text}»)"
        )

        print(f"[Agent] Продолжаю незавершённую задачу: {_pending_task}")

    result = _run_agent_core(effective)

    if result.startswith("Не удалось завершить"):
        _pending_task = _pending_task or user_text

    elif not result.startswith("Подтверждаешь"):
        _pending_task = None

    return result