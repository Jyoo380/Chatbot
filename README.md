# Chatbot
# Document Q&A Chatbot

This application is a web-based chatbot system built using Flask, designed to process and analyze documents. Users can upload PDF or DOCX files, and the app extracts text for question answering and summarization using NLP models.

## Features
- **File Upload**: Supports PDF and DOCX formats.
- **Question Answering**: Utilizes the "deepset/roberta-base-squad2" model for accurate responses.
- **Summarization**: Generates concise summaries of document content.
- **Security**: Implements CSRF protection and other security headers.
- **Logging**: Provides detailed logs for monitoring and debugging.

## Setup
Run `pip install -r requirements.txt` to install dependencies, then start the app with `python chatbot.py`.
