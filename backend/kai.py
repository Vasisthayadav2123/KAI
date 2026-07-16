import speech_recognition as sr
import os
import asyncio
import edge_tts
import json
import requests
import re
from playsound import playsound
import time
from dotenv import load_dotenv
from command_executor import execute_command_internal

# --- CONFIGURATION ---
recognizer = sr.Recognizer()
VOICE = "en-US-SteffanNeural"
OUTPUT_FILE = os.path.join("static", "audio", "response.mp3")
WAKE_WORD = "kai"

OLLAMA_DIRECT_URL = "http://localhost:11434/v1/chat/completions"
MODEL_NAME = "phi3.5:latest" 

# Keep-alive duration: model stays in VRAM for this long after the last request
KEEP_ALIVE = "10m"

load_dotenv()

# --- SYSTEM PROMPT FOR LOCAL CONTROLS ---
KAI_SYSTEM_PROMPT = """Your name is K.A.I (Kinetic AI Interface). You are a witty, extremely concise AI assistant like Jarvis.
NEVER call yourself "Phi", "Friendly Interface", or anything else. Always identify as K.A.I.
Keep all responses extremely short, concise, and under 2 sentences.

Only use tools if the user explicitly asks you to open an app, adjust volume, control media, or take a screenshot.
If the user asks a question or says a greeting, reply in plain text under 2 sentences without any tool prefixes.

Available tools:
- app.open | {"app": "spotify" | "browser" | "vscode" | "explorer" | "notepad" | "discord" | "helldivers2" | "apexlegends"}
- media.playpause
- media.next
- media.previous
- media.volumeup
- media.volumedown
- media.mute
- audio.change_volume | {"direction": "up" | "down", "steps": <integer>}
- display.screenshot
- system.diagnostics | {}

Examples:
- User: "open spotify" -> [TOOL: app.open | {"app": "spotify"}] Opening Spotify, sir.
- User: "turn up the volume by 5 steps" -> [TOOL: audio.change_volume | {"direction": "up", "steps": 5}] Adjusting the volume, sir.
- User: "take a screenshot" -> [TOOL: display.screenshot | {}] Capturing your screen now, sir.
- User: "how is the server doing?" -> [TOOL: system.diagnostics | {}] checking system health."""

# --- OPENCLAW DYNAMIC CONFIGURATION ---
def load_openclaw_config():
    """Loads OpenClaw configuration dynamically from the user's home folder."""
    config_path = os.path.expanduser(r"~/.openclaw/openclaw.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[KAI] Failed to read OpenClaw config: {e}")
    return {}

def get_openclaw_info():
    """Resolves correct URL, base models URL, and auth headers dynamically."""
    config = load_openclaw_config()
    gateway = config.get("gateway", {})
    port = gateway.get("port", 18789)
    bind = gateway.get("bind", "localhost")
    if bind == "loopback":
        bind = "localhost"
        
    completions_url = f"http://{bind}:{port}/v1/chat/completions"
    models_url = f"http://{bind}:{port}/v1/models"
    headers = {}
    
    auth = gateway.get("auth", {})
    if auth.get("mode") == "token" and auth.get("token"):
        headers["Authorization"] = f"Bearer {auth.get('token')}"
        
    return completions_url, models_url, headers

