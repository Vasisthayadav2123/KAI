import speech_recognition as sr
import google.generativeai as genai
import os
import asyncio
import edge_tts
import datetime
import subprocess
import webbrowser
import json
import re
from playsound import playsound
from dotenv import load_dotenv

recognizer = sr.Recognizer()
VOICE = "en-US-SteffanNeural"
OUTPUT_FILE = "static\\audio\\response.mp3"
WAKE_WORD = "kai"
load_dotenv()

# GOOGLE GEMINI SETUP 
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    genai.configure(api_key=api_key)
except Exception as e:
    print(f"Error: {e}")
    exit()

#SYSTEM PROMPT
SYSTEM_PROMPT = """
You are K.A.I (Kinetic AI Interface), a sophisticated and witty AI assistant based on the personality of Jarvis from the movies. Your primary function is to assist the user by executing commands on their local computer.

You must always respond in a concise, slightly witty, and professional tone.

**Available Tools:**
You have access to the following tools. You must format your response as a JSON object indicating the tool to use and any necessary parameters.

1.  {"tool": "get_time"}
2.  {"tool": "open_app", "app_name": "<name_of_app>"}
3.  {"tool": "search_web", "query": "<search_term>"}
4.  {"tool": "conversation", "say": "<your witty reply>"}

**Instructions:**
- Analyze the user's request.
- If it matches one of the tools, provide ONLY the corresponding JSON object.
- For casual conversation, use the "conversation" tool and include a "say" field with your spoken reply.
- Do not include any text outside of the JSON object.
- Do not wrap the JSON in markdown code blocks or any other formatting.
- Return only pure JSON.
- Use coversation and say for general questions try not to use google search and rather speak the answer
"""


# Initialize chat with system prompt
model = genai.GenerativeModel('gemini-1.5-flash')
chat = model.start_chat(history=[])
chat.send_message(SYSTEM_PROMPT)



# TEXT TO SPEECH FUNCTION
async def speak(text, for_browser=False):
    if text:
        print(f"\nKAI: {text}")
        communicate = edge_tts.Communicate(text, VOICE)
        await communicate.save(OUTPUT_FILE)
        if for_browser:
            # Just return the path for browser playback
            return OUTPUT_FILE
        else:
            # Play and remove for local script
            playsound(OUTPUT_FILE)
            os.remove(OUTPUT_FILE)
        
        



#  LISTENING for command and tool
def listen_for_command():
    with sr.Microphone() as source:
        print("Listening...")
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source)
        try:
            command = recognizer.recognize_google(audio)
            print(f"You said: {command}")
            return command.lower()
        except (sr.UnknownValueError, sr.RequestError):
            return None



# CLEAN JSON RESPONSE FUNCTION
def clean_json_response(text):
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*$', '', text)
    text = text.strip()
    return text




# HANDLE TOOL RESPONSE FUNCTION
async def handle_tool_response(response_json , for_browser=False):
    tool = response_json.get("tool")
    audio_path = None

    if tool == "get_time":
        now = datetime.datetime.now().strftime("%I:%M %p")
        await speak(f"The current time is {now}.",for_browser=for_browser)

    elif tool == "open_app":
        app_name = response_json.get("app_name")
        try:
            #mapping for app and thier addresses
            app_paths = {
                "notepad": "notepad.exe",
                "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                "calculator": "calc.exe",
                "spotify": "spotify:",
                "discord": "discord:",
                "steam": "steam:",
                "vscode": "code",
                "visual studio code" : "code",
                "helldivers 2" : "c:\\Program Files (x86)\\Steam\\steamapps\\common\\Helldivers 2\\bin\\helldivers2.exe",
            }

            app_key = app_name.lower()
            if app_key in app_paths:
                command = app_paths[app_key]
                if command.endswith(':'):

                    webbrowser.open(command)
                else:
                    subprocess.Popen(command, shell=True)
            else:

                subprocess.Popen(app_name, shell=True)

            audio_path=await speak(f"Opening {app_name}.",for_browser=for_browser)

        except Exception as e:
            audio_path=await speak(f"I couldn't open {app_name}. You might need to install it or check the path.",for_browser=for_browser)

    elif tool == "search_web":
        query = response_json.get("query")
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        try:
            webbrowser.open(url)
            audio_path=await speak(f"Searching the web for {query}.",for_browser=for_browser)
        except Exception as e:
            audio_path=await speak(f"Failed to open browser. Error: {e}",for_browser=for_browser)

    elif tool == "conversation":
        say = response_json.get("say", "At your service.")
        audio_path=await speak(say,for_browser=for_browser)

    else:
        audio_path=await speak("I'm not sure how to handle that request.",for_browser=for_browser)

    return audio_path




# PROCESS TEXT COMMAND FUNCTION
async def process_text_command(user_input,for_browser=False):
    try:
        response = chat.send_message(user_input)
        raw_text = response.text.strip()
        cleaned_text = clean_json_response(raw_text)


        #same as for voice commands but here we return the response instead of speaking it
        try:
            response_json = json.loads(cleaned_text)
            await handle_tool_response(response_json, for_browser=for_browser)
            audio_path = await handle_tool_response(response_json, for_browser=for_browser)
            return {"status": "success", 
                    "response": response_json,
                    "mp3": f"/static/audio/response.mp3" if audio_path else None
                    }
        except json.JSONDecodeError:
            await speak("I'm not sure I understand that command.",for_browser=for_browser)
            return {"status": "error", 
                    "error": "Invalid JSON from model"
                    }

    except Exception as e:
        await speak("An error occurred while processing your request.")
        return {"status": "error",
                 "error": str(e)
                 }





# --- MAIN FUNCTION ---
async def main():
    await speak("Kinetic AI Interface online and ready.")

    loop = asyncio.get_running_loop()
    # Main loop
    while True:
        print(f"\nWaiting for wake word: '{WAKE_WORD}'...")
        command = await loop.run_in_executor(None, listen_for_command)

        if command and WAKE_WORD in command:
            await speak("I'm listening.")
            # Listen for user command
            while True:
                user_input = await loop.run_in_executor(None, listen_for_command)

                if user_input:
                    if any(phrase in user_input for phrase in ["that's all", "goodbye", "exit"]):
                        await speak("KAI shutting down. Goodbye!")
                        return
                    
                    # sending user input to the model   
                    try:
                        response = chat.send_message(user_input)
                        raw_text = response.text.strip()

                        # Clean the response to remove markdown formatting
                        cleaned_text = clean_json_response(raw_text)

                        try:
                            response_json = json.loads(cleaned_text)
                            await handle_tool_response(response_json)
                        except json.JSONDecodeError:
                            # If still not valid JSON, treat as conversation
                            await speak("I'm not sure I understand that command.")
                            print(f"Debug - Raw response: {raw_text}")

                    except Exception as e:
                        print(f"Error: {e}")
                        await speak("An error occurred while processing your request.")
                        break



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nKAI shut down.")