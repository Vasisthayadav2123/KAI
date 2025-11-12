async function startStream() {
  const videoElement = document.getElementById("video");
  const pc = new RTCPeerConnection();

  pc.ontrack = event => {
    console.log("🎥 Received remote track");
    videoElement.srcObject = event.streams[0];
  };

  // Create an SDP offer
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  // Send the offer to Flask backend
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
