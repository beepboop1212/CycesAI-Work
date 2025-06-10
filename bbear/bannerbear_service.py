# bannerbear_service.py
import streamlit as st
import requests
import time
import json # For logging payload
from config import BANNERBEAR_API_ENDPOINT # Import endpoint from config

# --- Helper to get headers ---
def _get_bb_headers():
    # Access API key from session state, which should be initialized in app.py
    api_key = st.session_state.get('bannerbear_api_key')
    if not api_key:
        st.error("Bannerbear API Key not available in session state for API call.")
        return None
    return {"Authorization": f"Bearer {api_key}"}

# --- Cached Template Fetching ---
@st.cache_data(ttl=3600, show_spinner=False) # Cache for 1 hour
def fetch_all_templates_cached():
    """Cached function to fetch all Bannerbear templates."""
    headers = _get_bb_headers()
    if not headers: return None, "Bannerbear API Key not configured for fetching templates."
    
    response_obj = None
    try:
        response_obj = requests.get(f"{BANNERBEAR_API_ENDPOINT}/templates", headers=headers)
        response_obj.raise_for_status()
        return response_obj.json(), None # Data, Error message
    except requests.exceptions.HTTPError as http_err:
        error_message = f"Bannerbear API Error (Fetching Templates): {http_err}. "
        if response_obj is not None: error_message += f"Response: {response_obj.status_code} - {response_obj.text}"
        return None, error_message
    except requests.exceptions.RequestException as e:
        return None, f"Connection Error (Fetching Templates): {e}"

# --- Specific Template Details ---
# No caching here as it's usually for an interactive selection, but could be added.
def fetch_template_details(template_uid):
    """Fetches details for a specific Bannerbear template."""
    headers = _get_bb_headers()
    if not headers: return None, "Bannerbear API Key not configured."
    if not template_uid: return None, "No Template UID provided for fetching details."

    response_obj = None
    url_to_fetch = f"{BANNERBEAR_API_ENDPOINT}/templates/{template_uid}"
    try:
        # Spinner can be managed by the calling UI function in app.py
        response_obj = requests.get(url_to_fetch, headers=headers)
        response_obj.raise_for_status()
        return response_obj.json(), None
    except requests.exceptions.HTTPError as http_err:
        error_message = f"Bannerbear API Error (Details for {template_uid}): {http_err}. "
        if response_obj is not None: error_message += f"Response: {response_obj.status_code} - {response_obj.text}"
        return None, error_message
    except requests.exceptions.RequestException as e:
        return None, f"Connection Error (Details for {template_uid}): {e}"

# --- Image Generation ---
def generate_image(template_uid, modifications):
    """Generates an image using Bannerbear (sync=true) and returns initial response."""
    headers = _get_bb_headers()
    if not headers: return None, "Bannerbear API Key missing for generation."
    if not template_uid: return None, "Template UID missing for generation."

    payload = {"template": template_uid, "modifications": modifications}
    url_to_post = f"{BANNERBEAR_API_ENDPOINT}/images?sync=true"
    
    # Logging the payload can be done in app.py before calling this, or passed as a callback
    # For now, we keep service clean, app.py can log it to chat if needed.
    # print(f"DEBUG BB Service: Sending payload to {url_to_post}: {json.dumps(payload, indent=2)}")

    response_obj = None
    try:
        response_obj = requests.post(url_to_post, headers=headers, json=payload)
        response_obj.raise_for_status()
        return response_obj.json(), None
    except requests.exceptions.HTTPError as http_err:
        error_message = f"Bannerbear API Error (Image Generation): {http_err}. "
        if response_obj is not None: error_message += f"Response: {response_obj.status_code} - {response_obj.text}"
        return None, error_message
    except requests.exceptions.RequestException as e:
        return None, f"Connection Error (Image Generation): {e}"

# --- Image Polling ---
def poll_image_completion(image_uid, max_retries=20, delay_seconds=3):
    """Polls Bannerbear for image completion status."""
    headers = _get_bb_headers()
    if not headers: return None, "Bannerbear API Key missing for polling."
    
    url = f"{BANNERBEAR_API_ENDPOINT}/images/{image_uid}"
    
    # Polling messages should be handled by app.py by adding to chat history
    # This function will just return the final URL or error.
    
    response_poll_obj = None
    for attempt in range(max_retries):
        try:
            response_poll_obj = requests.get(url, headers=headers)
            response_poll_obj.raise_for_status()
            data = response_poll_obj.json()

            if data.get("status") == "completed":
                return data.get("image_url_png"), None # URL, Error
            elif data.get("status") == "failed":
                return None, f"Image {image_uid} generation failed on Bannerbear's side. Details: {data.get('failure_reason_code', data)}"
            elif data.get("status") == "pending":
                # Inform app.py about pending status so it can update chat
                st.session_state.last_poll_status = f"pending_attempt_{attempt+1}" 
                if attempt < max_retries -1:
                    time.sleep(delay_seconds)
            else: # Unexpected status
                st.session_state.last_poll_status = f"unexpected_status_{data.get('status')}"
                time.sleep(delay_seconds) 
        except requests.exceptions.HTTPError as http_err:
            err_msg = f"HTTP error polling for image {image_uid}: {http_err}. "
            if response_poll_obj is not None: err_msg += f"Response: {response_poll_obj.status_code}, {response_poll_obj.text}"
            return None, err_msg
        except requests.exceptions.RequestException as e:
            return None, f"Connection Error polling for image {image_uid}: {e}"
        except Exception as e_gen: # Catch broader exceptions during polling
            return None, f"Generic error during polling for {image_uid}: {str(e_gen)}"
            
    return None, f"Image {image_uid} generation timed out after {max_retries * delay_seconds} seconds."