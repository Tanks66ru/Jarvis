"""Диагностика зрения модели.

Запуск:
    python debug_vision.py

Тест 1:
    Обычное сообщение со скриншотом.

Тест 2:
    Реальный open_app -> ожидание -> новый скриншот -> сообщение
    с tool result + CURRENT_SCREEN.
"""

import time

from ollama import chat

from config import OLLAMA_MODEL, CONTEXT_SIZE
from tools import AVAILABLE_TOOLS, open_app, screenshot


def ask(messages, tools=None):
    return chat(
        model=OLLAMA_MODEL,
        messages=messages,
        tools=tools,
        think=False,
        options={"num_ctx": CONTEXT_SIZE},
    ).message


# ------------------------------------------------------------
# Тест 1: прямое зрение
# ------------------------------------------------------------

path = screenshot()

print("\n=== Тест 1: скриншот в обычном сообщении ===")

message = ask(
    [
        {
            "role": "user",
            "content": (
                "Опиши, что на этом скриншоте. "
                "Какие окна и программы видны?"
            ),
            "images": [path],
        }
    ]
)

print("content:", message.content)
print("tool_calls:", message.tool_calls)


# ------------------------------------------------------------
# Тест 2: tool -> новый screenshot -> модель
# ------------------------------------------------------------

print("\n=== Тест 2: скриншот после tool-вызова ===")

print("[Test] Открываю блокнот...")

tool_result = open_app("notepad")

# Даём приложению реально появиться.
time.sleep(0.8)

after_path = screenshot()

test_messages = [
    {
        "role": "user",
        "content": "Открой блокнот и проверь, что он действительно открыт.",
    },
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "type": "function",
                "function": {
                    "name": "open_app",
                    "arguments": {
                        "name": "notepad",
                    },
                },
            }
        ],
    },
    {
        "role": "tool",
        "content": tool_result,
        "tool_name": "open_app",
    },
    {
        "role": "user",
        "content": (
            "[CURRENT_SCREEN]\n"
            "Это новый скриншот ПОСЛЕ выполнения open_app.\n"
            "Проверь именно изображение.\n"
            "Если блокнот действительно открыт, "
            "ответь только «Готово» без вызова tool.\n"
            "Если блокнота нет, опиши, что ты видишь."
        ),
        "images": [after_path],
    },
]

message = ask(
    test_messages,
    tools=AVAILABLE_TOOLS,
)

print("content:", message.content)
print("tool_calls:", message.tool_calls)