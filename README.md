# Jarvis

A local, voice-controlled desktop assistant for Windows. Jarvis combines speech recognition, speech synthesis, a local language model, and Windows automation tools in one agent loop.

The project is built as a personal software project and is still under active development. It is not a packaged desktop application.

## Features

- **Voice interaction:** wake-word detection with OpenWakeWord, speech recognition with Faster-Whisper, and Russian speech synthesis with Piper.
- **Local LLM agent:** tool-calling loop powered by Ollama. The model is configured in `config.py`.
- **Desktop automation:** mouse and keyboard input, application launching, file opening, and browser navigation.
- **Windows UI Automation:** reads accessible controls from the active window and can interact with named UI elements through Pywinauto.
- **Screen understanding:** screenshots and optional OCR through Tesseract.
- **System tools:** clipboard, active-window information, process and resource usage, volume control, and power actions.
- **Local memory:** stores user-approved notes as Markdown files in a local `memory/` directory.

## Architecture

- `main.py` — voice interaction loop and application entry point.
- `audio.py` — wake-word detection, recording, speech-to-text, and text-to-speech.
- `agent.py` — Ollama conversation loop, tool execution, task continuation, and screenshot handling.
- `prompts.py` — system instructions for the local assistant.
- `config.py` — model names, audio settings, timing, and local data directories.
- `confirmation.py` — confirmation flow for potentially destructive actions.
- `tools/` — desktop, UI, screen, system, memory, and volume tools.

## Requirements

- Windows 10 or Windows 11.
- Python 3.11 recommended.
- [Ollama](https://ollama.com/) with the configured model available locally.
- A microphone and audio output device.
- Tesseract OCR is optional. It is only needed for OCR functionality.

## Setup

1. Install Python 3.11 and [Ollama](https://ollama.com/).
2. Pull the model configured in `config.py`:

   ```powershell
   ollama pull qwen3.5:4b
   ```

3. Create and activate a virtual environment:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install Python dependencies:

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. Download the configured Piper voice into the local `voices/` directory:

   ```powershell
   python -m piper.download_voices --data-dir voices ru_RU-dmitri-medium
   ```

6. Start Ollama, then run Jarvis:

   ```powershell
   python main.py
   ```

On first launch, Faster-Whisper and OpenWakeWord may download their model files. These assets are stored locally by their respective libraries.

## Configuration

Edit `config.py` to change the Ollama model, audio parameters, wake-word threshold, recording limits, screenshot size, and local directories.

For OCR, install Tesseract separately and make sure the Russian language data is installed. Set `TESSERACT_CMD` in `config.py` only when Tesseract is not available through the system PATH.

## Safety and privacy

- The language model is accessed through a local Ollama instance; no hosted LLM API key is required by the current code.
- First-run model downloads require an internet connection.
- Jarvis can inspect screenshots, read the clipboard, access files, type text, and control the mouse and keyboard. Run it only in a Windows session where you understand and trust those permissions.
- Shutdown, restart, process termination, and application closing use an explicit confirmation flow.
- Memory files, downloaded voice models, Python bytecode, virtual environments, and IDE settings are local runtime/development data and are excluded from version control.

## Development notes

The repository currently contains a manual vision diagnostic script: `python debug_vision.py`. It opens Notepad and captures screenshots, so run it only when that behavior is appropriate.

Automated tests and a packaged installer are not currently included.
