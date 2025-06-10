# config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file at the earliest
load_dotenv()

# API Endpoints
BANNERBEAR_API_ENDPOINT = "https://api.bannerbear.com/v2"
FREEIMAGE_API_ENDPOINT = "https://freeimage.host/api/1/upload"
GEMINI_MODEL_NAME = 'gemini-1.5-flash-latest'

# --- API Key Retrieval ---
# We'll manage API keys primarily through Streamlit's session state in app.py,
# but these functions can serve as helpers or be used if services need direct access.
def get_bannerbear_api_key():
    return os.getenv("BANNERBEAR_API_KEY")

def get_google_api_key():
    return os.getenv("GOOGLE_API_KEY")

def get_freeimage_api_key():
    return os.getenv("FREEIMAGE_API_KEY")

if __name__ == '__main__':
    # For testing if keys are loaded
    print(f"Bannerbear Key Loaded: {bool(get_bannerbear_api_key())}")
    print(f"Google Key Loaded: {bool(get_google_api_key())}")
    print(f"Freeimage Key Loaded: {bool(get_freeimage_api_key())}")