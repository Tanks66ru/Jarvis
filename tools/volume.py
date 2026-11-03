"""Громкость системы (Windows, pycaw)."""
import ctypes

from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL


def _endpoint():
    devices = AudioUtilities.GetSpeakers()

    # Новые версии pycaw
    if hasattr(devices, "EndpointVolume"):
        return devices.EndpointVolume

    # Старые версии pycaw
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))


def get_volume() -> str:
    """Текущая громкость и состояние mute."""
    try:
        v = _endpoint()
        return f"Громкость: {v.GetMasterVolumeLevelScalar() * 100:.0f}%\nMuted: {bool(v.GetMute())}"
    except Exception as e:
        return f"Ошибка громкости: {e}"


def set_volume(percent: int) -> str:
    """Установить громкость.

    Args:
        percent: Громкость от 0 до 100.
    """
    try:
        percent = max(0, min(100, int(percent)))
        _endpoint().SetMasterVolumeLevelScalar(percent / 100, None)
        return f"Громкость установлена: {percent}%"
    except Exception as e:
        return f"Ошибка установки громкости: {e}"


def _change_volume(delta: int) -> str:
    v = _endpoint()
    level = max(0.0, min(1.0, v.GetMasterVolumeLevelScalar() + delta / 100))
    v.SetMasterVolumeLevelScalar(level, None)
    return f"Громкость: {level * 100:.0f}%"


def volume_up(amount: int = 5) -> str:
    """Увеличить громкость.

    Args:
        amount: На сколько процентов (1-50).
    """
    try:
        return _change_volume(max(1, min(50, int(amount))))
    except Exception as e:
        return f"Ошибка громкости: {e}"


def volume_down(amount: int = 5) -> str:
    """Уменьшить громкость.

    Args:
        amount: На сколько процентов (1-50).
    """
    try:
        return _change_volume(-max(1, min(50, int(amount))))
    except Exception as e:
        return f"Ошибка громкости: {e}"


def mute() -> str:
    """Включить или выключить звук (переключатель mute)."""
    try:
        v = _endpoint()
        current = bool(v.GetMute())
        v.SetMute(not current, None)
        return f"Muted: {not current}"
    except Exception as e:
        return f"Ошибка mute: {e}"
