from flask import Flask ,render_template, request, jsonify
import subprocess
import sys
import asyncio
import os
import json
from kai import process_text_command, transcribe_audio
import threading
import ffmpeg;

# Create an instance of the Flask class
app = Flask(__name__)



def run_kai_script():
    try:
        result = subprocess.Popen([sys.executable, 'kai.py'],)
        return f'KAI script executed successfully. Output: {result.stdout}' 
        
    except subprocess.CalledProcessError as e:
        return f'Error executing KAI script: {e.stderr}'
    





# Define a route and a view function
@app.route('/')
def hello_world():
    return render_template('index.html')


## handling text input from broser
@app.route('/process',methods=['POST'])
def process_command():
    data = request.get_json()
    user_input= data.get('command')
    print(user_input)
    loop=asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result=loop.run_until_complete(process_text_command(user_input, for_browser=True))
    return jsonify(result)





## removing audio file after playing it in browser
@app.route('/delete_audio', methods=['POST'])
def delete_audio():
    try:
        os.remove("static\\audio\\response.mp3")
        os.remove("static\\audio\\userinputs\\user_command_audio.wav")
        return "Audio file deleted successfully."
    except FileNotFoundError:
        return "Audio file not found."
    except Exception as e:
        return f"An error occurred: {str(e)}"


## receiving audio data from browser and converting it to text
@app.route('/send_audio', methods=['POST'])
def audio_convert():
    blob = request.files['audio_data']
    target_dir = 'static/audio/userinputs'
    os.makedirs(target_dir, exist_ok=True)  # Create the folder if it doesn't exist
    file_path = os.path.join(target_dir, 'user_command_audio.webm')
    blob.save(file_path)
    audio_convert_mp3(file_path)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(transcribe_audio('static/audio/userinputs/user_command_audio.wav'))
    return jsonify(result)


## @app.route('/convert_audio', methods=['POST'])
def audio_convert_mp3(input_path):
    input_path = 'static/audio/userinputs/user_command_audio.webm'
    output_path = 'static/audio/userinputs/user_command_audio.wav'
    
    try:
        (
            ffmpeg
            .input(input_path)
            .output(output_path, format='wav', acodec='pcm_s16le', ac=1, ar='16000')
            .run(overwrite_output=True)
        )
        os.remove(input_path)  # Remove the original webm file after conversion
        return jsonify({"status":"success", "message":"Audio converted to mp3 successfully."})
    except ffmpeg.Error as e:
        return jsonify({"status":"error", "message":f"Error converting audio: {e.stderr.decode()}"})

@app.route('/run_kai')
def run_kai():
    #running script execution in a separate thread
    threading.Thread(target=run_kai_script).start()
    return 'KAI script is runnning in the background.'
    
@app.route('/sleep')
def sleep():
    try:
        result = subprocess.Popen([sys.executable, 'sleep.py'],)
        return f'Sleep script executed successfully. Output: {result.stdout}' 
        
    except subprocess.CalledProcessError as e:
        return f'Error executing Sleep script: {e.stderr}'
    
if __name__ == '__main__':
    app.run(debug=True)