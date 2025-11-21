async function startViewer() {
    const videoElement = document.getElementById("video");

    // WebRTC peer connection
    const pc = new RTCPeerConnection({
        iceServers: [
            { urls: ["stun:stun.l.google.com:19302"] }
        ]
    });

    pc.onicecandidate = (e) => console.log("CLIENT ICE candidate:", e.candidate);
    pc.oniceconnectionstatechange = () => console.log("CLIENT ICE state:", pc.iceConnectionState);
    pc.onconnectionstatechange = () => console.log("CLIENT connection state:", pc.connectionState);

    // When track received (server screen stream)
    pc.ontrack = (event) => {
        if (videoElement.srcObject !== event.streams[0]) {
            videoElement.srcObject = event.streams[0];
            videoElement.play().catch(e => console.warn("video.play() failed:", e));
        }
    };

    // REQUEST to RECEIVE video from server — must be added before createOffer
    pc.addTransceiver("video", { direction: "recvonly" });

    // Create offer
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    // Send offer to WebRTC server
    let resp;
    try {
        resp = await fetch("http://127.0.0.1:8080/offer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                sdp: pc.localDescription.sdp,
                type: pc.localDescription.type
            })
        });
    } catch (err) {
        console.error("Failed to POST offer:", err);
        return;
    }

    if (!resp.ok) {
        const text = await resp.text();
        console.error("Offer response error:", resp.status, text);
        return;
    }

    const answer = await resp.json();
    await pc.setRemoteDescription(answer);
}

async function sendAction(action) {
  await fetch('/control', {
    method: 'POST',
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ action: action })
  });
}


// Auto-start
startViewer();

