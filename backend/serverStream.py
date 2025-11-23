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
class GPUScreenTrack(VideoStreamTrack);
    def __init__(self, monitor=None, target_fps=60):
        super().__init__()
        self.sct = mss.mss()





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