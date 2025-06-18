# api_utils.py
import streamlit as st
import requests
import time
import base64
import logging
from config import BANNERBEAR_API_ENDPOINT, FREEIMAGE_API_ENDPOINT

logger = logging.getLogger(__name__)

def bb_headers(api_key):
    """Generates authorization headers for Bannerbear API."""
    return {"Authorization": f"Bearer {api_key}"}

@st.cache_resource(show_spinner="Loading designs...") # UPDATED: More neutral spinner text
def load_all_template_details(api_key):
    """Fetches details for all available Bannerbear templates."""
    if not api_key:
        st.error("Bannerbear API Key is missing. Cannot load designs.", icon="🛑")
        return None
    try:
        summary_response = requests.get(f"{BANNERBEAR_API_ENDPOINT}/templates", headers=bb_headers(api_key), timeout=15)
        summary_response.raise_for_status()
        return [
            requests.get(f"{BANNERBEAR_API_ENDPOINT}/templates/{t['uid']}", headers=bb_headers(api_key)).json()
            for t in summary_response.json() if t and 'uid' in t
        ]
    except requests.exceptions.RequestException as e:
        st.error(f"Could not connect to the design service: {e}", icon="🚨")
        return None

# --- No other changes below this line in this file ---
def create_image_async(api_key, template_uid, modifications):
    """Initiates an asynchronous image creation job on Bannerbear."""
    payload = {"template": template_uid, "modifications": modifications}
    try:
        response = requests.post(f"{BANNERBEAR_API_ENDPOINT}/images", headers=bb_headers(api_key), json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API Error creating image: {e}")
        return None

def poll_for_image_completion(api_key, image_object):
    """Polls Bannerbear for the status of an image generation job."""
    polling_url = image_object.get("self")
    if not polling_url: return None

    for _ in range(30):
        time.sleep(1)
        try:
            response = requests.get(polling_url, headers=bb_headers(api_key))
            response.raise_for_status()
            polled_object = response.json()
            if polled_object.get('status') == 'completed':
                return polled_object
            if polled_object.get('status') == 'failed':
                logger.error(f"Image generation failed on Bannerbear's side: {polled_object}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"API Error polling for image: {e}")
            return None
    return None

def upload_image_to_public_url(api_key, image_bytes):
    """Uploads image bytes to a public hosting service (FreeImage.host)."""
    if not api_key:
        st.error("Image hosting API key is missing. Cannot upload files.", icon="❌")
        return None
    try:
        b64_image = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"key": api_key, "source": b64_image, "format": "json"}
        response = requests.post(FREEIMAGE_API_ENDPOINT, data=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        if result.get("status_code") == 200 and result.get("image"):
            return result["image"]["url"]
        else:
            logger.error(f"Image hosting service returned an error: {result}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Connection error during image upload: {e}")
        return None