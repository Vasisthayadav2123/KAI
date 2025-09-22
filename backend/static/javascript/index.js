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
                document.getElementById('response').innerText = data.say;
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

