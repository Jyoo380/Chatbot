from flask import Flask, request, jsonify, render_template
from document_processor import extract_text_from_pdf
import os
import requests
import logging
from werkzeug.utils import secure_filename

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Get the absolute path to the project root directory
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__,
    template_folder=os.path.join(ROOT_DIR, 'frontend', 'templates'),
    static_folder=os.path.join(ROOT_DIR, 'frontend', 'static')
)

# Configuration
UPLOAD_FOLDER = os.path.join(ROOT_DIR, "temp")
ALLOWED_EXTENSIONS = {'pdf'}
OLLAMA_API_URL = "http://localhost:11434/api/generate"

# Create temp directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def ask_ollama(question, context):
    """Query Ollama API with the question and context."""
    prompt = f"""Based on the following context, please answer the question.
    Context: {context}
   
    Question: {question}
   
    Answer: """
   
    try:
        response = requests.post(OLLAMA_API_URL, json={
            "model": "llama2",
            "prompt": prompt,
            "temperature": 0.7
        })
       
        if response.status_code == 200:
            return response.json()['response']
        else:
            raise Exception(f"Ollama API returned status code {response.status_code}")
           
    except requests.exceptions.ConnectionError:
        raise Exception("Could not connect to Ollama. Make sure it's running on localhost:11434")

@app.route('/')
def index():
    """Serve the main page."""
    try:
        logger.debug(f"Template folder: {app.template_folder}")
        logger.debug(f"Looking for template: {os.path.join(app.template_folder, 'index.html')}")
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering template: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and process the PDF."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
   
    if not allowed_file(file.filename):
        return jsonify({"error": "Only PDF files are supported"}), 400

    try:
        # Secure the filename and save the file
        filename = secure_filename(file.filename)
        pdf_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(pdf_path)

        # Extract text from the PDF
        text = extract_text_from_pdf(pdf_path)
       
        # Clean up the temporary file
        os.remove(pdf_path)

        if not text.strip():
            return jsonify({"error": "No text could be extracted from the PDF"}), 400

        return jsonify({
            "message": "File uploaded and processed successfully.",
            "text": text
        }), 200
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        # Clean up the file if it exists
        if 'pdf_path' in locals() and os.path.exists(pdf_path):
            os.remove(pdf_path)
        return jsonify({"error": str(e)}), 500

@app.route('/ask', methods=['POST'])
def ask_question():
    """Answer a question based on the uploaded document's text."""
    try:
        data = request.json
        question = data.get("question")
        context = data.get("context")

        if not question or not context:
            return jsonify({"error": "Question and context are required"}), 400

        logger.debug(f"Received question: {question}")
        answer = ask_ollama(question, context)
        logger.debug(f"Generated answer: {answer}")

        return jsonify({"answer": answer}), 200
       
    except Exception as e:
        logger.error(f"Error processing question: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint."""
    try:
        # Test Ollama connection
        requests.post(OLLAMA_API_URL, json={
            "model": "llama2",
            "prompt": "test"
        })
        return jsonify({"status": "healthy", "ollama": "connected"}), 200
    except requests.exceptions.ConnectionError:
        return jsonify({
            "status": "unhealthy",
            "ollama": "not connected",
            "message": "Could not connect to Ollama. Make sure it's running on localhost:11434"
        }), 503

if __name__ == '__main__':
    logger.info(f"Starting application...")
    logger.info(f"Template folder: {app.template_folder}")
    logger.info(f"Static folder: {app.static_folder}")
    logger.info(f"Upload folder: {UPLOAD_FOLDER}")
   
    # Check if Ollama is running
    try:
        requests.post(OLLAMA_API_URL, json={"model": "llama2", "prompt": "test"})
        logger.info("Successfully connected to Ollama")
    except requests.exceptions.ConnectionError:
        logger.warning("Could not connect to Ollama. Make sure it's running on localhost:11434")
   
    app.run(debug=True)
