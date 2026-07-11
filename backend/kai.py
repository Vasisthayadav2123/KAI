import speech_recognition as sr
import os
import asyncio
import edge_tts
import json
import requests
from playsound import playsound
from dotenv import load_dotenv

# --- CONFIGURATION ---
recognizer = sr.Recognizer()
VOICE = "en-US-SteffanNeural"
OUTPUT_FILE = os.path.join("static", "audio", "response.mp3")
WAKE_WORD = "kai"

# OpenClaw Settings (Default port 18789)
OPENCLAW_URL = "http://localhost:18789/v1/chat/completions"
OLLAMA_DIRECT_URL = "http://localhost:11434/v1/chat/completions"
MODEL_NAME = "gemma4:e4b" 

# Keep-alive duration: model stays in VRAM for this long after the last request
KEEP_ALIVE = "10m"

load_dotenv()

async def speak(text, for_browser=False):
    """Handles Jarvis-style TTS."""
    if text:
        print(f"\nKAI: {text}")
        communicate = edge_tts.Communicate(text, VOICE)
        await communicate.save(OUTPUT_FILE)
        if for_browser:
            return OUTPUT_FILE
        else:
            playsound(OUTPUT_FILE)
            if os.path.exists(OUTPUT_FILE):
                os.remove(OUTPUT_FILE)

def listen_for_command():
    """Listens for the wake word or user input via Microphone."""
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
            return recognizer.recognize_google(audio).lower()
        except:
            return None


# ── LLM Lifecycle Management ─────────────────────────────────────

def warmup_model():
    """Pre-load the LLM into GPU VRAM. Called after handshake.
    Sends a minimal 1-token request to force Ollama to load model weights."""
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": "hi"}
        ],
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "num_predict": 1  # Generate only 1 token — just enough to trigger loading
        }
    }
    try:
        print("[KAI] Warming up model — loading into VRAM...")
        # Try OpenClaw first (so its skills/tools get initialized too)
        response = requests.post(OPENCLAW_URL, json=payload, timeout=(5, 120))
        if response.status_code == 200:
            print("[KAI] Model warmed up successfully via OpenClaw — VRAM loaded.")
            return True
        else:
            print(f"[KAI] OpenClaw warm-up returned status {response.status_code}, trying Ollama direct...")
    except requests.exceptions.ConnectionError:
        print("[KAI] OpenClaw unreachable for warm-up, trying Ollama direct...")
    except Exception as e:
        print(f"[KAI] OpenClaw warm-up error: {e}, trying Ollama direct...")

    # Fallback: warm up via Ollama directly
    try:
        response = requests.post(OLLAMA_DIRECT_URL, json=payload, timeout=(5, 120))
        if response.status_code == 200:
            print("[KAI] Model warmed up successfully via Ollama direct — VRAM loaded.")
            return True
        else:
            print(f"[KAI] Ollama direct warm-up returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"[KAI] Ollama direct warm-up also failed: {e}")
        return False


def unload_model():
    """Immediately unload the LLM from GPU VRAM to free resources.
    Sends keep_alive=0 to tell Ollama to release the model now."""
    try:
        payload = {
            "model": MODEL_NAME,
            "keep_alive": "0"
        }
        print("[KAI] Unloading model from VRAM...")
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=5)
        if response.status_code == 200:
            print("[KAI] Model unloaded — VRAM freed.")
            return True
        else:
            print(f"[KAI] Unload returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"[KAI] Failed to unload model: {e}")
        return False


def get_ai_status():
    """Check the health of Ollama and OpenClaw. Returns a status dict."""
    status = {
        "ollama": {"reachable": False, "model_loaded": False},
        "openclaw": {"reachable": False}
    }

    # Check Ollama
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            status["ollama"]["reachable"] = True
            models = r.json().get("models", [])
            for m in models:
                if MODEL_NAME in m.get("name", ""):
                    status["ollama"]["model_loaded"] = True
                    status["ollama"]["model_name"] = m.get("name")
                    status["ollama"]["size_gb"] = round(m.get("size", 0) / (1024**3), 1)
    except Exception:
        pass

    # Check OpenClaw
    try:
        r = requests.get("http://localhost:18789/v1/models", timeout=3)
        status["openclaw"]["reachable"] = r.status_code == 200
    except Exception:
        pass

    # Check if model is currently loaded in memory via Ollama ps
    try:
        r = requests.get("http://localhost:11434/api/ps", timeout=3)
        if r.status_code == 200:
            running = r.json().get("models", [])
            for m in running:
                if MODEL_NAME in m.get("name", ""):
                    status["ollama"]["model_running"] = True
                    status["ollama"]["vram_used"] = m.get("size", 0)
                    expires = m.get("expires_at", "")
                    status["ollama"]["expires_at"] = expires
    except Exception:
        pass

    # Overall verdict
    if status["ollama"]["reachable"] and status["openclaw"]["reachable"]:
        status["overall"] = "ALL_SYSTEMS_GO"
    elif status["ollama"]["reachable"]:
        status["overall"] = "OPENCLAW_DOWN"
    else:
        status["overall"] = "OLLAMA_DOWN"

    return status


# ── Core AI Query ─────────────────────────────────────────────────

async def query_openclaw(user_input):
    """Bridge to the local OpenClaw gateway with Ollama fallback."""
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are K.A.I (Kinetic AI Interface), a witty AI assistant like Jarvis. Use your skills to control the local system. Be concise and professional."},
            {"role": "user", "content": user_input}
        ],
        "stream": False,
        "keep_alive": KEEP_ALIVE
    }
    try:
        # OpenClaw automatically triggers skills (system-control, etc.) 
        # if the prompt requires it before returning this text.
        response = requests.post(OPENCLAW_URL, json=payload, timeout=(5, 120))
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except requests.exceptions.ConnectionError:
        # OpenClaw is down — try Ollama directly (without agentic skills)
        print("[KAI] OpenClaw unreachable. Falling back to Ollama direct.")
        try:
            response = requests.post(OLLAMA_DIRECT_URL, json=payload, timeout=(5, 120))
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content']
        except Exception as e:
            print(f"[KAI] Ollama direct also failed: {e}")
            return "Both OpenClaw and Ollama are unreachable, sir. Check if the services are running."
    except Exception as e:
        print(f"Core Error: {e}")
        return "I'm having trouble connecting to the local core, sir."

async def process_text_command(user_input, for_browser=False):
    """Used by both the local loop and the Flask API."""
    reply = await query_openclaw(user_input)
    audio_path = await speak(reply, for_browser=for_browser)
    return {
        "status": "success",
        "response": {"tool": "conversation", "say": reply},
        "mp3": "/static/audio/response.mp3" if audio_path else None
    }

async def transcribe_audio(file_path):
    """Converts recorded browser audio (.wav) to text."""
    with sr.AudioFile(file_path) as source:
        audio = recognizer.record(source)
    try:
        text = recognizer.recognize_google(audio)
        return await process_text_command(text, for_browser=True)
    except Exception as e:
        return {"status": "error", "message": f"Transcription failed: {str(e)}"}

async def main():
    await speak("Kinetic AI Interface online. All local systems nominal.")
    loop = asyncio.get_running_loop()
    while True:
        command = await loop.run_in_executor(None, listen_for_command)
        if command and WAKE_WORD in command:
            await speak("Yes, sir?")
            user_input = await loop.run_in_executor(None, listen_for_command)
            if user_input:
                if any(p in user_input for p in ["shutdown", "exit"]):
                    await speak("KAI shutting down.")
                    break
                await process_text_command(user_input)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Manual exit.")