"""Quick diagnostic to check if the audio pipeline works end-to-end."""
import subprocess
import re
import time
import numpy as np
from av import AudioFrame

# Step 1: Detect device
print("=" * 60)
print("STEP 1: Detecting audio devices...")
cmd = ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
stderr = result.stderr or ""
audio_devices = re.findall(r'"([^"]+)"\s+\(audio\)', stderr)
print(f"  Found devices: {audio_devices}")

if not audio_devices:
    print("  ERROR: No audio devices found!")
    exit(1)

device_name = audio_devices[0]
for dev in audio_devices:
    if "stereo mix" in dev.lower():
        device_name = dev
        break

print(f"  Using: {device_name}")

# Step 2: Try to capture audio with FFmpeg
print("\n" + "=" * 60)
print("STEP 2: Testing FFmpeg capture (3 seconds)...")
ffmpeg_cmd = [
    "ffmpeg",
    "-f", "dshow",
    "-i", f"audio={device_name}",
    "-ac", "2",
    "-ar", "48000",
    "-f", "s16le",
    "-t", "3",
    "pipe:1"
]

proc = subprocess.Popen(
    ffmpeg_cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    bufsize=0
)

samples_per_frame = 960
channels = 2
num_bytes = samples_per_frame * channels * 2  # 3840 bytes per frame

frame_count = 0
total_bytes = 0
start = time.time()

while time.time() - start < 4:
    data = proc.stdout.read(num_bytes)
    if not data:
        break
    total_bytes += len(data)
    frame_count += 1
    
    if frame_count <= 3 or frame_count % 50 == 0:
        audio_data = np.frombuffer(data, dtype=np.int16)
        max_val = np.max(np.abs(audio_data))
        print(f"  Frame {frame_count}: {len(data)} bytes, max amplitude: {max_val}")

proc.terminate()
stderr_output = proc.stderr.read().decode('utf-8', errors='replace')

if frame_count == 0:
    print(f"\n  ERROR: FFmpeg produced 0 frames!")
    print(f"  FFmpeg stderr:\n{stderr_output[-500:]}")
else:
    print(f"\n  SUCCESS: Got {frame_count} frames, {total_bytes} total bytes")

# Step 3: Test AudioFrame creation
print("\n" + "=" * 60)
print("STEP 3: Testing AudioFrame creation...")
try:
    test_data = np.zeros(samples_per_frame * channels, dtype=np.int16)
    test_data = test_data.reshape(1, -1)
    frame = AudioFrame.from_ndarray(test_data, format="s16", layout="stereo")
    frame.sample_rate = 48000
    print(f"  SUCCESS: Created AudioFrame - samples={frame.samples}, rate={frame.sample_rate}, layout={frame.layout.name}")
    print(f"  Frame format: {frame.format.name}, planes: {len(frame.planes)}")
except Exception as e:
    print(f"  ERROR: {e}")

# Step 4: Check FFmpeg stderr for any device errors
print("\n" + "=" * 60)
print("STEP 4: FFmpeg stderr (last 500 chars):")
print(stderr_output[-500:] if stderr_output else "  (empty)")

print("\n" + "=" * 60)
print("DIAGNOSIS COMPLETE")
