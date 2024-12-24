from flask import Flask, request, jsonify
from document_processor import extract_text_from_pdf
from transformers import pipeline
import os

app = Flask(__name__)

# Create temp directory if it doesn't exist
os.makedirs("./temp", exist_ok=True)

# Load the question-answering model
qa_pipeline = pipeline("question-answering", model="deepset/roberta-base-squad2")

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and process the PDF."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if not file.filename.endswith('.pdf'):
        return jsonify({"error": "Only PDF files are supported"}), 400

    try:
        # Save the uploaded PDF file temporarily
        pdf_path = os.path.join("./temp", file.filename)
        file.save(pdf_path)

        # Extract text from the PDF
        text = extract_text_from_pdf(pdf_path)
        
        # Clean up the temporary file
        os.remove(pdf_path)

        return jsonify({
            "message": "File uploaded and processed successfully.", 
            "text": text
        }), 200
    except Exception as e:
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

        answer = qa_pipeline(question=question, context=context)
        return jsonify(answer), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)