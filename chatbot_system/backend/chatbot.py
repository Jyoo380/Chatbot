from flask import Flask, request, jsonify, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_seasurf import SeaSurf
from werkzeug.utils import secure_filename
from document_processor import extract_text_from_pdf
import os
import secrets
import logging
from transformers import (
    AutoTokenizer, 
    AutoModelForQuestionAnswering,
    pipeline
)
from sentence_transformers import SentenceTransformer
import torch
import faiss
import numpy as np
from typing import List, Tuple, Dict, Optional
import re

# Constants - Updated for better models
EMBEDDING_MODEL = "microsoft/mpnet-base"  # Faster & more accurate embeddings
QA_MODEL = "facebook/bart-large-qa"       # Better for QA tasks
EMBEDDING_DIM = 768                       # MPNet dimension
CHUNK_SIZE = 384                          # Optimized for BART
TOP_K = 4                                 # Number of chunks to consider
MAX_FILE_SIZE = 16 * 1024 * 1024         # 16MB

# Get the absolute path to the project root directory
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

class EnhancedRAG:
    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"Initializing Enhanced RAG System on {self.device}...")
        
        try:
            # Initialize embedding model (MPNet)
            self.embed_model = SentenceTransformer(EMBEDDING_MODEL)
            self.embed_model.to(self.device)
            
            # Initialize QA pipeline (BART)
            self.qa_pipeline = pipeline(
                'question-answering',
                model=QA_MODEL,
                tokenizer=QA_MODEL,
                device=-1 if self.device.type == 'cpu' else 0,
                max_length=512,
                min_length=20,
                handle_long_generation=True
            )
            
            # Initialize FAISS index
            self.index = faiss.IndexFlatL2(EMBEDDING_DIM)
            
            # Storage for text chunks and their embeddings
            self.chunks: List[str] = []
            self.chunk_embeddings = None
            
            logger.info("Enhanced RAG System initialized successfully")
        except Exception as e:
            logger.error(f"Model initialization error: {str(e)}")
            raise

    def preprocess_text(self, text: str) -> str:
        """Clean and preprocess text with enhanced cleaning."""
        # Basic cleaning
        text = re.sub(r'\s+', ' ', text)
        text = text.replace('\n', ' ')
        
        # Fix common PDF extraction issues
        text = re.sub(r'([a-z])([A-Z])', r'\1. \2', text)  # Split likely sentences
        text = re.sub(r'\.{2,}', '.', text)                # Fix multiple periods
        text = re.sub(r'\s*\.\s*', '. ', text)            # Standardize period spacing
        
        # Remove special characters but keep essential punctuation
        text = re.sub(r'[^a-zA-Z0-9\s\.,;:?!-]', '', text)
        
        return text.strip()

    def create_chunks(self, text: str) -> List[str]:
        """Create overlapping chunks with improved sentence handling."""
        text = self.preprocess_text(text)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence_length = len(sentence.split())
            
            # Handle very long sentences
            if sentence_length > CHUNK_SIZE:
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = []
                    current_length = 0
                
                # Split long sentence into smaller parts
                words = sentence.split()
                for i in range(0, len(words), CHUNK_SIZE):
                    chunk = ' '.join(words[i:i + CHUNK_SIZE])
                    chunks.append(chunk)
                continue
            
            if current_length + sentence_length > CHUNK_SIZE:
                chunks.append(' '.join(current_chunk))
                # Keep last sentence for overlap
                current_chunk = [current_chunk[-1], sentence] if current_chunk else [sentence]
                current_length = len(' '.join(current_chunk).split())
            else:
                current_chunk.append(sentence)
                current_length += sentence_length
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks

    def index_document(self, text: str) -> bool:
        """Index document with improved error handling and chunking."""
        try:
            # Create chunks
            self.chunks = self.create_chunks(text)
            
            if not self.chunks:
                raise ValueError("No chunks created from document")
            
            logger.info(f"Created {len(self.chunks)} chunks")
            
            # Generate embeddings with batching
            chunk_embeddings = []
            batch_size = 8
            
            for i in range(0, len(self.chunks), batch_size):
                batch = self.chunks[i:i + batch_size]
                batch_embeddings = self.embed_model.encode(
                    batch,
                    convert_to_tensor=True,
                    show_progress_bar=False
                )
                chunk_embeddings.append(batch_embeddings)
            
            # Combine all embeddings
            self.chunk_embeddings = torch.cat(chunk_embeddings).cpu().numpy()
            
            # Normalize embeddings
            faiss.normalize_L2(self.chunk_embeddings)
            
            # Reset and add to FAISS index
            self.index = faiss.IndexFlatL2(EMBEDDING_DIM)
            self.index.add(self.chunk_embeddings)
            
            logger.info(f"Successfully indexed {len(self.chunks)} chunks")
            return True
            
        except Exception as e:
            logger.error(f"Indexing error: {str(e)}")
            return False