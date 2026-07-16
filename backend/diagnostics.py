import os
import sys
import time
import socket
import threading
import json
import asyncio
import psutil
import subprocess

# --- CONFIGURATION & GLOBALS ---
START_TIME = time.time()
LAST_LLM_LATENCY_MS = None
VOICE = "en-US-SteffanNeural"

# Track active websocket connections (populated by app.py)
active_ws_connections = set()

# Thread-safe cache for slow network & TTS checks
_cached_network_tts = {
    "internet": False,
    "dns": False,
    "ping_ms": None,
    "tts": False,
    "last_updated": 0
}
cache_lock = threading.Lock()

# --- LATENCY TRACKING ---
def set_last_latency(latency_ms: float):
    global LAST_LLM_LATENCY_MS
    LAST_LLM_LATENCY_MS = latency_ms

def get_last_latency():
    return LAST_LLM_LATENCY_MS

# --- GPU STATS GATHERER ---
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
        return {
            "load_percent": 0,
            "memory_total_mb": 0,
            "memory_used_mb": 0,
            "memory_percent": 0,
            "temperature_c": 0,
            "error": str(e)
        }

# --- NETWORK THROUGHPUT ---
last_net_io = psutil.net_io_counters()
last_time = time.time()

def get_network_speed():
    global last_net_io, last_time

    current_net_io = psutil.net_io_counters()
    current_time = time.time()

    interval = current_time - last_time
    if interval <= 0:
        interval = 1.0

    bytes_sent = current_net_io.bytes_sent - last_net_io.bytes_sent
    bytes_recv = current_net_io.bytes_recv - last_net_io.bytes_recv

    last_net_io = current_net_io
    last_time = current_time
    
    # Return speed in Mbps
    return {
        "upload_mbps": round(((bytes_sent * 8) / (1024 * 1024)) / interval, 2),
        "download_mbps": round(((bytes_recv * 8) / (1024 * 1024)) / interval, 2)
    }

# --- EDGE TTS CONNECTIVITY CHECK ---
async def check_tts_connectivity():
    import edge_tts
    temp_file = "static/audio/temp_tts_check.mp3"
    os.makedirs(os.path.dirname(temp_file), exist_ok=True)
    try:
        communicate = edge_tts.Communicate("h", VOICE)
        await communicate.save(temp_file)
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except: pass
            return True
        return False
    except Exception:
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except: pass
        return False

def check_tts_connectivity_sync():
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        # Run with 2.5s timeout to prevent hanging
        return loop.run_until_complete(asyncio.wait_for(check_tts_connectivity(), timeout=2.5))
    except Exception:
        return False
    finally:
        loop.close()

# --- BACKROUND NETWORK & TTS WORKER ---
def run_slow_checks():
    """Performs the slow network and TTS checks in a separate background thread."""
    # 1. Ping Google DNS (8.8.8.8) on port 53
    ping_ms = None
    internet = False
    t0 = time.perf_counter()
    try:
        with socket.create_connection(("8.8.8.8", 53), timeout=1.5) as s:
            ping_ms = round((time.perf_counter() - t0) * 1000, 1)
            internet = True
    except Exception:
        pass

    # 2. DNS Resolution of google.com
    dns = False
    try:
        socket.gethostbyname("google.com")
        dns = True
    except Exception:
        pass

    # 3. TTS Connectivity
    tts = check_tts_connectivity_sync()

    with cache_lock:
        _cached_network_tts["internet"] = internet
        _cached_network_tts["dns"] = dns
        _cached_network_tts["ping_ms"] = ping_ms
        _cached_network_tts["tts"] = tts
        _cached_network_tts["last_updated"] = time.time()

