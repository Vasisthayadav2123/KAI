import asyncio
import time
import numpy as np
import cv2
from mss import mss
from av import VideoFrame
from aiortc import VideoStreamTrack

class GPUScreenTrack(VideoStreamTrack):
    def __init__(self, monitor=None, target_fps=60):
        super().__init__()
        self.sct = mss()
        self.monitor = monitor or self.sct.monitors[1]  # full screen
        self.frame_interval = 1 / target_fps
        self.last_time = 0
        self.running = True

        # grab first frame to initialize track
        img = self.sct.grab(self.monitor)
        frame = np.array(img)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
        self.first_frame = frame

    async def recv(self):
        if not self.running:
            await asyncio.sleep(0.05)
            return await self.recv()  # never return None

        # frame pacing
        now = time.time()
        elapsed = now - self.last_time
        if elapsed < self.frame_interval:
            await asyncio.sleep(self.frame_interval - elapsed)
        self.last_time = time.time()

        # grab screen frame
        img = self.sct.grab(self.monitor)
        frame = np.array(img)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)

        # convert to WebRTC VideoFrame
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts, video_frame.time_base = await self.next_timestamp()
        return video_frame

    def stop(self):
        self.running = False
        super().stop()