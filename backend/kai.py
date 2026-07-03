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
MODEL_NAME = "gemma4:e4b" 

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

async def query_openclaw(user_input):
    """Bridge to the local OpenClaw gateway."""
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are K.A.I (Kinetic AI Interface), a witty AI assistant like Jarvis. Use your skills to control the local system. Be concise and professional."},
            {"role": "user", "content": user_input}
        ],
        "stream": False
    }
    try:
        # OpenClaw automatically triggers skills (system-control, etc.) 
        # if the prompt requires it before returning this text.
        response = requests.post(OPENCLAW_URL, json=payload, timeout=45)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
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