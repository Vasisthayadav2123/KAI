import time
import random
import secrets
import uuid

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
from kai import process_text_command, transcribe_audio, warmup_model, unload_model, get_ai_status, stream_query_openclaw, only_transcribe, VOICE
import threading
import base64
from flask_socketio import SocketIO, emit
import ffmpeg
from flask_cors import CORS
from functools import wraps
from command_executor import execute_command_internal, APP_WHITELIST, SAFE_ROOTS
from diagnostics import start_diagnostics_monitor, active_ws_connections

# In-memory command history audit log
command_history = []
MAX_HISTORY_LIMIT = 50




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
socketio = SocketIO(app, cors_allowed_origins="*")


USERS = {
    "mobile_user": generate_password_hash("mobilepass"),
    "laptop_user": generate_password_hash("laptoppass")
}

active_logins = {
    "mobile_user": False,
    "laptop_user": False
}


@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "ok", "message": "pong"})


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

    # Warm up the LLM in the background (non-blocking)
    # This pre-loads the model into GPU VRAM so first AI query is fast
    threading.Thread(target=warmup_model, daemon=True).start()
    print("[KAI AUTH] Model warm-up triggered in background.")
    
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
        cmd = [
            'ffmpeg',
            '-y',
            '-i', input_path,
            '-f', 'wav',
            '-acodec', 'pcm_s16le',
            '-ac', '1',
            '-ar', '16000',
            output_path
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        os.remove(input_path)  # Remove the original
        return jsonify({"status":"success", "message":"Audio converted to mp3 successfully."})
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr if e.stderr else str(e)
        return jsonify({"status":"error", "message":f"Error converting audio: {err_msg}"})
    except Exception as e:
        return jsonify({"status":"error", "message":f"Error converting audio: {str(e)}"})

def convert_to_wav(input_path, output_path):
    """Utility to transcode input audio (like .m4a, .caf, .webm) into 16kHz mono WAV."""
    try:
        cmd = [
            'ffmpeg',
            '-y',
            '-i', input_path,
            '-f', 'wav',
            '-acodec', 'pcm_s16le',
            '-ac', '1',
            '-ar', '16000',
            output_path
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        if os.path.exists(input_path):
            os.remove(input_path)
        return True, "Success"
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr if e.stderr else str(e)
        return False, f"FFmpeg subprocess error: {err_msg}"
    except Exception as e:
        return False, str(e)

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


@app.route('/api/control/touch', methods=['POST'])
@require_auth
def control_touch():
    data = request.json or {}
    action_type = data.get('type')
    nx = data.get('nx')
    ny = data.get('ny')
    orientation = data.get('orientation', 'landscape')
    
    if nx is None or ny is None:
        return jsonify({'status': 'error', 'message': 'Missing coordinates'}), 400
        
    try:
        # Disable pyautogui fail-safe during remote touch to prevent crashes at coordinates (0,0)
        pyautogui.FAILSAFE = False
        
        screen_w, screen_h = pyautogui.size()
        x = int(nx * screen_w)
        y = int(ny * screen_h)
        
        if action_type == 'move':
            pyautogui.moveTo(x, y)
        elif action_type == 'click':
            pyautogui.click(x, y)
        elif action_type == 'double_click':
            pyautogui.doubleClick(x, y)
        elif action_type == 'right_click':
            pyautogui.rightClick(x, y)
        elif action_type == 'scroll':
            dy = data.get('dy', 0)
            pyautogui.scroll(int(dy * 100))
        elif action_type == 'drag':
            drag_state = data.get('drag_state')
            if drag_state == 'start':
                pyautogui.mouseDown(x, y)
            elif drag_state == 'drag':
                pyautogui.moveTo(x, y)
            elif drag_state == 'end':
                pyautogui.mouseUp(x, y)
        else:
            return jsonify({'status': 'error', 'message': f'Unknown action type: {action_type}'}), 400
            
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/control/keyboard', methods=['POST'])
@require_auth
def control_keyboard():
    data = request.json or {}
    text = data.get('text')
    key = data.get('key')
    
    try:
        if key:
            pyautogui.press(key)
        elif text:
            pyautogui.write(text)
        else:
            return jsonify({'status': 'error', 'message': 'Missing text or key'}), 400
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


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

# ── Command Centre Endpoints ──────────────────────────────────────

@app.route('/api/command/categories', methods=['GET'])
@require_auth
def get_categories():
    """Lists available commands, categories, whitelisted apps, and safe paths."""
    categories = [
        {
            "id": "media",
            "name": "Media Controller",
            "icon": "music.note",
            "commands": [
                {"type": "media.playpause", "name": "Play / Pause", "icon": "playpause.fill"},
                {"type": "media.previous", "name": "Previous Track", "icon": "backward.fill"},
                {"type": "media.next", "name": "Next Track", "icon": "forward.fill"},
                {"type": "media.volumeup", "name": "Volume Up", "icon": "speaker.wave.3.fill"},
                {"type": "media.volumedown", "name": "Volume Down", "icon": "speaker.wave.1.fill"},
                {"type": "media.mute", "name": "Mute", "icon": "speaker.slash.fill"},
            ]
        },
        {
            "id": "apps",
            "name": "Applications",
            "icon": "app.grid.3x3.fill",
            "commands": [
                {"type": "app.open", "name": "Web Browser", "icon": "globe", "payload": {"app": "browser"}},
                {"type": "app.open", "name": "VS Code", "icon": "chevron.left.forwardslash.chevron.right", "payload": {"app": "vscode"}},
                {"type": "app.open", "name": "File Explorer", "icon": "folder.fill", "payload": {"app": "explorer"}},
                {"type": "app.open", "name": "Notepad", "icon": "doc.text.fill", "payload": {"app": "notepad"}},
                {"type": "app.open", "name": "Discord", "icon": "discord", "payload": {"app": "discord"}},
                {"type": "app.open", "name": "Spotify", "icon": "spotify", "payload": {"app": "spotify"}},
                {"type": "app.open", "name": "Helldivers 2", "icon": "gamecontroller", "payload": {"app": "helldivers2"}},
                {"type": "app.open", "name": "Apex Legends", "icon": "gamecontroller", "payload": {"app": "apexlegends"}}
            ]
        },
        {
            "id": "fs",
            "name": "File Browser",
            "icon": "folder.badge.gearshape",
            "commands": [
                {"type": "fs.list", "name": "Browse Files", "icon": "list.bullet.indent"},
                {"type": "fs.open_file", "name": "Open File/Folder", "icon": "arrow.up.right.square"}
            ],
            "safe_roots": [{"name": os.path.basename(r) or r, "path": r} for r in SAFE_ROOTS]
        },
        {
            "id": "kai",
            "name": "KAI Assistant",
            "icon": "wand.and.stars",
            "commands": [
                {"type": "kai.text_command", "name": "Send AI Prompt", "icon": "paperplane.fill"},
                {"type": "kai.run_script", "name": "Run KAI Core", "icon": "play.fill"}
            ]
        },
        {
            "id": "audio",
            "name": "Audio Level",
            "icon": "speaker.wave.2.fill",
            "commands": [
                {"type": "audio.change_volume", "name": "Increase Volume", "icon": "plus", "payload": {"direction": "up", "steps": 2}},
                {"type": "audio.change_volume", "name": "Decrease Volume", "icon": "minus", "payload": {"direction": "down", "steps": 2}}
            ]
        },
        {
            "id": "display",
            "name": "Display Tools",
            "icon": "macpro.gen1",
            "commands": [
                {"type": "display.screenshot", "name": "Capture Screen", "icon": "camera.fill"}
            ]
        }
    ]
    return jsonify({"status": "success", "categories": categories})

@app.route('/api/command/execute', methods=['POST'])
@require_auth
def execute_command():
    """Route to execute a command securely."""
    data = request.get_json() or {}
    cmd_type = data.get("type")
    payload = data.get("payload") or {}

    if not cmd_type:
        return jsonify({"status": "error", "message": "Command type is required."}), 400

    # Intercept KAI async/threaded commands
    if cmd_type == "kai.text_command":
        user_input = payload.get("command")
        if not user_input:
            return jsonify({"status": "error", "message": "AI command input is required."}), 400
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(process_text_command(user_input, for_browser=True))
            # Log history
            record = {"type": cmd_type, "status": "success", "result": result.get("response", {}).get("say", ""), "timestamp": time.time()}
            command_history.insert(0, record)
            if len(command_history) > MAX_HISTORY_LIMIT:
                command_history.pop()
            return jsonify(result)
        except Exception as e:
            record = {"type": cmd_type, "status": "failed", "result": str(e), "timestamp": time.time()}
            command_history.insert(0, record)
            return jsonify({"status": "error", "message": f"KAI execution failed: {str(e)}"}), 500

    elif cmd_type == "kai.run_script":
        try:
            threading.Thread(target=run_kai_script).start()
            record = {"type": cmd_type, "status": "success", "result": "KAI script triggered in background", "timestamp": time.time()}
            command_history.insert(0, record)
            if len(command_history) > MAX_HISTORY_LIMIT:
                command_history.pop()
            return jsonify({"status": "success", "message": "KAI script is running in the background."})
        except Exception as e:
            record = {"type": cmd_type, "status": "failed", "result": str(e), "timestamp": time.time()}
            command_history.insert(0, record)
            return jsonify({"status": "error", "message": f"Failed to run KAI: {str(e)}"}), 500

    # Execute standard synchronous command
    success, result = execute_command_internal(cmd_type, payload)
    
    # Save to history log
    record = {
        "type": cmd_type,
        "status": "success" if success else "failed",
        "result": result if success else str(result),
        "timestamp": time.time()
    }
    command_history.insert(0, record)
    if len(command_history) > MAX_HISTORY_LIMIT:
        command_history.pop()

    if not success:
        return jsonify({"status": "error", "message": result}), 400

    return jsonify({"status": "success", "result": result})

@app.route('/api/command/history', methods=['GET'])
@require_auth
def get_command_history():
    """Retrieve recent command logs."""
    limit = min(int(request.args.get("limit", 20)), MAX_HISTORY_LIMIT)
    return jsonify({"status": "success", "history": command_history[:limit]})

@app.route('/api/command/voice', methods=['POST'])
@require_auth
def execute_voice_command():
    """Endpoint for processing mobile audio recordings and returning text + TTS response."""
    if 'audio_data' not in request.files:
        return jsonify({"status": "error", "message": "No audio file provided"}), 400

    audio_file = request.files['audio_data']
    if audio_file.filename == '':
        return jsonify({"status": "error", "message": "Empty filename"}), 400

    userinputs_dir = os.path.join('static', 'audio', 'userinputs')
    responses_dir = os.path.join('static', 'audio')
    os.makedirs(userinputs_dir, exist_ok=True)
    os.makedirs(responses_dir, exist_ok=True)

    # Resource management: Clean up audio files older than 5 minutes
    try:
        current_time = time.time()
        for folder in [userinputs_dir, responses_dir]:
            for f in os.listdir(folder):
                file_path = os.path.join(folder, f)
                if os.path.isfile(file_path) and (current_time - os.path.getmtime(file_path)) > 300:
                    if f not in ["dummy.wav", "response.mp3"]:
                        os.remove(file_path)
    except Exception as cleanup_err:
        print(f"[KAI CLEANUP] Error cleaning up audio: {cleanup_err}")

    # Generate isolated session UUID paths
    unique_id = str(uuid.uuid4())
    _, ext = os.path.splitext(audio_file.filename)
    if not ext:
        ext = '.m4a'

    temp_input_path = os.path.join(userinputs_dir, f"{unique_id}{ext}")
    temp_wav_path = os.path.join(userinputs_dir, f"{unique_id}.wav")
    output_mp3_path = os.path.join(responses_dir, f"response_{unique_id}.mp3")

    try:
        audio_file.save(temp_input_path)
        
        # Transcode to WAV format
        success, convert_msg = convert_to_wav(temp_input_path, temp_wav_path)
        if not success:
            return jsonify({"status": "error", "message": f"Audio transcoding failed: {convert_msg}"}), 500

        # Run speech-to-text -> query LLM -> text-to-speech loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(transcribe_audio(temp_wav_path, output_file=output_mp3_path))
        
        if os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)

        if result.get("status") == "error":
            return jsonify(result), 500

        # Log history
        record = {
            "type": "kai.voice_command",
            "status": "success",
            "result": f"Voice command: '{result.get('query')}' -> '{result.get('response', {}).get('say')}'",
            "timestamp": time.time()
        }
        command_history.insert(0, record)
        if len(command_history) > MAX_HISTORY_LIMIT:
            command_history.pop()

        return jsonify({
            "status": "success",
            "query": result.get("query", ""),
            "reply": result.get("response", {}).get("say", ""),
            "mp3": result.get("mp3")
        })

    except Exception as e:
        # Cleanup
        for p in [temp_input_path, temp_wav_path, output_mp3_path]:
            if os.path.exists(p):
                try: os.remove(p)
                except: pass
        return jsonify({"status": "error", "message": f"Voice command execution failed: {str(e)}"}), 500


# ── AI Lifecycle Endpoints ────────────────────────────────────────

@app.route('/api/ai/status')
@require_auth
def ai_status():
    """Check the health of Ollama, OpenClaw, and model load state."""
    status = get_ai_status()
    return jsonify(status)


@app.route('/api/ai/warmup', methods=['POST'])
@require_auth
def manual_warmup():
    """Manually trigger LLM model loading into VRAM."""
    threading.Thread(target=warmup_model, daemon=True).start()
    return jsonify({"status": "warming_up", "message": "Model loading into VRAM in background."})


@app.route('/api/ai/unload', methods=['POST'])
@require_auth
def manual_unload():
    """Immediately unload the LLM from GPU VRAM to free resources."""
    success = unload_model()
    if success:
        return jsonify({"status": "unloaded", "message": "Model removed from VRAM. GPU resources freed."})
    else:
        return jsonify({"status": "error", "message": "Failed to unload model."}), 500


# ── WebSockets Streaming Handlers ─────────────────────────────────

@socketio.on('connect')
def ws_connect(auth=None):
    token = auth.get('token') if auth else None
    if not token or not is_valid_session(token):
        print("[KAI WS] Connection refused: invalid session token.")
        return False
    print(f"[KAI WS] Client connected: {request.sid}")
    active_ws_connections.add(request.sid)

@socketio.on('disconnect')
def ws_disconnect():
    print(f"[KAI WS] Client disconnected: {request.sid}")
    active_ws_connections.discard(request.sid)

@socketio.on('command')
def ws_handle_command(data):
    """Processes incoming client prompts or base64 audio commands."""
    text = data.get('text')
    audio_base64 = data.get('audio')
    file_ext = data.get('ext', '.m4a')
    sid = request.sid
    
    # Process in a background thread to prevent blocking WebSocket server loop
    socketio.start_background_task(target=process_ws_command_background, text=text, audio_base64=audio_base64, file_ext=file_ext, sid=sid)

def process_ws_command_background(text, audio_base64, file_ext, sid):
    # Establish new event loop for async operations in this background thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    temp_input_path = None
    temp_wav_path = None
    
    try:
        user_input = text
        
        if audio_base64:
            # Save and decode base64 audio
            audio_bytes = base64.b64decode(audio_base64)
            userinputs_dir = os.path.join('static', 'audio', 'userinputs')
            os.makedirs(userinputs_dir, exist_ok=True)
            unique_id = str(uuid.uuid4())
            
            temp_input_path = os.path.join(userinputs_dir, f"{unique_id}_ws_in{file_ext}")
            temp_wav_path = os.path.join(userinputs_dir, f"{unique_id}_ws.wav")
            
            with open(temp_input_path, 'wb') as f:
                f.write(audio_bytes)
                
            # Transcode
            success, convert_msg = convert_to_wav(temp_input_path, temp_wav_path)
            if not success:
                socketio.emit('reply_error', {"message": f"Audio transcoding failed: {convert_msg}"}, to=sid)
                return
                
            # Transcribe
            try:
                user_input = only_transcribe(temp_wav_path)
            except Exception as stt_err:
                socketio.emit('reply_error', {"message": f"Speech-to-text failed: {str(stt_err)}"}, to=sid)
                return
            finally:
                if temp_wav_path and os.path.exists(temp_wav_path):
                    try: os.remove(temp_wav_path)
                    except: pass
                    
        if not user_input:
            socketio.emit('reply_error', {"message": "Empty prompt received."}, to=sid)
            return

        # Emit reply_start with the query
        socketio.emit('reply_start', {"query": user_input}, to=sid)

        # Run streaming LLM + TTS pipeline
        async def run_pipeline():
            import edge_tts
            full_reply_text = []
            
            async for sentence in stream_query_openclaw(user_input):
                full_reply_text.append(sentence)
                
                # Stream TTS audio chunks
                audio_chunks = []
                try:
                    communicate = edge_tts.Communicate(sentence, VOICE)
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            audio_chunks.append(chunk["data"])
                except Exception as tts_err:
                    print(f"[KAI WS] TTS streaming failed for sentence '{sentence}': {tts_err}")
                
                audio_b64 = None
                if audio_chunks:
                    audio_b64 = base64.b64encode(b"".join(audio_chunks)).decode('utf-8')
                    
                socketio.emit('reply_chunk', {
                    "text_chunk": sentence,
                    "audio_chunk": audio_b64
                }, to=sid)
                
            # Emit reply_end when finished
            full_reply_str = " ".join(full_reply_text)
            socketio.emit('reply_end', {"status": "done"}, to=sid)
            
            # Log history
            record = {
                "type": "kai.ws_voice_command" if audio_base64 else "kai.ws_text_command",
                "status": "success",
                "result": f"WS command: '{user_input}' -> '{full_reply_str}'",
                "timestamp": time.time()
            }
            command_history.insert(0, record)
            if len(command_history) > MAX_HISTORY_LIMIT:
                command_history.pop()

        loop.run_until_complete(run_pipeline())
        
    except Exception as e:
        print(f"[KAI WS] Execution failed: {e}")
        socketio.emit('reply_error', {"message": f"Execution failed: {str(e)}"}, to=sid)
        
    finally:
        for p in [temp_input_path, temp_wav_path]:
            if p and os.path.exists(p):
                try: os.remove(p)
                except: pass


if __name__ == '__main__':
    import os
    # Start background dependency services only in the main/parent process.
    # This avoids double-spawning services in the Flask reloader child process,
    # and keeps the background services running across code reloads.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        from service_manager import start_all_services_async
        start_all_services_async()
        
        # Start background diagnostics monitoring thread
        start_diagnostics_monitor()

    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)