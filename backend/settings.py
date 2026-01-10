"""
LLM Configuration for KB Standalone Backend

This file configures the default LLM for all backend operations.
Switch between providers by modifying the LLM initialization below.
"""

import os
from langchain_google_genai import ChatGoogleGenerativeAI

# Get Google API key from environment
google_api_key = os.getenv('GOOGLE_API_KEY')
if not google_api_key:
    raise ValueError(
        "GOOGLE_API_KEY not found in environment variables. "
        "Please add it to your .env file or Cloud Run environment variables."
    )

# Initialize Gemini 2.0 Flash
# Benefits:
# - 1M context window (vs 128k for Groq)
# - Higher rate limits
# - Free tier available
# - Excellent reasoning capabilities
LLM = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-exp",  # Latest Gemini 2.0 Flash experimental
    temperature=0.0,  # Deterministic responses
    google_api_key=google_api_key,
    max_output_tokens=8000,
    convert_system_message_to_human=True  # Required for Gemini
)

print(f"✅ LLM configured: Gemini 2.0 Flash (1M context window)")
