"""Голос: загрузка моделей, wake word, запись команды, STT и TTS."""
import os
import tempfile
import time
import wave

import numpy as np
import scipy.io.wavfile
import sounddevice as sd

from faster_whisper import WhisperModel
from piper import PiperVoice
import openwakeword
from openwakeword.model import Model as WakeWordModel

from config import (
    SAMPLE_RATE, CHANNELS,
    WHISPER_MODEL, PIPER_MODEL, PIPER_VOICE_NAME,
    WAKEWORD_NAME, WAKEWORD_THRESHOLD, WAKEWORD_FRAME_SIZE, WAKEWORD_FRAMEWORK,
    COMMAND_START_TIMEOUT, COMMAND_MAX_SECONDS,
    COMMAND_SILENCE_SECONDS, COMMAND_SILENCE_THRESHOLD,
)

whisper: WhisperModel | None = None
piper_voice: PiperVoice | None = None
wake_model: WakeWordModel | None = None


def load_models() -> None:
    global whisper, piper_voice, wake_model

    print("Загрузка Whisper...")
    whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

    print("Загрузка Piper...")
    if not PIPER_MODEL.exists():
        raise FileNotFoundError(
            f"Голос Piper не найден:\n{PIPER_MODEL}\n\n"
            f"Выполни:\n"
            f"python -m piper.download_voices --data-dir voices {PIPER_VOICE_NAME}"
        )
    piper_voice = PiperVoice.load(str(PIPER_MODEL))

    print("Загрузка wake word...")
    try:
        openwakeword.utils.download_models()
    except Exception as e:
        print(f"Предупреждение: не удалось скачать модели wake word: {e}")

    wake_model = WakeWordModel(
        wakeword_models=[WAKEWORD_NAME],
        inference_framework=WAKEWORD_FRAMEWORK,
    )


# --- TTS ----------------------------------------------------

def speak(text: str) -> None:
    if not text:
        return

    fd, audio_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    try:
        with wave.open(audio_path, "wb") as wav_file:
            if hasattr(piper_voice, "synthesize_wav"):
                piper_voice.synthesize_wav(text, wav_file)
            else:  # старые версии piper-tts
                piper_voice.synthesize(text, wav_file)

        sample_rate, audio_data = scipy.io.wavfile.read(audio_path)
        sd.play(audio_data, sample_rate)
        sd.wait()
    except Exception as e:
        print(f"Ошибка TTS: {e}")
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


# --- Wake word ----------------------------------------------

def wait_for_wake_word() -> None:
    print('Ожидание wake word "Hey Jarvis"...')
    wake_model.reset()

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=WAKEWORD_FRAME_SIZE,
    ) as stream:
        while True:
            data, overflowed = stream.read(WAKEWORD_FRAME_SIZE)
            if overflowed:
                print("[Wake] Audio overflow")

            prediction = wake_model.predict(data[:, 0].copy())
            score = max(prediction.values())

            if score >= WAKEWORD_THRESHOLD:
                print(f"[Wake] Wake word detected (score={score:.2f})")
                wake_model.reset()
                return


# --- Запись команды -----------------------------------------

def record_command() -> np.ndarray | None:
    print("Слушаю...")

    chunks = []
    started_speaking = False
    silence_time = 0.0
    blocksize = int(SAMPLE_RATE * 0.1)
    start_time = time.monotonic()

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=blocksize,
    ) as stream:
        while True:
            data, overflowed = stream.read(blocksize)
            if overflowed:
                print("[Audio] Input overflow")

            chunk = data[:, 0].copy()
            chunks.append(chunk)

            elapsed = time.monotonic() - start_time
            rms = float(np.sqrt(np.mean(chunk ** 2)))

            if rms >= COMMAND_SILENCE_THRESHOLD:
                started_speaking = True
                silence_time = 0.0
            elif started_speaking:
                silence_time += blocksize / SAMPLE_RATE
                if silence_time >= COMMAND_SILENCE_SECONDS:
                    break

            if not started_speaking and elapsed >= COMMAND_START_TIMEOUT:
                print("Время ожидания команды истекло.")
                return None

            if elapsed >= COMMAND_MAX_SECONDS:
                print("Достигнут лимит длины команды.")
                break

    if not chunks:
        return None
    return np.concatenate(chunks)


def save_audio(audio: np.ndarray) -> str:
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    audio_int16 = np.int16(np.clip(audio, -1.0, 1.0) * 32767)
    scipy.io.wavfile.write(path, SAMPLE_RATE, audio_int16)
    return path


# --- STT ----------------------------------------------------

def transcribe(audio_path: str) -> str:
    segments, _info = whisper.transcribe(
        audio_path, language="ru", beam_size=5, vad_filter=True
    )
    return "".join(segment.text for segment in segments).strip()