async def speak(text, for_browser=False, output_file=None):
    """Handles Jarvis-style TTS."""
    if text:
        print(f"\nKAI: {text}")
        communicate = edge_tts.Communicate(text, VOICE)
        file_to_save = output_file if output_file else OUTPUT_FILE
        await communicate.save(file_to_save)
        if for_browser:
            return file_to_save
        else:
            playsound(file_to_save)
            if os.path.exists(file_to_save):
                os.remove(file_to_save)

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
    # Warm up via Ollama directly
    try:
        print("[KAI] Warming up model — loading into VRAM via Ollama direct...")
        response = requests.post(OLLAMA_DIRECT_URL, json=payload, timeout=(5, 120))
        if response.status_code == 200:
            print("[KAI] Model warmed up successfully via Ollama direct — VRAM loaded.")
            return True
        else:
            print(f"[KAI] Ollama direct warm-up returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"[KAI] Ollama direct warm-up failed: {e}")
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

    # OpenClaw is disabled
    status["openclaw"]["reachable"] = False

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

    # Overall verdict (OpenClaw bypassed)
    if status["ollama"]["reachable"]:
        status["overall"] = "ALL_SYSTEMS_GO"
    else:
        status["overall"] = "OLLAMA_DOWN"

    return status


# ── Core AI Query ─────────────────────────────────────────────────

async def query_openclaw(user_input):
    """Bridge to Ollama directly (OpenClaw has been bypassed)."""
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": KAI_SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ],
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "temperature": 0.0,
        "max_tokens": 100,
        "stop": ["\n\n", "---", "<|user|>", "<|system|>", "\n- User:"]
    }
    try:
        # Query Ollama directly
        t0 = time.time()
        response = requests.post(OLLAMA_DIRECT_URL, json=payload, timeout=(5, 120))
        response.raise_for_status()
        reply = response.json()['choices'][0]['message']['content']
        
        latency = round((time.time() - t0) * 1000, 1)
        try:
            import diagnostics
            diagnostics.set_last_latency(latency)
        except Exception:
            pass
        
        # Parse potential tool execution instructions
        tool_match = re.search(r'\[TOOL:\s*([a-zA-Z0-9\._\-]+)\s*\|\s*({.*?})\s*\]', reply, re.DOTALL)
        if tool_match:
            tool_name = tool_match.group(1)
            payload_str = tool_match.group(2)
            
            # Clean up the output text to exclude the tool bracket markup
            reply = re.sub(r'\[TOOL:\s*([a-zA-Z0-9\._\-]+)\s*\|\s*({.*?})\s*\]', '', reply).strip()
            
            try:
                tool_payload = json.loads(payload_str)
                success, msg = execute_command_internal(tool_name, tool_payload)
                print(f"[KAI] Executed tool '{tool_name}' with payload '{tool_payload}': success={success}, msg={msg}")
                
                # Special handling for system.diagnostics to do a second pass:
                if tool_name == "system.diagnostics" and success:
                    second_pass_prompt = (
                        f"Here are the current diagnostics: {json.dumps(msg)}. "
                        "Summarize them concisely for the user, highlighting key stats (CPU, RAM, GPU, internet/ping/TTS status) "
                        "and mentioning any abnormal metrics."
                    )
                    payload_2 = {
                        "model": MODEL_NAME,
                        "messages": [
                            {"role": "system", "content": KAI_SYSTEM_PROMPT},
                            {"role": "user", "content": user_input},
                            {"role": "assistant", "content": f"[TOOL: system.diagnostics | {payload_str}]"},
                            {"role": "system", "content": second_pass_prompt}
                        ],
                        "stream": False,
                        "keep_alive": KEEP_ALIVE,
                        "temperature": 0.2,
                        "max_tokens": 150,
                        "stop": ["\n\n", "---", "<|user|>", "<|system|>", "\n- User:"]
                    }
                    t0_2 = time.time()
                    response_2 = requests.post(OLLAMA_DIRECT_URL, json=payload_2, timeout=(5, 120))
                    response_2.raise_for_status()
                    reply = response_2.json()['choices'][0]['message']['content'].strip()
                    
                    latency_2 = round((time.time() - t0_2) * 1000, 1)
                    try:
                        diagnostics.set_last_latency(latency_2)
                    except Exception:
                        pass
            except Exception as parse_err:
                print(f"[KAI] Failed to parse tool payload or execute: {parse_err}")
                
        return reply
    except Exception as e:
        print(f"[KAI] Ollama query failed: {e}")
        return "I'm having trouble connecting to Ollama, sir. Check if the service is running."

