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
                document.getElementById("response").innerText = data.status;
            } else {
                console.error('Error:', xhr.statusText);
                document.getElementById("response").innerText = "An error occurred.";
            }
        }
    };

    const requestData = JSON.stringify({ command: userInput });
    xhr.send(requestData);
    document.getElementById('response').innerText = data.say;
}
