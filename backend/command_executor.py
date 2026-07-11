import os
import subprocess
import sys
import pyautogui
import base64
from io import BytesIO

# Whitelist of safe applications that can be launched
APP_WHITELIST = {
    "browser": "start https://www.google.com",
    "vscode": "code",
    "explorer": "explorer",
    "notepad": "notepad",
    "discord": '"%LocalAppData%\\Discord\\Update.exe" --processStart Discord.exe',
    "spotify": "explorer.exe shell:AppsFolder\\SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify",
    "helldivers2": "start steam://rungameid/553850",
    "apexlegends": "start steam://rungameid/1172470"
}

# Whitelist of safe root directories for file browsing
# We'll resolve paths and ensure they start with these prefix paths
SAFE_ROOTS = [
    os.path.abspath(os.path.expanduser("~")),  # User home directory
    os.path.abspath(os.getcwd())  # Current project directory
]

def is_path_safe(target_path):
    try:
        abs_path = os.path.abspath(target_path)
        for root in SAFE_ROOTS:
            if abs_path.startswith(root):
                return True
        return False
    except Exception:
        return False

def execute_command_internal(cmd_type, payload):
    """
    Executes a given command by type and payload.
    Returns (success, result_message_or_data)
    """
    try:
        # --- MEDIA COMMANDS ---
        if cmd_type == "media.playpause":
            pyautogui.press('playpause')
            return True, "Media toggled Play/Pause"
        elif cmd_type == "media.next":
            pyautogui.press('nexttrack')
            return True, "Media skipped to Next track"
        elif cmd_type == "media.previous":
            pyautogui.press('prevtrack')
            return True, "Media skipped to Previous track"
        elif cmd_type == "media.volumeup":
            pyautogui.press('volumeup')
            return True, "Volume Increased"
        elif cmd_type == "media.volumedown":
            pyautogui.press('volumedown')
            return True, "Volume Decreased"
        elif cmd_type == "media.mute":
            pyautogui.press('volumemute')
            return True, "Volume Muted/Unmuted"

        # --- APP LAUNCH COMMANDS ---
        elif cmd_type == "app.open":
            app_id = payload.get("app")
            if not app_id or app_id not in APP_WHITELIST:
                return False, f"Unauthorized or unknown application: {app_id}"
            
            cmd = APP_WHITELIST[app_id]
            expanded_cmd = os.path.expandvars(cmd)
            # Use shell=True to support commands like 'start' or 'code'
            subprocess.Popen(expanded_cmd, shell=True)
            return True, f"Launched application: {app_id}"

        # --- FILE SYSTEM COMMANDS ---
        elif cmd_type == "fs.list":
            target_dir = payload.get("path") or SAFE_ROOTS[0]
            if not is_path_safe(target_dir):
                return False, "Access denied: directory is outside of safe zones."
            
            if not os.path.exists(target_dir):
                return False, f"Directory does not exist: {target_dir}"
            
            items = []
            for item in os.listdir(target_dir):
                full_path = os.path.join(target_dir, item)
                items.append({
                    "name": item,
                    "is_dir": os.path.isdir(full_path),
                    "path": full_path,
                    "size": os.path.getsize(full_path) if os.path.isfile(full_path) else 0
                })
            
            # Sort: directories first, then files alphabetically
            items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            return True, {"current_path": target_dir, "items": items}

        elif cmd_type == "fs.open_file":
            target_path = payload.get("path")
            if not target_path or not is_path_safe(target_path):
                return False, "Access denied: file/folder is outside of safe zones."
            
            if not os.path.exists(target_path):
                return False, f"Path does not exist: {target_path}"
            
            # Use safe opening mechanism
            os.startfile(target_path)
            return True, f"Opened: {os.path.basename(target_path)}"

        # --- AUDIO COMMANDS ---
        elif cmd_type == "audio.change_volume":
            direction = payload.get("direction")
            steps = min(int(payload.get("steps", 1)), 10)
            key = "volumeup" if direction == "up" else "volumedown"
            for _ in range(steps):
                pyautogui.press(key)
            return True, f"Adjusted volume {direction} by {steps} steps"

        # --- DISPLAY COMMANDS ---
        elif cmd_type == "display.screenshot":
            screenshot = pyautogui.screenshot()
            buffered = BytesIO()
            screenshot.save(buffered, format="JPEG", quality=75)
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            return True, {"image": f"data:image/jpeg;base64,{img_str}"}

        # --- KAI COMMANDS ---
        # Note: kai.text_command and kai.run_script will be intercepted and handled 
        # asynchronously inside app.py since they might need to run async event loops or separate threads.
        else:
            return False, f"Unknown command type: {cmd_type}"

    except Exception as e:
        return False, f"Execution failed: {str(e)}"
