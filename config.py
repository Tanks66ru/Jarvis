"""Все настройки Jarvis в одном месте."""

from pathlib import Path


# --- Пути ----------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

MEMORY_DIR = BASE_DIR / "memory"
VOICES_DIR = BASE_DIR / "voices"

MEMORY_DIR.mkdir(exist_ok=True)
VOICES_DIR.mkdir(exist_ok=True)


# --- Модели -------------------------------------------------

OLLAMA_MODEL = "qwen3.5:4b"

# Контекст для агентного цикла.
CONTEXT_SIZE = 16384

# Whisper.
WHISPER_MODEL = "small"

# Piper.
PIPER_VOICE_NAME = "ru_RU-dmitri-medium"
PIPER_MODEL = VOICES_DIR / f"{PIPER_VOICE_NAME}.onnx"


# --- Аудио --------------------------------------------------

SAMPLE_RATE = 16000
CHANNELS = 1


# --- Wake word ----------------------------------------------

WAKEWORD_NAME = "hey_jarvis"

WAKEWORD_THRESHOLD = 0.5

# openWakeWord использует 16 kHz mono.
WAKEWORD_FRAME_SIZE = 1280

# На Windows ONNX обычно удобнее, чем tflite-runtime.
WAKEWORD_FRAMEWORK = "onnx"


# --- Запись команды -----------------------------------------

COMMAND_START_TIMEOUT = 10.0
COMMAND_MAX_SECONDS = 20.0
COMMAND_SILENCE_SECONDS = 1.0
COMMAND_SILENCE_THRESHOLD = 0.012


# --- Агент --------------------------------------------------

# Общая пауза после tool, если отдельная не указана.
DEFAULT_ACTION_DELAY = 0.4

# Максимум итераций агента.
MAX_AGENT_STEPS = 30

# Сколько последних обычных ходов разговора хранить.
MAX_HISTORY_TURNS = 6

# Сколько сообщений промежуточного агентного цикла держать
# перед обрезкой старого контекста.
AGENT_RECENT_MESSAGES = 14

# Автоматически делать новый screenshot после изменения UI.
AUTO_SCREENSHOT_AFTER_ACTION = True


# --- Экран / OCR --------------------------------------------

TESSERACT_LANG = "rus+eng"

# Если Tesseract находится нестандартно,
# можно вписать полный путь сюда.
TESSERACT_CMD = ""

# Средняя разница яркости 0-255 между двумя уменьшенными
# скриншотами, после которой считаем экран изменившимся.
SCREEN_CHANGE_THRESHOLD = 1.0

# Максимальная ширина изображения, которое отправляется модели.
SCREENSHOT_MAX_WIDTH = 1280


# --- Фразы --------------------------------------------------

GOODBYE_PHRASES = [
    "пока",
    "до свидания",
    "до связи",
    "отбой",
    "джарвис пока",
]


CONFIRMATIONS = {
    "да",
    "подтверждаю",
    "выполняй",
    "согласен",
    "давай",
}


DENIALS = {
    "нет",
    "отмена",
    "отменяй",
    "отменить",
    "не надо",
    "не делай",
}