# --- SERVICE CHECKERS ---
def get_spawned_services_status():
    try:
        from service_manager import spawned_processes, process_lock
        status_list = []
        with process_lock:
            for name, proc in spawned_processes:
                poll_val = proc.poll()
                status = "RUNNING" if poll_val is None else f"EXITED({poll_val})"
                status_list.append({
                    "name": name,
                    "pid": proc.pid,
                    "status": status
                })
        return status_list
    except Exception:
        return []

# --- DIAGNOSTICS COLLECTION ---
def collect_full_diagnostics() -> dict:
    """Gathers all diagnostics. Real-time for fast checks, cached for slow ones."""
    # Gather real-time fast checks
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_cores = psutil.cpu_count()
    cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
    
    virtual_mem = psutil.virtual_memory()
    ram = {
        "used_gb": round(virtual_mem.used / (1024**3), 2),
        "total_gb": round(virtual_mem.total / (1024**3), 1),
        "percent": virtual_mem.percent
    }
    
    disk_usage = psutil.disk_usage('/')
    disk = {
        "used_gb": round(disk_usage.used / (1024**3), 1),
        "total_gb": round(disk_usage.total / (1024**3), 1),
        "percent": disk_usage.percent
    }
    
    gpu = get_gpu_stats()
    
    # AI Core Health
    try:
        from kai import get_ai_status
        ollama_status = get_ai_status()
    except Exception as e:
        ollama_status = {"error": str(e)}

    # Process health
    try:
        p = psutil.Process(os.getpid())
        proc_stats = {
            "pid": os.getpid(),
            "memory_mb": round(p.memory_info().rss / (1024 * 1024), 1),
            "threads": p.num_threads()
        }
    except Exception:
        proc_stats = {"pid": os.getpid(), "memory_mb": 0, "threads": 0}

    # Service health ports
    try:
        from service_manager import is_port_open
        webrtc_running = is_port_open(8080)
        ollama_running = is_port_open(11434)
    except Exception:
        webrtc_running = False
        ollama_running = False

    # Retrieve slow checks from cache
    with cache_lock:
        slow_checks = _cached_network_tts.copy()

    # Network Speed (measured over the loop interval)
    net_speed = get_network_speed()

    stats = {
        "timestamp": time.time(),
        "hardware": {
            "cpu": {
                "percent": cpu_percent,
                "cores": cpu_cores,
                "per_core": cpu_per_core
            },
            "ram": ram,
            "disk": disk,
            "gpu": gpu
        },
        "ai_core": {
            "ollama": ollama_status,
            "last_latency_ms": LAST_LLM_LATENCY_MS,
            "tts": {
                "edge_tts_connected": slow_checks["tts"]
            }
        },
        "network": {
            "internet": slow_checks["internet"],
            "dns": slow_checks["dns"],
            "ping_ms": slow_checks["ping_ms"],
            "speed": net_speed
        },
        "services": {
            "flask_uptime_s": round(time.time() - START_TIME, 1),
            "webrtc": webrtc_running,
            "ollama": ollama_running,
            "ws_connections": len(active_ws_connections),
            "spawned": get_spawned_services_status()
        },
        "process": proc_stats
    }
    return stats

# --- BACKGROUND MONITORING LOOP ---
def diagnostics_worker_loop():
    """Runs in a background daemon thread, performing diagnostics periodically."""
    print("[KAI Diagnostics] Background diagnostics monitoring loop started.")
    
    # Perform initial slow check immediately on startup
    try:
        run_slow_checks()
    except Exception as e:
        print(f"[KAI Diagnostics] Initial slow checks error: {e}")
        
    while True:
        try:
            # Update slow cached network/TTS checks
            run_slow_checks()
        except Exception as err:
            print(f"[KAI Diagnostics] Error in background monitoring loop: {err}")
            
        # Sleep for 30 seconds before next collection
        time.sleep(30)

def start_diagnostics_monitor():
    """Starts the diagnostics thread."""
    thread = threading.Thread(target=diagnostics_worker_loop, name="KAI-Diagnostics-Monitor")
    thread.daemon = True
    thread.start()
