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
import spacy
from sentence_transformers import SentenceTransformer, util

# Load spaCy English model
nlp = spacy.load("en_core_web_sm")

# Load SentenceTransformer model
similarity_model = SentenceTransformer('all-MiniLM-L6-v2')

def calculate_semantic_similarity(text1, text2):
    """Calculate cosine similarity between two texts."""
    embeddings1 = similarity_model.encode(text1, convert_to_tensor=True)
    embeddings2 = similarity_model.encode(text2, convert_to_tensor=True)
    cosine_sim = util.pytorch_cos_sim(embeddings1, embeddings2)
    return cosine_sim.item()

def extract_entities(text):
    """Extract named entities from text using spaCy."""
    doc = nlp(text)
    return set(ent.text for ent in doc.ents)

def detect_hallucinations(answer, context_entities):
    """Detect hallucinated entities in the answer."""
    answer_entities = extract_entities(answer)
    hallucinated = answer_entities - context_entities
    return hallucinated

def detect_semantic_inconsistency(answer, context):
    """Detect if the answer is semantically inconsistent with the context."""
    similarity_score = calculate_semantic_similarity(answer, context)
    threshold = 0.1
    return similarity_score < threshold, similarity_score

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
    """Handle file upload and process the PDF."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    is_valid, error_message = validate_file(file)
    
    if not is_valid:
        return jsonify({"error": error_message}), 400

    try:
        secure_name = secure_temp_file(file.filename)
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
        file.save(pdf_path)
        logger.info(f"File saved successfully: {secure_name}")

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

        context_entities = extract_entities(context)

        logger.debug(f"Processing question: {question}")
        
        try:
            answer = qa_pipeline(question=question, context=context, handle_impossible_answer=True)
            generated_answer = answer.get('answer', '')
            supporting_text = answer.get('context', '')
            confidence_score = round(answer.get('score', 0.0), 4)
            if not generated_answer:
                generated_answer = "I'm sorry, I couldn't find the answer to your question. We prevent HALLUCINATIONS"

            similarity_with_support = calculate_semantic_similarity(generated_answer, supporting_text)
            threshold_support = 0.1
            is_support_inconsistent = similarity_with_support < threshold_support

            if is_support_inconsistent:
                inconsistency_warning = f"Warning: The answer may be inconsistent with the supporting text (Similarity Score: {similarity_with_support:.2f})."
                logger.warning(inconsistency_warning)
            else:
                inconsistency_warning = None

            hallucinated_entities = detect_hallucinations(generated_answer, context_entities)
            if hallucinated_entities:
                logger.warning(f"Hallucinated entities detected: {hallucinated_entities}")
                hallucination_warning = f"Warning: The answer contains entities not found in the document: {', '.join(hallucinated_entities)}"
            else:
                hallucination_warning = None

            response = {
                "answer": generated_answer,
                "confidence": confidence_score
            }

            if hallucination_warning:
                response["hallucination_warning"] = hallucination_warning
            if inconsistency_warning:
                response["inconsistency_warning"] = inconsistency_warning

            return jsonify(response), 200
            
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
    
    app.run(debug=True)  # Set to False in production