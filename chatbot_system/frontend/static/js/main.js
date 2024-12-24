let documentText = '';

async function uploadPDF() {
    const fileInput = document.getElementById('pdfFile');
    const file = fileInput.files[0];
    
    if (!file) {
        alert('Please select a file first!');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        
        if (response.ok) {
            documentText = data.text;
            document.getElementById('documentContent').textContent = documentText;
            document.querySelector('.chat-section').style.display = 'block';
        } else {
            alert(data.error || 'Error uploading file');
        }
    } catch (error) {
        alert('Error uploading file: ' + error.message);
    }
}

async function askQuestion() {
    const questionInput = document.getElementById('questionInput');
    const question = questionInput.value.trim();
    
    if (!question) {
        alert('Please enter a question!');
        return;
    }

    try {
        const response = await fetch('/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                question: question,
                context: documentText
            })
        });

        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('answer').textContent = data.answer;
        } else {
            alert(data.error || 'Error getting answer');
        }
    } catch (error) {
        alert('Error getting answer: ' + error.message);
    }
}