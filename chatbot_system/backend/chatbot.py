from flask import Flask, request, jsonify, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_seasurf import SeaSurf
from werkzeug.utils import secure_filename
from document_processor import extract_text_from_pdf
from transformers import pipeline, RagTokenizer, RagRetriever, RagSequenceForGeneration
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

# Load the summarization model
try:
    summarizer = pipeline("summarization")
    logger.info("Successfully loaded summarization model")
except Exception as e:
    logger.error(f"Error loading summarization model: {str(e)}")
    summarizer = None

# Load RAG components
try:
    tokenizer = RagTokenizer.from_pretrained("facebook/rag-sequence-nq")
    retriever = RagRetriever.from_pretrained("facebook/rag-sequence-nq", index_name="exact", passages_path="path/to/passages")
    rag_model = RagSequenceForGeneration.from_pretrained("facebook/rag-sequence-nq", retriever=retriever)
    logger.info("Successfully loaded RAG model")
except Exception as e:
    logger.error(f"Error loading RAG model: {str(e)}")
    rag_model = None

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

def detect_hallucination_rag(question, context):
    """Detect hallucination using RAG."""
    if not rag_model:
        logger.error("RAG model not available")
        return False

    inputs = tokenizer(question, return_tensors="pt")
    outputs = rag_model.generate(**inputs, num_return_sequences=1, num_beams=2)
    generated_answer = tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]

    # Compare generated answer with context
    similarity = util.pytorch_cos_sim(generated_answer, context).item()
    return similarity < 0.5  # Threshold for hallucination

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
    """Handle file upload and process the PDF."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
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
            return jsonify({"error": "No text could be extracted from the PDF"}), 400

        return jsonify({
            "message": "File processed successfully",
            "text": text
        }), 200

    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        return jsonify({"error": str(e)}), 500

    finally:
        # Clean up the temporary file
        if 'pdf_path' in locals() and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
                logger.info(f"Temporary file removed: {secure_name}")
            except Exception as e:
                logger.error(f"Error removing temporary file: {str(e)}")

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

            # Check for hallucination using RAG
            if detect_hallucination_rag(question, context):
                logger.warning("Potential hallucination detected.")
                return jsonify({
                    "answer": answer['answer'],
                    "confidence": round(answer['score'], 4),
                    "warning": "The answer may not be consistent with the document context."
                }), 200
            
            return jsonify({
                "answer": answer['answer'],
                "confidence": round(answer['score'], 4)
            }), 200

        except Exception as e:
            logger.error(f"Error generating answer: {str(e)}")
            return jsonify({"error": "Error generating answer"}), 500

    except Exception as e:
        logger.error(f"Ask question error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/summarize', methods=['POST'])
@limiter.limit("10 per minute")
def summarize_document():
    """Summarize the uploaded document's text."""
    try:
        if not summarizer:
            return jsonify({"error": "Summarization model not available"}), 503

        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        context = data.get("context", "").strip()

        if not context:
            return jsonify({"error": "Context is required for summarization"}), 400

        # Summarize the document
        summary = summarizer(context, max_length=130, min_length=30, do_sample=False)
        logger.debug(f"Generated summary: {summary}")

        return jsonify({
            "summary": summary[0]['summary_text']
        }), 200

    except Exception as e:
        logger.error(f"Summarization error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "model": "loaded"
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
    logger.error(f"Internal server error: {str(e)}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    logger.info("Starting application...")
    logger.info(f"Template folder: {app.template_folder}")
    logger.info(f"Static folder: {app.static_folder}")
    logger.info(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
    
    app.run(debug=True)