# llm_service.py
import streamlit as st
import json
import google.generativeai as genai # Import here
from config import GEMINI_MODEL_NAME # Import model name

# MODIFICATION_PROMPT_TEMPLATE should be defined here as it's specific to this service
MODIFICATION_PROMPT_TEMPLATE = """
You are an AI assistant helping a user modify a Bannerbear template.
The user wants to make a change. Your task is to understand their request and map it to one of the available template layers.

**User's Request:**
"{user_message}"

**Available Template Layers (Name and Type):**
{layers_description}

Based on the user's request and the available layers, determine:
1.  `layer_name`: The exact name of the layer the user most likely wants to modify from the "Available Template Layers". Choose the best match.
2.  `modification_type`: Must be one of "text", "image_url", or "color". Determine this from the layer's type in "Available Template Layers" and the user's intent.
3.  `new_value`: The new value for the modification.
    - If it's for "text", this is the new text string.
    - If it's for "image_url", and the user provides a URL, use that URL. If the user says they want to change an image but doesn't provide a URL (e.g., "change the logo", "use a new picture for main_image"), set `new_value` to "USER_UPLOAD_PENDING".
    - If it's for "color", this should be a hex color code (e.g., "#FF0000"). If the user says "blue", try to infer a common hex code like "#0000FF".

Output ONLY a single, valid JSON object with these three keys: "layer_name", "modification_type", and "new_value".
Do NOT include any other text, explanations, or markdown.

Example (Text):
User Request: "Change the headline to 'Summer Sale!'"
Available Layers:
- headline (Text)
- main_image (Image)
Your JSON Output: {{"layer_name": "headline", "modification_type": "text", "new_value": "Summer Sale!"}}

Example (Image URL provided):
User Request: "For main_image, use https://example.com/photo.jpg"
Available Layers:
- main_image (Image)
Your JSON Output: {{"layer_name": "main_image", "modification_type": "image_url", "new_value": "https://example.com/photo.jpg"}}

Example (Image upload implied):
User Request: "I want to change the main_image"
Available Layers:
- main_image (Image)
Your JSON Output: {{"layer_name": "main_image", "modification_type": "image_url", "new_value": "USER_UPLOAD_PENDING"}}
"""

def configure_gemini_model():
    """Configures and returns the Gemini model instance. To be called from app.py."""
    # API key should be configured in app.py before this is effectively used
    if st.session_state.get('google_api_key') and not st.session_state.get('gemini_model_instance'):
        try:
            genai.configure(api_key=st.session_state.google_api_key)
            st.session_state.gemini_model_instance = genai.GenerativeModel(GEMINI_MODEL_NAME)
            print("LLM Service: Gemini model instance configured.") # For server logs
            return st.session_state.gemini_model_instance
        except Exception as e:
            print(f"LLM Service ERROR: Failed to configure Gemini model: {e}")
            st.session_state.gemini_model_instance = None
            return None
    elif st.session_state.get('gemini_model_instance'):
        return st.session_state.gemini_model_instance
    else:
        print("LLM Service: Google API key not available in session_state for Gemini model setup.")
        return None


def parse_modification_request(user_message, available_layers_for_llm):
    """
    Sends the user's message and template layer info to Gemini for parsing.
    `available_layers_for_llm` should be a list of dictionaries like:
    [{'name': 'layer1', 'type': 'Text'}, {'name': 'layer2', 'type': 'Image'}]
    Returns (parsed_json, error_message)
    """
    model = st.session_state.get('gemini_model_instance') # Get from session_state
    if not model:
        return None, "Gemini model not available for parsing modification request."

    layers_description_str = "\n".join([f"- {layer['name']} ({layer['type']})" for layer in available_layers_for_llm])
    prompt_filled = MODIFICATION_PROMPT_TEMPLATE.format(
        user_message=user_message,
        layers_description=layers_description_str
    )
    
    response_obj = None # Initialize for error reporting
    response_text_debug = "" # For debugging
    try:
        # Spinner should be handled by the calling UI function in app.py
        response_obj = model.generate_content(prompt_filled)
        response_text_debug = response_obj.text
        
        # Clean the response to ensure it's valid JSON
        json_string = response_text_debug.strip()
        if json_string.startswith("```json"):
            json_string = json_string[7:]
        if json_string.endswith("```"):
            json_string = json_string[:-3]
        json_string = json_string.strip()
        
        parsed_json = json.loads(json_string)
        # Basic validation of the parsed structure
        if all(key in parsed_json for key in ["layer_name", "modification_type", "new_value"]):
            return parsed_json, None # Parsed data, Error message
        else:
            return None, f"LLM returned an unexpected JSON structure: {parsed_json}. Raw: {response_text_debug}"
            
    except json.JSONDecodeError as json_e:
        error_msg = f"LLM response was not valid JSON: {json_e}. Raw response: {response_text_debug}"
        return None, error_msg
    except Exception as e: # Catch other potential errors from Gemini API or processing
        error_msg = f"An error occurred during LLM call: {e}. Raw response: {response_text_debug}"
        # Check for specific Gemini API errors if possible from 'e'
        # For example, if hasattr(e, 'response') and e.response.prompt_feedback
        if hasattr(response_obj, 'prompt_feedback') and response_obj.prompt_feedback:
             error_msg += f" Prompt Feedback: {response_obj.prompt_feedback}"
        return None, error_msg