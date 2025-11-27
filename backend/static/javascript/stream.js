const videoElement = document.getElementById("video");
async function startViewer() {

    // WebRTC peer connection
    const pc = new RTCPeerConnection({
        iceServers: [
            { urls: ["stun:stun.l.google.com:19302"] }
        ]
    });

    pc.oniceconnectionstatechange = () => console.log("CLIENT ICE state:", pc.iceConnectionState);
    pc.onconnectionstatechange = () => console.log("CLIENT connection state:", pc.connectionState);

    // When track received (server screen stream)
    pc.ontrack = (event) => {
        if (videoElement.srcObject !== event.streams[0]) {
            videoElement.srcObject = event.streams[0];
            videoElement.play().catch(e => console.warn("video.play() failed:", e));
            startFPSCounter(videoElement);
        }
    };

    // REQUEST to RECEIVE video/audio from server 
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });

    // Create offer
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    // Send offer to WebRTC server
    let resp;
    try {
        resp = await fetch("http://192.168.1.38:8080/offer", {
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

function startFPSCounter(){
    let lastFrame = performance.now();
    let frames = 0;

    function updateFPS(now){
        frames++;
        const delta = now - lastFrame;
        if(delta >= 1000){
            const fps =(frames/delta)*1000;
            document.getElementById("fps").textContent = `FPS: ${fps.toFixed(1)}`;

            lastTime= now;
            frames =0;
        }
        videoElement.requestVideoFrameCallback(updateFPS);
    }
    videoElement.requestVideoFrameCallback(updateFPS);
}

