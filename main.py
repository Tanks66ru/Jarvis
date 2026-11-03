"""Jarvis: точка входа и главный цикл."""
import os
import time

import pyautogui

import audio
import confirmation
from agent import run_agent
from history import update_conversation_history
from textutils import is_goodbye, is_confirmation, is_denial
from tools import cleanup_screenshots

VERSION = "0.63"


def say(text: str, pause: float = 0.4) -> None:
    print(f"Jarvis: {text}")
    audio.speak(text)
    # Даём микрофону перестать слышать собственный TTS.
    time.sleep(pause)


def handle_confirmation(user_text: str) -> None:
    if is_confirmation(user_text):
        print("Подтверждение получено.")
        say(confirmation.execute_pending())
    elif is_denial(user_text):
        confirmation.clear_pending()
        say("Действие отменено.")
    else:
        say("Нужно подтверждение. Скажи «да» или «нет».")


def print_banner() -> None:
    line = "=" * 32
    print(f"\n{line}\n        JARVIS v{VERSION}\n{line}")
    print('Wake word: "Hey Jarvis"')
    print("После ответа можно говорить сразу без wake word.")
    print('Для выхода из разговора скажи "пока".')
    print("Для аварийной остановки перемести мышь в левый верхний угол.\n")


def main() -> None:
    pyautogui.FAILSAFE = True

    audio.load_models()
    print("Jarvis готов.")
    print_banner()

    conversation_mode = False

    while True:
        try:
            # --- Wake word ---------------------------------
            if not conversation_mode:
                audio.wait_for_wake_word()
                time.sleep(0.3)  # не ловим остаток wake word
                print("[Jarvis] Слушаю.")
                audio.speak("Слушаю.")
                conversation_mode = True

            # --- Запись команды ----------------------------
            recorded = audio.record_command()
            if recorded is None:
                print("[Jarvis] Нет команды. Возвращаюсь в режим ожидания.")
                conversation_mode = False
                continue

            # --- STT ---------------------------------------
            audio_path = audio.save_audio(recorded)
            try:
                print("Распознаю...")
                user_text = audio.transcribe(audio_path)
            finally:
                try:
                    os.remove(audio_path)
                except OSError:
                    pass

            if not user_text:
                print("Ничего не расслышал.")
                continue

            print(f"Ты: {user_text}")

            # --- Прощание ----------------------------------
            if is_goodbye(user_text):
                confirmation.clear_pending()
                conversation_mode = False
                say("Хорошо.", pause=0)
                continue

            # --- Ожидается подтверждение -------------------
            if confirmation.has_pending():
                handle_confirmation(user_text)
                continue

            # --- Агент -------------------------------------
            print("Jarvis думает...")
            answer = run_agent(user_text)
            update_conversation_history(user_text, answer)
            say(answer)

        except KeyboardInterrupt:
            print("\nJarvis выключен.")
            break
        except Exception as e:
            print(f"Критическая ошибка: {e}")
            time.sleep(1)
        finally:
            cleanup_screenshots()


if __name__ == "__main__":
    main()
