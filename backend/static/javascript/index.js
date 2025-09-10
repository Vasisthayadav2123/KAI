function handleSubmit() {
    const userInput = document.getElementById('commandInput').value;
    
    fetch('/process', {
        method: 'POST',
        headers: {
            'content-type': 'application/json'
        },
        body: JSON.stringify({ command: userInput })
    })
    .then(response => response.json())
    .then(data => {
        console.log('Success:', data);
    })
    .catch((error) => {
        console.error('Error:', error);
    });
    document.getElementById("response").innerText = data.status;
}
