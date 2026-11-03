"""Короткая история обычного разговора (без промежуточных шагов агента)."""
import copy

from config import MAX_HISTORY_TURNS
from prompts import SYSTEM_PROMPT

conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]


def get_history_copy() -> list[dict]:
    return copy.deepcopy(conversation_history)


def update_conversation_history(user_text: str, assistant_text: str) -> None:
    conversation_history.append({"role": "user", "content": user_text})
    conversation_history.append({"role": "assistant", "content": assistant_text})

    max_messages = 1 + MAX_HISTORY_TURNS * 2
    if len(conversation_history) > max_messages:
        del conversation_history[1:len(conversation_history) - max_messages + 1]
