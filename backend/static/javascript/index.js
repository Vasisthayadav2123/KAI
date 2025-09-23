function handleSubmit() {
    const userInput = document.getElementById('commandInput').value;

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/process', true);
    xhr.setRequestHeader('Content-Type', 'application/json');

    xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
            if (xhr.status === 200) {
                const data = JSON.parse(xhr.responseText);
                console.log('Success:', data);
                const audioElm = document.getElementById("audio")
                document.getElementById("response").innerText = data.response.say;
                if(data.mp3){
                    audioElm.src= data.mp3;
                    audioElm.onended = function(){
                        fetch('/delete_audio', {method: 'POST' })
                    };
                    // loading and playing the audio
                    audioElm.load();
                    audioElm.play();
                }
                
            } else {
                console.error('Error:', xhr.statusText);
                document.getElementById("response").innerText = "An error occurred.";
            }
        }
    };

    const requestData = JSON.stringify({ command: userInput });
    xhr.send(requestData);
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
            const blob = new Blob(chunks, {'type':'audio/mp3'});
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
    formData.append('audio_data', blob, 'input.mp3');

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