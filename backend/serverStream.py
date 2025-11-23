import asyncio
import time
import numpy as np
import cv2
import mss as mss
from av import VideoFrame
from aiohttp import web
import aiohttp_cors
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack , AudioStreamTrack
import subprocess


"""""""""
------> Gpu screen track for low latency
"""""""""
class GPUScreenTrack(VideoStreamTrack):
    def __init__(self, monitor=None, target_fps=60):
        super().__init__()
        self.sct = mss.mss()
        self.monitor = monitor or self.sct.monitors[1]
        self.frame_interval = 1/ target_fps
        self.last_time = 0
        self.running = True

        img = self.sct.grab(self.monitor)
        frame = np.array(img)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
        self.first_frame = frame

    async def recv(self):
        if not self.running:
            await asyncio.sleep(0.05)
            return await self.recv()
        
        now = time.time()
        elapsed = now - self.last_time
        if elapsed < self.frame_interval:
            await asyncio.sleep(self.frame_interval - elapsed)
        self.last_time = time.time()

        #get screen frame
        img = self.sct.grab(self.monitor)
        frame = np.array(img)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)

        # attacht to webrtc frame
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts, video_frame.time_base = await self.next_timestamp()
        return video_frame
    
    def stop(self):
        self.running = False
        super().stop()




"""""""""
------> Audio track from system audio
"""""""""



class systemAudioTrack(AudioStreamTrack):
    kind = "audio"
    def __init__(self):
        super().__init__()

        ffmpeg_cmd = [
            "ffmpeg",
            "-f", "dshow",
            "-i",
            "audio=Stereo Mix (Realtek(R) Audio)", 
            "-ac",
            "2",
            "-ar",
            "48000",
            "-f",
            "s16le",
            "pipe:1"
        ]





"""""""""
------> webRtc server
"""""""""
pcs = set()
viewer_count = 0

async def offer(request):
    global viewer_count
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)
    viewer_count += 1
    print("Viewer connected:", viewer_count)

    # each viewer gets its own GPU track
    screen_track = GPUScreenTrack(target_fps=60)
    pc.addTrack(screen_track)

    @pc.on("connectionstatechange")
    async def on_disconnect():
        global viewer_count
        if pc.connectionState in ["failed", "closed", "disconnected"]:
            viewer_count -= 1
            print("Viewer disconnected:", viewer_count)
            screen_track.stop()
            await pc.close()
            pcs.discard(pc)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response(
        {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
    )

# Create aiohttp app
app = web.Application()
app.router.add_post("/offer", offer)

# Setup CORS to allow Flask page access
cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
    )
})
for route in list(app.router.routes()):
    cors.add(route)

if __name__ == "__main__":
    web.run_app(app, port=8080)