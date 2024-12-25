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
    const files = fileInput.files;

    if (!files || files.length === 0) {
        showError('Please select at least one file!');
        return;
    }

    for (const file of files) {
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            showError('Only PDF files are allowed!');
            return;
        }
    }

    showLoading('Uploading files...');

    const formData = new FormData();
    for (const file of files) {
        formData.append('files', file); // Use 'files' to send multiple files
    }

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken(),
            },
            body: formData,
            credentials: 'same-origin',
        });

        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);

        const data = await response.json();
        if (data.texts && Array.isArray(data.texts)) {
            // Join all extracted text into one variable
            documentText = data.texts.join('\n\n');
            document.getElementById('documentContent').textContent = documentText;

            const chatSection = document.querySelector('.chat-section');
            chatSection.style.opacity = '0';
            chatSection.style.display = 'block';
            setTimeout(() => {
                chatSection.style.transition = 'opacity 0.5s ease-in-out';
                chatSection.style.opacity = '1';
            }, 10);

            showSuccess('Files uploaded successfully!');
            document.getElementById('questionInput').focus();
        } else {
            showError(data.error || 'Error processing files.');
        }
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
            answerDiv.innerHTML = `
                <div class="answer-content">
                    <p class="answer-text">${data.answer}</p>
                    <div class="confidence-score">Confidence: ${confidencePercentage}%</div>
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
        const files = e.target.files;
        if (files.length > 0) {
            const fileNames = Array.from(files).map(file => file.name).join(', ');
            uploadLabel.textContent = fileNames;
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
        const files = dt.files;
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