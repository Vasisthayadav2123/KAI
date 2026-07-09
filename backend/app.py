import time
import random
import secrets

import psutil
from werkzeug.security import generate_password_hash, check_password_hash
from av import VideoFrame
from flask import Flask, redirect ,render_template, request, jsonify, session
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
from flask_cors import CORS
from functools import wraps



# ── Shared Key Table (must match mobile app) ──────────────────────
# The server picks a random key number, the client must reply with the matching secret.
KAI_KEYS = {
    "1": "kai-sec-alpha-87219",
    "2": "kai-sec-beta-39281",
    "3": "kai-sec-gamma-10482",
    "4": "kai-sec-delta-58291",
    "5": "kai-sec-epsilon-74920",
}

# Active session tokens (token -> expiry timestamp)
active_sessions = {}
SESSION_TTL = 3600  # 1 hour


def generate_session_token():
    """Generate a cryptographically secure session token."""
    return secrets.token_hex(32)


def is_valid_session(token):
    """Check if a session token is valid and not expired."""
    if token not in active_sessions:
        return False
    if time.time() > active_sessions[token]:
        del active_sessions[token]
        return False
    return True


def require_auth(f):
    """Decorator: reject requests without a valid session token.
       Exempt routes: /health, /api/handshake/*, /login, /"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        token = auth_header[7:]
        if not is_valid_session(token):
            return jsonify({"error": "Invalid or expired session token"}), 401
        return f(*args, **kwargs)
    return decorated



# Create an instance of the Flask class
app = Flask(__name__)
app.secret_key = '4f8e3c7a9d2b4e8f98cbb1160d912af4912fb32b690efce5accf41bec0f23a80'
CORS(app)  # Allow cross-origin requests from mobile app


USERS = {
    "mobile_user": generate_password_hash("mobilepass"),
    "laptop_user": generate_password_hash("laptoppass")
}

active_logins = {
    "mobile_user": False,
    "laptop_user": False
}



# ── Challenge-Response Handshake ──────────────────────────────────

# Pending challenges: { challenge_id: { key_number, expires } }
pending_challenges = {}

@app.route('/api/handshake/init', methods=['POST'])
def handshake_init():
    """Step 1: Server picks a random key number and sends it to the client."""
    key_number = str(random.choice(list(KAI_KEYS.keys())))
    challenge_id = secrets.token_hex(16)
    
    pending_challenges[challenge_id] = {
        "key_number": key_number,
        "expires": time.time() + 30  # challenge valid for 30 seconds
    }
    
    # Clean up expired challenges
    expired = [cid for cid, c in pending_challenges.items() if time.time() > c["expires"]]
    for cid in expired:
        del pending_challenges[cid]
    
    return jsonify({
        "challenge_id": challenge_id,
        "key_number": key_number
    })


@app.route('/api/handshake/verify', methods=['POST'])
def handshake_verify():
    """Step 2: Client sends back the key matching the challenged key number."""
    data = request.get_json()
    challenge_id = data.get("challenge_id")
    key_number = data.get("key_number")
    key_value = data.get("key")
    
    if not challenge_id or challenge_id not in pending_challenges:
        return jsonify({"error": "Invalid or expired challenge"}), 401
    
    challenge = pending_challenges.pop(challenge_id)
    
    # Check challenge hasn't expired
    if time.time() > challenge["expires"]:
        return jsonify({"error": "Challenge expired"}), 401
    
    # Check key number matches what the server asked for
    if str(key_number) != challenge["key_number"]:
        return jsonify({"error": "Key number mismatch"}), 401
    
    # Check the key value is correct
    expected_key = KAI_KEYS.get(str(key_number))
    if not expected_key or key_value != expected_key:
        return jsonify({"error": "Invalid key"}), 401
    
    # All checks passed — issue a session token
    token = generate_session_token()
    active_sessions[token] = time.time() + SESSION_TTL
    
    print(f"[KAI AUTH] Device authenticated via key #{key_number}. Session granted.")
    
    return jsonify({
        "status": "authenticated",
        "session_token": token,
        "expires_in": SESSION_TTL
    })



#FUNTIONS

#Running Kai script
def run_kai_script():
    try:
        result = subprocess.Popen([sys.executable, 'kai.py'],)
        return f'KAI script executed successfully. Output: {result.stdout}' 
        
    except subprocess.CalledProcessError as e:
        return f'Error executing KAI script: {e.stderr}'

""" #screenCapture function
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


pcs = set()  # keep peer connections alive

