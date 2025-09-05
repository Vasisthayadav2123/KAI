import speech_recognition as sr
import google.generativeai as genai
import os
import asyncio
import edge_tts
from playsound import playsound


recognizer = sr.Recognizer()

try:
    api_key = os.getenv("GOOGLE_API_KEY")
    genai.configure(api_key=api_key)
except Exception as e:
    print(f"Error: {e}")
    exit()

model = genai.GenerativeModel('gemini-1.5-flash')
chat = model.start_chat(history=[])


VOICE = "en-US-SteffanNeural"
OUTPUT_FILE = "response.mp3"

async def speak(text):

    if text:
        print(f" ~\n KAI (speaking): {text}")
        communicate = edge_tts.Communicate(text, VOICE)
        await communicate.save(OUTPUT_FILE)
        playsound(OUTPUT_FILE)
        os.remove(OUTPUT_FILE)


def listen_for_command():
    # run this using an executer because ot is a syncronous funtion and bloacking action and rescources
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


async def main():
 # main funtion that keeps the voice assistant running and listening for wake command
    wake_word = "kai"
    await speak("Kinetic AI interface online and ready.")

    loop = asyncio.get_running_loop()

    while True:
        print(f"\nWaiting for wake word: '{wake_word}'...")
        
        command = await loop.run_in_executor(None, listen_for_command)

        if command and wake_word in command:
            await speak("I'm listening.")

            while True:
                user_input = await loop.run_in_executor(None, listen_for_command)

                if user_input:
                    if any(phrase in user_input for phrase in ["that's all", "goodbye", "exit"]):
                        await speak("Goodbye!")
                        break

                    try:
                        response_stream = chat.send_message(user_input, stream=True)
                        full_response = "".join(chunk.text for chunk in response_stream)
                        await speak(full_response)
                    except Exception as e:
                        print(f"An error occurred: {e}")
                        await speak("Sorry, there was an error.")
                        break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(" \n Assistant shut down.")