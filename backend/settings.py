"""
LLM Configuration for KB Standalone Backend

This file configures the default LLM for all backend operations.
Switch between providers by modifying the LLM initialization below.
"""

import os
from langchain_groq import ChatGroq

# Get Groq API key from environment
groq_api_key = os.getenv('NEXT_PUBLIC_GROQ_API_KEY')
if not groq_api_key:
    raise ValueError(
        "NEXT_PUBLIC_GROQ_API_KEY not found in environment variables. "
        "Please add it to your .env file or Cloud Run environment variables."
    )

# Initialize Groq LLaMA 3.3 70B
# Benefits:
# - 128k context window
# - Very fast inference
# - 100k tokens/day free tier (should have reset by now)
# - Excellent for SQL reasoning
LLM = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.0,  # Deterministic responses
    groq_api_key=groq_api_key,
    max_tokens=8000,
    model_kwargs={'seed': 42}
)

print(f"✅ LLM configured: Groq LLaMA 3.3 70B (128k context window)")
