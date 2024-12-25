from flask import Flask, request, jsonify, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_seasurf import SeaSurf
from werkzeug.utils import secure_filename
from document_processor import extract_text_from_pdf
from transformers import pipeline
import os
import hashlib
import secrets
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Get the absolute path to the project root directory
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__,
    template_folder=os.path.join(ROOT_DIR, 'frontend', 'templates'),
    static_folder=os.path.join(ROOT_DIR, 'frontend', 'static')
)

# Security configurations
app.config.update(
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max file size
    SECRET_KEY=secrets.token_hex(32),
    UPLOAD_FOLDER=os.path.join(ROOT_DIR, "temp"),
    ALLOWED_EXTENSIONS={'pdf'},
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=1800,  # 30 minutes
    # Add CSRF settings
    WTF_CSRF_ENABLED=True,
    WTF_CSRF_SSL_STRICT=True
)

# Initialize security extensions
csrf = SeaSurf(app)

# Add CSRF error handler
@app.errorhandler(400)
def csrf_error(reason):
    logger.warning(f"CSRF Error: {reason}")
    return jsonify({
        "error": "CSRF validation failed. Please refresh the page and try again."
    }), 400

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Create temp directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Load the question-answering model
try:
    qa_pipeline = pipeline("question-answering", model="deepset/roberta-base-squad2")
    logger.info("Successfully loaded QA model")
except Exception as e:
    logger.error(f"Error loading QA model: {str(e)}")
    qa_pipeline = None

def secure_temp_file(filename):
    """Generate secure temporary filename."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    hash_name = hashlib.sha256(
        f"{filename}{secrets.token_hex(16)}{timestamp}".encode()
    ).hexdigest()
    return f"{hash_name}.pdf"

def validate_file(file):
    """Validate file type and content."""
    if not file or file.filename == '':
        return False, "No file selected"
    
    # Check file extension
    if not file.filename.lower().endswith('.pdf'):
        return False, "Only PDF files are supported"
    
    return True, None

@app.route('/')
def index():
    """Render the main page."""
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering template: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/upload', methods=['POST'])
@limiter.limit("10 per minute")
def upload_file():
    """Handle file upload and process multiple PDFs."""
    if 'files' not in request.files:
        return jsonify({"error": "No files part"}), 400

    files = request.files.getlist('files')  # Get all files

    if not files:
        return jsonify({"error": "No files selected"}), 400

    # Process each file
    all_texts = []
    for file in files:
        is_valid, error_message = validate_file(file)
        if not is_valid:
            return jsonify({"error": error_message}), 400

        try:
            # Generate secure filename and save
            secure_name = secure_temp_file(file.filename)
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
            file.save(pdf_path)
            logger.info(f"File saved successfully: {secure_name}")

            # Extract text from the PDF
            text = extract_text_from_pdf(pdf_path)
            
            if not text.strip():
                logger.warning(f"No text extracted from file: {secure_name}")
                continue  # Skip files with no extracted text

            all_texts.append(text)

        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {str(e)}")
            return jsonify({"error": f"Error processing file {file.filename}: {str(e)}"}), 500

        finally:
            # Clean up the temporary file
            if 'pdf_path' in locals() and os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                    logger.info(f"Temporary file removed: {secure_name}")
                except Exception as e:
                    logger.error(f"Error removing temporary file: {str(e)}")

    if all_texts:
        return jsonify({
            "message": "Files processed successfully",
            "texts": all_texts  # Return the extracted text from all PDFs
        }), 200
    else:
        return jsonify({"error": "No text extracted from any file"}), 400
    
@app.route('/ask', methods=['POST'])
@limiter.limit("30 per minute")
def ask_question():
    """Answer a question based on the uploaded document's text."""
    try:
        if not qa_pipeline:
            return jsonify({"error": "QA model not available"}), 503

        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        question = data.get("question", "").strip()
        context = data.get("context", "").strip()

        if not question or not context:
            return jsonify({"error": "Question and context are required"}), 400

        # Validate input lengths
        if len(question) > 1000:
            return jsonify({"error": "Question too long (max 1000 characters)"}), 400
        if len(context) > 100000:
            return jsonify({"error": "Context too long (max 100000 characters)"}), 400

        # Validate for potentially malicious characters
        injection_characters = [
            "'", "\"", "--", "/*", "*/", ";", "(", ")", "=", "<", ">", "!=", 
            "LIKE", "UNION", "||", "\\", "|", "&", "`", "$", "*", "[", "]", 
            "&&", ">", ">>", "\r", "\n", "{", "}", ":", ","
        ]
        if any(char in question for char in injection_characters):
            logger.warning(f"Malicious input detected in question: {question}")
            return jsonify({"error": "The given text may contain malicious content. Please revise your question."}), 400

        logger.debug(f"Processing question: {question}")
        
        # Get answer from model
        try:
            answer = qa_pipeline(question=question, context=context)
            logger.debug(f"Generated answer: {answer}")
            
            return jsonify({
                "answer": answer['answer'],
                "confidence": round(answer['score'], 4)
            }), 200
            
        except Exception as e:
            logger.error(f"Model error: {str(e)}")
            return jsonify({"error": "Error processing question"}), 500

    except Exception as e:
        logger.error(f"Ask question error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "model": "loaded" if qa_pipeline else "not loaded"
    }), 200

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(405)
def method_not_allowed_error(error):
    return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "File too large (max 16MB)"}), 413

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        "error": "Rate limit exceeded",
        "retry_after": int(e.description.split('in')[1].split('seconds')[0].strip())
    }), 429

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    logger.info("Starting application...")
    logger.info(f"Template folder: {app.template_folder}")
    logger.info(f"Static folder: {app.static_folder}")
    logger.info(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
    
    app.run(debug=True)