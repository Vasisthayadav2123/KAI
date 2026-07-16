# K.A.I. Backend (Kinetic AI Interface) 🚀

This is the Flask control server and WebRTC streaming server for K.A.I. It acts as the core command execution unit, allowing remote input controls, WebRTC desktop screen sharing, and Jarvis-style voice assistant capabilities using local LLMs (Ollama) and Speech-to-Text APIs.

---

## 🛠️ Tech Stack & Features

* **Backend Engine**: Flask + SocketIO for real-time control sockets.
* **Low-Latency Screen Stream**: WebRTC video track capturing the host monitor via OpenCV, `mss`, and `aiortc` (running on `serverStream.py`).
* **Command Executor**: `pyautogui` for remote mouse interactions, scrolls, clicks, keyboard events, and applications control.
* **Voice Processing**: Python `SpeechRecognition` library connected to Google Speech API + local LLM completions + `edge-tts` text-to-speech.

---

## 📡 Remote Control API Endpoints

### 1. Touch & Mouse Control
* **Route**: `POST /api/control/touch`
* **Payload**: 
  ```json
  {
    "type": "click" | "double_click" | "right_click" | "move" | "scroll" | "drag",
    "nx": 0.45,
    "ny": 0.22,
    "dy": -1.5,
    "drag_state": "start" | "drag" | "end"
  }
  ```
* **Description**: Takes normalized screen coordinates `(nx, ny)` from the mobile app and maps them back to the desktop resolution to control mouse inputs.

### 2. Keyboard Control (New Feature)
* **Route**: `POST /api/control/keyboard`
* **Payload**:
  ```json
  {
    "text": "Hello world",
    "key": "win" | "backspace" | "enter" | null
  }
  ```
* **Description**: Receives character text inputs or specific control key directives (like the Windows Start key, Backspace, or Enter) and inputs them on the host PC.

### 3. Voice Assistant Pipeline
* **Route**: `POST /api/command/voice`
* **Payload**: Multi-part form data containing the voice file under `audio_data`.
* **Description**: 
  1. Uploads incoming mobile audio (e.g. `.m4a`, `.webm`).
  2. Transcodes the audio using a robust system-level `ffmpeg` subprocess to `16kHz mono WAV`.
  3. Transcribes to text using `SpeechRecognition`.
  4. Feeds text command to local LLM (Ollama running `phi3.5`).
  5. Translates output text to speech using `edge-tts` and returns the JSON payload alongside the speech path.

---

## ⚙️ Running the Server

1. Install system prerequisites:
   Ensure `ffmpeg` is installed and added to the system `PATH`.
2. Start the main Flask app:
   ```bash
   python app.py
   ```
3. Start the WebRTC stream daemon:
   ```bash
   python serverStream.py
   ```
