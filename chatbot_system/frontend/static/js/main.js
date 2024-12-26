let documentText = '';

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
   
    const sunIcon = document.querySelector('.sun-icon');
    const moonIcon = document.querySelector('.moon-icon');
   
    if (theme === 'dark') {
        sunIcon.style.display = 'none';
        moonIcon.style.display = 'block';
    } else {
        sunIcon.style.display = 'block';
        moonIcon.style.display = 'none';
    }
}

function getCSRFToken() {
    return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
}

function showSuccess(message) {
    const uploadStatus = document.getElementById('uploadStatus');
    uploadStatus.className = 'success-message';
    uploadStatus.textContent = message;
}

function showError(message) {
    const uploadStatus = document.getElementById('uploadStatus');
    uploadStatus.className = 'error-message';
    uploadStatus.textContent = message;
}

function showLoading(message = 'Processing...') {
    const uploadStatus = document.getElementById('uploadStatus');
    uploadStatus.className = 'loading';
    uploadStatus.textContent = message;
}

async function uploadPDF() {
    const fileInput = document.getElementById('pdfFile');
    const file = fileInput.files[0];

    if (!file) {
        showError('Please select a file first!');
        return;
    }

    if (!file.name.toLowerCase().endsWith('.pdf') && !file.name.toLowerCase().endsWith('.docx')) {
        showError('Please select a PDF or DOCX file');
        return;
    }

    showLoading('Uploading file...');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken()  // Ensure this function retrieves the correct token
            },
            body: formData,
            credentials: 'same-origin'
        });

        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();

        documentText = data.text;
        document.getElementById('documentContent').textContent = documentText;

        const chatSection = document.querySelector('.chat-section');
        chatSection.style.opacity = '0';
        chatSection.style.display = 'block';
        setTimeout(() => {
            chatSection.style.transition = 'opacity 0.5s ease-in-out';
            chatSection.style.opacity = '1';
        }, 10);

        showSuccess('File uploaded successfully!');
        document.getElementById('questionInput').focus();

    } catch (error) {
        showError('Upload failed: ' + error.message);
        console.error('Upload error:', error);
    }
}


async function askQuestion() {
    const questionInput = document.getElementById('questionInput');
    const answerDiv = document.getElementById('answer');
    const question = questionInput.value.trim();
   
    if (!question) {
        answerDiv.className = 'answer-section error-message';
        answerDiv.textContent = 'Please enter a question!';
        questionInput.focus();
        return;
    }

    answerDiv.className = 'answer-section loading';
    answerDiv.textContent = 'Thinking...';

    try {
        const response = await fetch('/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                question: question,
                context: documentText
            })
        });

        const data = await response.json();
       
        if (response.ok) {
            answerDiv.className = 'answer-section';
            const confidencePercentage = (data.confidence * 100).toFixed(1);
            let warningMessage = data.warning ? `<p class="warning-text">${data.warning}</p>` : '';
            answerDiv.innerHTML = `
                <div class="answer-content">
                    <p class="answer-text">${data.answer}</p>
                    <div class="confidence-score">Confidence: ${confidencePercentage}%</div>
                    ${warningMessage}
                </div>
            `;
            questionInput.value = '';
            questionInput.focus();
            answerDiv.scrollIntoView({ behavior: 'smooth' });
        } else {
            answerDiv.className = 'answer-section error-message';
            answerDiv.textContent = data.error || 'Error getting answer';
        }
    } catch (error) {
        answerDiv.className = 'answer-section error-message';
        answerDiv.textContent = 'Error getting answer: ' + error.message;
        console.error('Question error:', error);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    setTheme(savedTheme);
   
    document.getElementById('themeToggle').addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        setTheme(currentTheme === 'dark' ? 'light' : 'dark');
    });
   
    const fileInput = document.getElementById('pdfFile');
    const uploadLabel = document.querySelector('.file-upload-label');
    const uploadSection = document.querySelector('.upload-section');
   
    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            uploadLabel.textContent = file.name;
            document.getElementById('uploadStatus').textContent = '';
        }
    });

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        uploadSection.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
        });
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        uploadSection.addEventListener(eventName, () => {
            uploadSection.classList.add('highlight');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        uploadSection.addEventListener(eventName, () => {
            uploadSection.classList.remove('highlight');
        });
    });

    uploadSection.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const file = dt.files[0];
        const fileInput = document.getElementById('pdfFile');
        fileInput.files = dt.files;
        fileInput.dispatchEvent(new Event('change'));
    });

    document.getElementById('questionInput').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            askQuestion();
        }
    });
});



function changeBackground() {
    const randomNumber = Math.floor(Math.random() * 6) + 1; // Update the number based on the total number of backgrounds
    document.body.className = `background-${randomNumber}`;
}

// Call the changeBackground function every 10 seconds to change the background dynamically
setInterval(changeBackground, 30000); // Change every 10 seconds (10000 milliseconds)

async function summarizeDocument() {
    const summaryDiv = document.getElementById('summary');
    summaryDiv.className = 'summary-section loading';
    summaryDiv.textContent = 'Summarizing...';

    try {
        const response = await fetch('/summarize', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                context: documentText
            })
        });

        const data = await response.json();

        if (response.ok) {
            summaryDiv.className = 'summary-section';
            summaryDiv.innerHTML = `
                <div class="summary-content">
                    <p class="summary-text">${data.summary}</p>
                </div>
            `;
            summaryDiv.scrollIntoView({ behavior: 'smooth' });
        } else {
            summaryDiv.className = 'summary-section error-message';
            summaryDiv.textContent = data.error || 'Error getting summary';
        }
    } catch (error) {
        summaryDiv.className = 'summary-section error-message';
        summaryDiv.textContent = 'Error getting summary: ' + error.message;
        console.error('Summary error:', error);
    }
}