async def stream_query_openclaw(user_input):
    """Streams response from Ollama directly, yielding sentence chunks."""
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": KAI_SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ],
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "temperature": 0.0,
            "num_predict": 100,
            "stop": ["\n\n", "---", "<|user|>", "<|system|>", "\n- User:"]
        }
    }
    
    loop = asyncio.get_running_loop()
    
    def get_stream(p):
        return requests.post("http://localhost:11434/api/chat", json=p, stream=True, timeout=(5, 120))

    try:
        t0 = time.time()
        response = await loop.run_in_executor(None, get_stream, payload)
        response.raise_for_status()
        
        buffer = ""
        tool_executed = False
        sentence_delimiters = re.compile(r'[.!?:]')
        
        is_diagnostics = False
        diagnostics_payload_str = None
        diagnostics_data = None
        
        for line in response.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line.decode('utf-8'))
                content = data.get('message', {}).get('content', '')
                if content:
                    buffer += content
                    
                    if not tool_executed:
                        if '[' in buffer:
                            if ']' in buffer:
                                tool_match = re.search(r'\[TOOL:\s*([a-zA-Z0-9\._\-]+)\s*\|\s*({.*?})\s*\]', buffer, re.DOTALL)
                                if tool_match:
                                    tool_name = tool_match.group(1)
                                    payload_str = tool_match.group(2)
                                    buffer = re.sub(r'\[TOOL:\s*([a-zA-Z0-9\._\-]+)\s*\|\s*({.*?})\s*\]', '', buffer).strip()
                                    tool_executed = True
                                    
                                    try:
                                        tool_payload = json.loads(payload_str)
                                        success, msg = execute_command_internal(tool_name, tool_payload)
                                        print(f"[KAI] Stream-executed tool '{tool_name}' with payload '{tool_payload}': success={success}, msg={msg}")
                                        if tool_name == "system.diagnostics" and success:
                                            is_diagnostics = True
                                            diagnostics_payload_str = payload_str
                                            diagnostics_data = msg
                                            break
                                    except Exception as parse_err:
                                        print(f"[KAI] Failed to parse tool payload or execute: {parse_err}")
                                else:
                                    if len(buffer) > 200:
                                        tool_executed = True
                        else:
                            tool_executed = True
                    
                    if tool_executed and not is_diagnostics:
                        matches = list(sentence_delimiters.finditer(buffer))
                        if matches:
                            split_idx = matches[-1].end()
                            sentence = buffer[:split_idx]
                            buffer = buffer[split_idx:]
                            if sentence.strip():
                                yield sentence.strip()
            except Exception as e:
                print(f"[KAI] Stream parsing error: {e}")
                
        # If diagnostics tool was triggered, perform second pass streaming
        if is_diagnostics:
            second_pass_prompt = (
                f"Here are the current diagnostics: {json.dumps(diagnostics_data)}. "
                "Summarize them concisely for the user, highlighting key stats (CPU, RAM, GPU, internet/ping/TTS status) "
                "and mentioning any abnormal metrics."
            )
            payload_2 = {
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": KAI_SYSTEM_PROMPT},
                    {"role": "user", "content": user_input},
                    {"role": "assistant", "content": f"[TOOL: system.diagnostics | {diagnostics_payload_str}]"},
                    {"role": "system", "content": second_pass_prompt}
                ],
                "stream": True,
                "keep_alive": KEEP_ALIVE,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 150,
                    "stop": ["\n\n", "---", "<|user|>", "<|system|>", "\n- User:"]
                }
            }
            
            t0_2 = time.time()
            response_2 = await loop.run_in_executor(None, get_stream, payload_2)
            response_2.raise_for_status()
            
            buffer = ""
            for line in response_2.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line.decode('utf-8'))
                    content = data.get('message', {}).get('content', '')
                    if content:
                        buffer += content
                        matches = list(sentence_delimiters.finditer(buffer))
                        if matches:
                            split_idx = matches[-1].end()
                            sentence = buffer[:split_idx]
                            buffer = buffer[split_idx:]
                            if sentence.strip():
                                yield sentence.strip()
                except Exception as e:
                    print(f"[KAI Stream 2nd Pass] Parsing error: {e}")
            if buffer.strip():
                yield buffer.strip()
                
            latency_2 = round((time.time() - t0_2) * 1000, 1)
            try:
                import diagnostics
                diagnostics.set_last_latency(latency_2)
            except Exception:
                pass
        else:
            if buffer.strip():
                yield buffer.strip()
            
            latency = round((time.time() - t0) * 1000, 1)
            try:
                import diagnostics
                diagnostics.set_last_latency(latency)
            except Exception:
                pass
            
    except Exception as e:
        print(f"[KAI] Ollama query failed: {e}")
        yield "I'm having trouble connecting to Ollama, sir."

def only_transcribe(file_path):
    """Transcribes audio file to text, returning the string."""
    with sr.AudioFile(file_path) as source:
        audio = recognizer.record(source)
    return recognizer.recognize_google(audio)

async def process_text_command(user_input, for_browser=False, output_file=None):
    """Used by both the local loop and the Flask API."""
    reply = await query_openclaw(user_input)
    audio_path = await speak(reply, for_browser=for_browser, output_file=output_file)
    web_path = None
    if audio_path:
        web_path = "/" + audio_path.replace("\\", "/").lstrip("/")
    return {
        "status": "success",
        "response": {"tool": "conversation", "say": reply},
        "mp3": web_path if audio_path else None
    }

async def transcribe_audio(file_path, output_file=None):
    """Converts recorded browser audio (.wav) to text."""
    with sr.AudioFile(file_path) as source:
        audio = recognizer.record(source)
    try:
        text = recognizer.recognize_google(audio)
        result = await process_text_command(text, for_browser=True, output_file=output_file)
        result["query"] = text
        return result
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