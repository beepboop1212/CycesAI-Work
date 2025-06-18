# app.py
import streamlit as st
import logging

import config
import api_utils
import ai_core

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 1. INITIALIZATION & SESSION STATE ---
def initialize_app():
    """Sets up the Streamlit page and initializes session state variables."""
    st.set_page_config(page_title=f"{config.COMPANY_NAME} AI", layout="centered", page_icon="🏠")
    st.image(config.COMPANY_LOGO_URL, width=700)
    st.title("ROA.AI")

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": f"Hello! I'm your AI design assistant from {config.COMPANY_NAME}. How can I help you create marketing materials today?"}]
    if "gemini_model" not in st.session_state:
        st.session_state.gemini_model = ai_core.get_gemini_model_with_tool(config.GEMINI_API_KEY)
    if "rich_templates_data" not in st.session_state:
        st.session_state.rich_templates_data = api_utils.load_all_template_details(config.BB_API_KEY)
    if "design_context" not in st.session_state:
        st.session_state.design_context = {"template_uid": None, "modifications": []}
    if "staged_file_bytes" not in st.session_state:
        st.session_state.staged_file_bytes = None
    if "file_was_processed" not in st.session_state:
        st.session_state.file_was_processed = False

# --- 2. CORE LOGIC HANDLERS ---
def handle_ai_decision(decision: dict) -> str:
    """Processes the AI's decision and returns the final text response."""
    action = decision.get("action")
    response_text = decision.get("response_text", "I'm not sure how to proceed.")
    trigger_generation = False

    if action == "MODIFY":
        new_template_uid = decision.get("template_uid")
        if new_template_uid and new_template_uid != st.session_state.design_context.get("template_uid"):
            if st.session_state.design_context.get("template_uid"):
                trigger_generation = True
            st.session_state.design_context["template_uid"] = new_template_uid
        
        current_mods = {mod['name']: mod for mod in st.session_state.design_context.get('modifications', [])}
        for new_mod in decision.get("modifications", []):
            current_mods[new_mod['name']] = dict(new_mod)
        st.session_state.design_context["modifications"] = list(current_mods.values())

    elif action == "GENERATE":
        trigger_generation = True

    elif action == "RESET":
        st.session_state.design_context = {"template_uid": None, "modifications": []}
        return response_text

    if trigger_generation:
        context = st.session_state.design_context
        if not context.get("template_uid"):
            return "I can't generate an image yet. Please describe the design you want so I can pick a template."

        with st.spinner("Creating your design..."): # Neutral spinner
            initial_response = api_utils.create_image_async(config.BB_API_KEY, context['template_uid'], context['modifications'])
            if not initial_response:
                return "❌ **Error:** I couldn't start the image generation process."

            final_image = api_utils.poll_for_image_completion(config.BB_API_KEY, initial_response)
            if final_image and final_image.get("image_url_png"):
                response_text += f"\n\n![Generated Image]({final_image['image_url_png']})"
            else:
                response_text = "❌ **Error:** The image generation timed out or failed. Please try again."

    return response_text

def process_user_input(prompt: str) -> str:
    """
    Handles file upload, calls AI, processes decision, and returns the final response string.
    """
    final_prompt_for_ai = prompt
    if st.session_state.staged_file_bytes:
        with st.spinner("Uploading your image..."):
            image_url = api_utils.upload_image_to_public_url(config.FREEIMAGE_API_KEY, st.session_state.staged_file_bytes)
            st.session_state.staged_file_bytes = None
            if image_url:
                final_prompt_for_ai = f"Image context: The user has uploaded an image, its URL is {image_url}. Their text command is: '{prompt}'"
                st.session_state.file_was_processed = True
            else:
                return "Sorry, there was an error uploading your image. Please try again."

    with st.spinner(" "): # General spinner for AI call
        ai_response = ai_core.get_ai_decision(
            st.session_state.gemini_model, st.session_state.messages, final_prompt_for_ai,
            st.session_state.rich_templates_data, st.session_state.design_context
        )

    try:
        if ai_response and ai_response.candidates and ai_response.candidates[0].content.parts[0].function_call:
            decision = dict(ai_response.candidates[0].content.parts[0].function_call.args)
            logger.info(f"AI decision: {decision}")
            return handle_ai_decision(decision)
        else:
            logger.error(f"AI did not return a valid function call. Response: {ai_response}")
            return "I'm not sure how to respond to that. Can you clarify what design action you want to take?"
    except (AttributeError, IndexError, TypeError) as e:
        logger.error(f"Error parsing AI response: {e}\nFull Response: {ai_response}")
        return "I'm sorry, I had a problem. Could you please rephrase your request?"


# --- 3. MAIN APPLICATION FLOW ---

initialize_app()

if not all([st.session_state.gemini_model, st.session_state.rich_templates_data, config.BB_API_KEY, config.FREEIMAGE_API_KEY]):
    st.error("Application cannot start. Check API keys and restart.", icon="🛑")
    st.stop()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"], unsafe_allow_html=True)

uploaded_file = st.file_uploader("Attach an image (e.g., a listing photo or headshot)", type=["png", "jpg", "jpeg"])
if uploaded_file:
    if not st.session_state.file_was_processed:
        st.session_state.staged_file_bytes = uploaded_file.getvalue()
        st.success("✅ Image attached! It will be included with your next message.")

if "processing" not in st.session_state:
    st.session_state.processing = False

# UPDATED: This block no longer adds a "thinking" placeholder.
if prompt := st.chat_input("e.g., 'Create a 'Just Sold' post for 123 Oak St.'"):
    st.session_state.file_was_processed = False
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.processing = True
    st.session_state.last_prompt = prompt
    st.rerun()

# UPDATED: This block now appends the final message instead of updating a placeholder.
if st.session_state.processing:
    st.session_state.processing = False
    response_content = process_user_input(st.session_state.last_prompt)
    st.session_state.messages.append({"role": "assistant", "content": response_content})
    st.rerun()