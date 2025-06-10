# freeimage_service.py
import streamlit as st
import requests
import base64
from config import FREEIMAGE_API_ENDPOINT # Import endpoint from config

def _get_fi_api_key():
    # Access API key from session state, initialized in app.py
    api_key = st.session_state.get('freeimage_api_key')
    if not api_key:
        st.error("Freeimage.host API Key not available in session state.")
        return None
    return api_key

def upload_image(uploaded_file_object):
    """Uploads a file object to freeimage.host and returns its public URL or an error message."""
    api_key = _get_fi_api_key()
    if not api_key: return None, "Freeimage.host API Key not configured."
    if not uploaded_file_object: return None, "No file object provided for upload."

    response_obj = None
    try:
        image_bytes = uploaded_file_object.getvalue()
        b64_image = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"key": api_key, "source": b64_image, "format": "json"}
        
        # Spinner can be managed by calling UI function in app.py
        response_obj = requests.post(FREEIMAGE_API_ENDPOINT, data=payload, timeout=60) # Increased timeout
        response_obj.raise_for_status()
        result = response_obj.json()

        if result.get("status_code") == 200 and result.get("image") and result["image"].get("url"):
            return result["image"]["url"], None # URL, Error message
        else:
            error_detail = result.get("error", {}).get("message", "Unknown error from freeimage.host")
            return None, f"Freeimage.host upload failed. Response: {error_detail}. Full API Response: {result}"
            
    except requests.exceptions.HTTPError as http_err:
        error_msg = f"HTTP error uploading to Freeimage.host: {http_err}. "
        if response_obj is not None: error_msg += f"Status: {response_obj.status_code}, Text: {response_obj.text}"
        return None, error_msg
    except requests.exceptions.RequestException as req_e:
        return None, f"Connection Error uploading to Freeimage.host: {req_e}"
    except Exception as e: # Catch broader exceptions
        return None, f"An unexpected error occurred during freeimage.host upload: {e}"