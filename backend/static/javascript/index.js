function handleSubmit() {
    const userInput = document.getElementById('commandInput').value;

    fetch('/process',{
        method : 'POST',
        headers : {
            'content-type' : 'application/json'
        },
        body : JSON.stringify({command : userInput})
    })
    .then(response => {
        if (!response.ok){
            throw new Error('error status:${response.status}');
        }
        return response.json();
    })
    .then(data => {
        console.log('Success:', data);
        const audioEmlement = document.getElementById('audio');
        document.getElementById('response').innerText = data.response.say;
        if (data.mp3) {
            audioEmlement.src = data.mp3 + '?t=' + new Date().getTime(); // Cache-busting
            audioEmlement.onended = function() {
                fetch('/delete_audio', {
                    method: 'POST',
                });
                audioEmlement.src = "";
            };
            audioEmlement.load();
            audioEmlement.play();
        }
    })
    .catch((error) => {
        console.error('Error:', error);
    });
}

let mdeiaRecorder;
let chunks = [];

const constraints = { audio:true}




async function start_Audio_Record() {
    navigator.mediaDevices.getUserMedia(constraints)
    .then(function(stream) {
        // new media recorder instance
        mediaRecorder = new MediaRecorder(stream);

        mediaRecorder.ondataavailable = function(e){
            chunks.push(e.data);
        };
        //after recording stop
        // convert the audio data to blob
        mediaRecorder.onstop = function(e){
            const blob = new Blob(chunks, {'type':'audio/webm'});
            const audioURL = window.URL.createObjectURL(blob);

            //send the blob to the server
            sendAudio(blob)
        };
        //start recording
        mediaRecorder.start();
        console.log(mediaRecorder.state);
        console.log("recorder started");
    })
    .catch(function(err) {
        console.log('The following error occurred: ' + err);
    });

}

function stop_Audio_Record() {
    mediaRecorder.stop();
    console.log(mediaRecorder.state);
    console.log("recorder stopped");
}

function sendAudio(blob) {
    const formData = new FormData();
    formData.append('audio_data', blob, 'input.webm');
    fetch('/send_audio',{
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        console.log('Success:', data);
    })
    .catch((error) => {
        console.error('Error:', error);
    });
}