class ScreenTrack(VideoStreamTrack):
    
    def __init__(self, monitor_index=1):
        super().__init__()
        self.monitor_index = monitor_index

    async def recv(self):
        # create mss inside the thread where recv runs to avoid thread-local errors
        with mss.mss() as sct:
            monitors = sct.monitors
            monitor = monitors[self.monitor_index] if len(monitors) > self.monitor_index else monitors[0]
            img = np.array(sct.grab(monitor))
        frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts, video_frame.time_base = self.next_timestamp()
        await asyncio.sleep(1 / 30)  # ~30 FPS
        return video_frame
 """

kai_lock = threading.Lock()

last_net_io = psutil.net_io_counters()
last_time = time.time()

def get_network_speed():
    global last_net_io, last_time

    current_net_io = psutil.net_io_counters()
    current_time = time.time()

    interval = current_time - last_time

    bytes_sent = current_net_io.bytes_sent - last_net_io.bytes_sent
    bytes_recv = current_net_io.bytes_recv - last_net_io.bytes_recv

    last_net_io = current_net_io
    last_time = current_time
    
    # Return speed in MB/s (divide by interval to handle varied polling rates)
    return {
        "upload_mbps": round((bytes_sent / (1024 * 1024)) / interval, 2),
        "download_mbps": round((bytes_recv / (1024 * 1024)) / interval, 2)
    }

def get_gpu_stats():
    try:
        result = subprocess.check_output(
            [
                "nvidia-smi", 
                "--query-gpu=utilization.gpu,memory.total,memory.used,temperature.gpu", 
                "--format=csv,noheader,nounits"
            ],
            shell=True,
            timeout=1
        )
        output = result.decode("utf-8").strip()
        gpu_util, mem_total, mem_used, temp = output.split(", ")

        return {
            "load_percent": int(gpu_util),
            "memory_total_mb": int(mem_total),
            "memory_used_mb": int(mem_used),
            "memory_percent": round((int(mem_used) / int(mem_total)) * 100, 1),
            "temperature_c": int(temp)
        }
    except Exception as e:
        # Fallback values if no NVIDIA GPU is found or command fails
        return {
            "load_percent": 0,
            "memory_total_mb": 0,
            "memory_used_mb": 0,
            "memory_percent": 0,
            "temperature_c": 0,
            "error": str(e)
        }

@app.route('/health')
@require_auth
def health():
    net_speed = get_network_speed()
    gpu = get_gpu_stats()

    stats = {
        "version": "v3.1",
        "cpu_usage_percent": psutil.cpu_percent(interval=0.1),
        "memory_usage_percent": psutil.virtual_memory().percent,
        "memory_used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
        "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
        "disk_usage_percent": psutil.disk_usage('/').percent,
        "network_out_mbps": net_speed["upload_mbps"],
        "network_in_mbps": net_speed["download_mbps"],

        "gpu": gpu,
        "nodes": [
            {"id": "Node 01", "status": "ONLINE"},
            {"id": "Node 02", "status": "ONLINE"},
            {"id": "Node 03", "status": "DISTRIBUTING"}
        ]
    }
    return jsonify(stats)

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
        os.remove(input_path)  # Remove the original
        return jsonify({"status":"success", "message":"Audio converted to mp3 successfully."})
    except ffmpeg.Error as e:
        return jsonify({"status":"error", "message":f"Error converting audio: {e.stderr.decode()}"})

@app.route('/control', methods=['POST'])
@require_auth
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
def index():
    if "username" in session:
        return redirect('/index')
    return redirect('/login')

@app.route('/index')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    username = request.form['username']
    password = request.form['password']
    if username in USERS and check_password_hash(USERS[username], password):
        if active_logins[username]:
            return "User already logged in from another device.", 403
        
        ua = request.user_agent.string.lower()
        if username == "mobile_user" and "mobile" not in ua:
            return "This account can only be accessed from a mobile device.", 403
        if username == "laptop_user" and "mobile" in ua:
            return "This account can only be accessed from a laptop/desktop device.", 403
        
        active_logins[username] = True
        session['username'] = username
        return redirect('/index')

@app.route('/stream')
def stream():
    return render_template('stream.html')

""" @app.route("/offer", methods=["POST"])
async def offer():
    params = request.get_json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection(RTCConfiguration(
        iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]
    ))
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print("Connection state:", pc.connectionState)
        if pc.connectionState in ("failed", "closed"):
            await pc.close()
            pcs.discard(pc)

    @pc.on("iceconnectionstatechange")
    async def on_ice():
        print("ICE state:", pc.iceConnectionState)
        if pc.iceConnectionState in ("failed", "disconnected", "closed"):
            await pc.close()
            pcs.discard(pc)

    # IMPORTANT: create the server-side transceiver first so it can be matched to
    # the client's offer m-line and have a valid offer-direction.
    transceiver = pc.addTransceiver("video", direction="sendonly")

    # now set the client's offer as the remote description
    await pc.setRemoteDescription(offer)

    # attach the screen track to the transceiver sender
    transceiver.sender.replaceTrack(ScreenTrack())

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return jsonify({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    }) """


## handling text input from broser
@app.route('/process',methods=['POST'])
@require_auth
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
@require_auth
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
@require_auth
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
@require_auth
def run_kai():
    #running script execution in a separate thread
    threading.Thread(target=run_kai_script).start()
    return 'KAI script is runnning in the background.'



@app.route('/sleep')
@require_auth
def sleep():
    try:
        result = subprocess.Popen([sys.executable, 'sleep.py'],)
        return f'Sleep script executed successfully. Output: {result.stdout}' 
        
    except subprocess.CalledProcessError as e:
        return f'Error executing Sleep script: {e.stderr}'
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)