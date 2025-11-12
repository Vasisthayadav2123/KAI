import time
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, RTCConfiguration, RTCIceServer
from av import VideoFrame
from flask import Flask ,render_template, request, jsonify
import subprocess
import sys
import asyncio
import os
import json
import numpy as np
import pyautogui
from kai import process_text_command, transcribe_audio
import threading
import ffmpeg
import cv2
import mss





# Create an instance of the Flask class
app = Flask(__name__)


#FUNTIONS

#Running Kai script
def run_kai_script():
    try:
        result = subprocess.Popen([sys.executable, 'kai.py'],)
        return f'KAI script executed successfully. Output: {result.stdout}' 
        
    except subprocess.CalledProcessError as e:
        return f'Error executing KAI script: {e.stderr}'

#screenCapture function
def generate_frames():
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Capture the primary monitor
        while True:
            img = sct.grab(monitor)
            frame = cv2.cvtColor(np.array(img), cv2.COLOR_BGRA2BGR)
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.01) #~20 FPS 


class ScreenTrack(VideoStreamTrack):
    """A video track that continuously captures your screen."""
    def __init__(self):
        super().__init__()
        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1]

    async def recv(self):
        img = np.array(self.sct.grab(self.monitor))
        frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts, video_frame.time_base = self.next_timestamp()
        await asyncio.sleep(1 / 30)  # ~30 FPS
        return video_frame



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

@app.route('/control', methods=['POST'])
def control():
    action = request.json.get('action')
    
    if action == 'playpause':
        pyautogui.press('playpause')
    elif action == 'next':
        pyautogui.press('nexttrack')
    elif action == 'previous':
        pyautogui.press('prevtrack')
    elif action == 'volumeup':
        pyautogui.press('volumeup')
    elif action == 'volumedown':
        pyautogui.press('volumedown')
    else:
        return jsonify({'status': 'error', 'message': 'Unknown action'}), 400
    
    return jsonify({'status': 'ok', 'action': action})



# Define a route and a view function
@app.route('/')
def hello_world():
    return render_template('index.html')

@app.route('/stream')
def stream():
    return render_template('stream.html')

@app.route("/offer", methods=["POST"])
async def offer():
    params = request.get_json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection(RTCConfiguration(
        iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]
    ))

    # create a transceiver that is explicitly sendonly (server -> client video)
    transceiver = pc.addTransceiver(kind="video", direction="sendonly")

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print("Connection state:", pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()

    # set remote description from client offer
    await pc.setRemoteDescription(offer)

    # attach the screen track to the transceiver's sender
    # replace_track is synchronous in aiortc; pass an instance of your track
    transceiver.sender.replace_track(ScreenTrack())

    # create and set local answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return jsonify({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })


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




@app.route('/run_kai')
def run_kai():
    #running script execution in a separate thread
    threading.Thread(target=run_kai_script).start()
    return 'KAI script is runnning in the background.'


@app.route('/video_feed')
def video_feed():
    return app.response_class(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    
    
@app.route('/sleep')
def sleep():
    try:
        result = subprocess.Popen([sys.executable, 'sleep.py'],)
        return f'Sleep script executed successfully. Output: {result.stdout}' 
        
    except subprocess.CalledProcessError as e:
        return f'Error executing Sleep script: {e.stderr}'
    
if __name__ == '__main__':
    app.run(debug=True)