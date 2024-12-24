let documentText = '';

// Show/hide loading overlay
function showLoading(message = 'Processing...') {
    document.getElementById('loadingText').textContent = message;
    document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('pdfFile');
    const fileInfo = document.getElementById('fileInfo');
    const uploadStatus = document.getElementById('uploadStatus');

    // File input change handler
    fileInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            if (file.type !== 'application/pdf') {
                uploadStatus.innerHTML = '<span class="error">Please select a PDF file</span>';
                return;
            }
            fileInfo.textContent = `Selected: ${file.name}`;
            uploadPDF(file);
        }
    });

    // Drag and drop handlers
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('upload-area-active');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('upload-area-active');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('upload-area-active');
       
        const file = e.dataTransfer.files[0];
        if (file && file.type === 'application/pdf') {
            fileInfo.textContent = `Selected: ${file.name}`;
            uploadPDF(file);
        } else {
            uploadStatus.innerHTML = '<span class="error">Please upload a PDF file</span>';
        }
    });
});

async function uploadPDF(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        showLoading('Uploading and processing PDF...');
        const uploadStatus = document.getElementById('uploadStatus');

        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
       
        if (response.ok) {
            documentText = data.text;
            document.getElementById('documentContent').textContent = documentText;
            document.querySelector('.chat-section').style.display = 'block';
            uploadStatus.innerHTML = '<span class="success">File uploaded successfully!</span>';
           
            // Clear previous messages
            document.getElementById('messageArea').innerHTML = '';
           
            // Add system message
            addMessage("I've processed your document. Feel free to ask any questions about it!", false);
        } else {
            uploadStatus.innerHTML = `<span class="error">${data.error || 'Error uploading file'}</span>`;
        }
    } catch (error) {
        console.error('Upload error:', error);
        document.getElementById('uploadStatus').innerHTML =
            `<span class="error">Error uploading file: ${error.message}</span>`;
    } finally {
        hideLoading();
    }
}

function addMessage(content, isUser = false) {
    const messageArea = document.getElementById('messageArea');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'} fade-in`;
    messageDiv.textContent = content;
    messageArea.appendChild(messageDiv);
    messageArea.scrollTop = messageArea.scrollHeight;
}

async function askQuestion() {
    const questionInput = document.getElementById('questionInput');
    const question = questionInput.value.trim();
   
    if (!question) {
        return;
    }

    try {
        // Add user's question to chat
        addMessage(question, true);
       
        // Clear input and show loading
        questionInput.value = '';
        showLoading('Thinking...');

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
            addMessage(data.answer, false);
        } else {
            addMessage(`Error: ${data.error || 'Failed to get answer'}`, false);
        }
    } catch (error) {
        console.error('Question error:', error);
        addMessage(`Error: ${error.message}`, false);
    } finally {
        hideLoading();
    }
}

function toggleContent() {
    const content = document.getElementById('documentContent');
    const button = document.querySelector('.document-header button i');
   
    if (content.style.display === 'none') {
        content.style.display = 'block';
        button.className = 'fas fa-chevron-down';
    } else {
        content.style.display = 'none';
        button.className = 'fas fa-chevron-up';
    }
}

// Add keyboard shortcut for asking questions
document.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        const questionInput = document.getElementById('questionInput');
        if (document.activeElement === questionInput) {
            e.preventDefault();
            askQuestion();
        }
    }
});