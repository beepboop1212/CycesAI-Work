# config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- BRANDING & CONSTANTS ---
COMPANY_NAME = "Realty of America"
COMPANY_LOGO_URL = "https://iili.io/FnwmFmF.png"

# --- API ENDPOINTS ---
BANNERBEAR_API_ENDPOINT = "https://api.bannerbear.com/v2"
FREEIMAGE_API_ENDPOINT = "https://freeimage.host/api/1/upload"

# --- API KEYS ---
BB_API_KEY = os.getenv("BANNERBEAR_API_KEY")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
FREEIMAGE_API_KEY = os.getenv("FREEIMAGE_API_KEY")