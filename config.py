"""
Configuration for the Financial Statement Translation Pipeline.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # Load .env file

# PwC GenAI Gateway
GENAI_BASE_URL = os.environ.get(
    "GENAI_BASE_URL",
    "https://genai-sharedservice-americas.pwcinternal.com",
)
GENAI_API_KEY = os.environ.get("PwC_LLM_API_KEY", "")
GENAI_MODEL = os.environ.get(
    "PwC_LLM_MODEL",
    "bedrock.anthropic.claude-sonnet-4-6",
)

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(BASE_DIR, "files")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# Review
MAX_REVIEW_ITERATIONS = 3
NUMBER_TOLERANCE = 1  # allowed rounding difference

# Translation
TRANSLATE_WITHOUT_API = True  # if True, use glossary/IFRS only (no API calls)
