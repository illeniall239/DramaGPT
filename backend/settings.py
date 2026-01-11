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

# Initialize Gemini 2.0 Flash with billing-enabled API key
# Benefits:
# - 1M context window (1,048,576 tokens input)
# - 8,192 output token limit
# - 2M tokens/month FREE tier, then pay-as-you-go
# - Much higher rate limits than AI Studio free tier
# - Function calling, code execution, and grounding support
LLM = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.0,  # Deterministic responses
    google_api_key=google_api_key,
    max_output_tokens=8000,
    convert_system_message_to_human=True  # Required for Gemini
)

print(f"✅ LLM configured: Gemini 2.0 Flash (latest) with billing-enabled quotas")
