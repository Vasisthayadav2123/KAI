async function startStream() {
  const videoElement = document.getElementById("video");
  const pc = new RTCPeerConnection();

  pc.ontrack = event => {
    console.log("🎥 Received remote track", event);
    videoElement.srcObject = event.streams[0];
    videoElement.play().catch(e => console.warn("video.play() failed:", e));
  };

  pc.oniceconnectionstatechange = () => {
    console.log("Client ICE state:", pc.iceConnectionState);
  };

  pc.addTransceiver("video", { direction: "recvonly" });

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  const response = await fetch("/offer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(pc.localDescription)
  });

  const answer = await response.json();
  await pc.setRemoteDescription(answer);
}

async function sendAction(action) {
  await fetch("/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action })
  });
}

startStream();
