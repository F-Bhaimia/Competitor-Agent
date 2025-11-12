# app/summarize.py
from __future__ import annotations
import openai
import os
import pandas as pd
from tenacity import retry, wait_random_exponential, stop_after_attempt

# Load your OpenAI API key from environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

SYSTEM_PROMPT = """You are a market intelligence analyst.
Summarize competitor blog posts for an internal update report.
Focus on key points like product launches, pricing changes, partnerships, or strategy signals.
Respond in 2-3 sentences maximum, concise and factual."""

@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(3))
def generate_summary(article_text: str) -> str:
    """Generate a concise summary using GPT model."""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": article_text[:5000]},  # limit input size
            ],
            temperature=0.3,
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        print(f"Error summarizing: {e}")
        return ""
