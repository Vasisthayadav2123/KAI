import os
import sys
import time
import socket
import subprocess
import threading
import atexit

# Configuration
OLLAMA_PORT = 11434
OPENCLAW_PORT = 18789
STREAM_PORT = 8080

OLLAMA_CMD = ["ollama", "serve"]

# Direct node execution for OpenClaw is cleaner and allows direct process killing (no orphaned cmd process trees)
openclaw_js = os.path.expanduser(r"~\AppData\Roaming\npm\node_modules\openclaw\dist\index.js")
if os.path.exists(openclaw_js):
    OPENCLAW_CMD = ["node", openclaw_js, "gateway", "--port", "18789"]
else:
    OPENCLAW_CMD = [os.path.expanduser(r"~\.openclaw\gateway.cmd")]

# Resolve the venv python path to run serverStream.py since it has OpenCV/WebRTC dependencies installed
venv_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "venv"))
if sys.platform == "win32":
    venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
else:
    venv_python = os.path.join(venv_dir, "bin", "python")

if os.path.exists(venv_python):
    STREAM_CMD = [venv_python, "serverStream.py"]
else:
    # Fallback to the current python environment
    STREAM_CMD = [sys.executable, "serverStream.py"]

# Keep track of processes we spawned to clean them up on exit
spawned_processes = []
process_lock = threading.Lock()

def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Checks if a local TCP port is already open/listening."""
    try:
        with socket.create_connection((host, port), timeout=1.0) as s:
            return True
    except (ConnectionRefusedError, socket.timeout):
        return False

def spawn_service(name: str, cmd: list, port: int):
    """Spawns a background service if it is not already running on its port."""
    if is_port_open(port):
        print(f"[KAI Service Manager] {name} is already running on port {port}.")
        return

    print(f"[KAI Service Manager] Starting {name}...")
    try:
        # Create detached process group on Windows so it runs invisibly in background
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            creationflags=creation_flags
        )
        
        with process_lock:
            spawned_processes.append((name, proc))
        
        print(f"[KAI Service Manager] Spawned {name} (PID: {proc.pid})")
    except Exception as e:
        print(f"[KAI Service Manager] Failed to start {name}: {e}")

def start_all_services_async():
    """Starts all missing services in a separate background thread so it doesn't block Flask boot."""
    def run():
        print("[KAI Service Manager] Initiating background dependency services check...")
        
        # 1. Start Ollama
        spawn_service("Ollama", OLLAMA_CMD, OLLAMA_PORT)
        time.sleep(1.0) # Give Ollama a moment to initialize
        
        # 2. Start WebRTC Stream Server (serverStream.py)
        spawn_service("WebRTC Stream Server", STREAM_CMD, STREAM_PORT)

    thread = threading.Thread(target=run, name="KAI-Service-Bootstrapper")
    thread.daemon = True
    thread.start()

def cleanup_spawned_services():
    """Terminates all services spawned by this instance on shutdown."""
    with process_lock:
        if not spawned_processes:
            return
            
        print("\n[KAI Service Manager] Server stopping. Terminating background services...")
        for name, proc in spawned_processes:
            if proc.poll() is None:
                print(f"[KAI Service Manager] Stopping {name} (PID: {proc.pid})...")
                try:
                    proc.terminate()
                    # Wait up to 2 seconds for it to exit
                    proc.wait(timeout=2.0)
                    print(f"[KAI Service Manager] {name} exited gracefully.")
                except subprocess.TimeoutExpired:
                    print(f"[KAI Service Manager] {name} did not exit. Killing process...")
                    proc.kill()
                except Exception as ex:
                    print(f"[KAI Service Manager] Error stopping {name}: {ex}")
        
        spawned_processes.clear()

# Register the cleanup handler to execute when Python interpreter exits
atexit.register(cleanup_spawned_services)
