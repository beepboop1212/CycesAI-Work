# app.py
import streamlit as st
import os # For getenv, though config.py handles it mostly
import requests # Keep for fetching final image bytes if needed directly here

# Import from our new modules
from config import (
    get_bannerbear_api_key, get_google_api_key, get_freeimage_api_key,
    BANNERBEAR_API_ENDPOINT, FREEIMAGE_API_ENDPOINT # Not strictly needed here if services use them
)
import bannerbear_service
import freeimage_service
import llm_service
import ui_components

# --- INITIALIZATION & CONFIGURATION ---
def initialize_session_state():
    # Basic app state
    default_chat = [{"role": "assistant", "content": "Hi! I'm BannerGenie. Type 'show templates' or click the button below to start."}]
    if 'chat_history' not in st.session_state: st.session_state.chat_history = default_chat
    if 'templates_list_details' not in st.session_state: st.session_state.templates_list_details = None
    if 'selected_template_uid' not in st.session_state: st.session_state.selected_template_uid = None
    if 'selected_template_details' not in st.session_state: st.session_state.selected_template_details = None
    if 'current_modifications' not in st.session_state: st.session_state.current_modifications = []
    if 'action_select_template_uid' not in st.session_state: st.session_state.action_select_template_uid = None
    if 'final_generated_image_url' not in st.session_state: st.session_state.final_generated_image_url = None
    if 'final_generated_image_bytes' not in st.session_state: st.session_state.final_generated_image_bytes = None
    if 'image_upload_for_layer' not in st.session_state: st.session_state.image_upload_for_layer = None # { 'layer_name': 'name' }
    if 'last_poll_status' not in st.session_state: st.session_state.last_poll_status = None # For polling messages

    # API Keys - load from .env via config.py and store in session_state for services to use
    if 'bannerbear_api_key' not in st.session_state: st.session_state.bannerbear_api_key = get_bannerbear_api_key()
    if 'google_api_key' not in st.session_state: st.session_state.google_api_key = get_google_api_key()
    if 'freeimage_api_key' not in st.session_state: st.session_state.freeimage_api_key = get_freeimage_api_key()
    
    # API Key status flags for UI
    st.session_state.bannerbear_api_key_ok = bool(st.session_state.bannerbear_api_key)
    st.session_state.google_api_key_ok = bool(st.session_state.google_api_key)
    st.session_state.freeimage_api_key_ok = bool(st.session_state.freeimage_api_key)

    # Configure Gemini Model (uses key from session_state)
    if st.session_state.google_api_key_ok and 'gemini_model_instance' not in st.session_state:
        llm_service.configure_gemini_model() # This will set st.session_state.gemini_model_instance


initialize_session_state() # Call initialization

# --- PAGE CONFIG & TITLE ---
st.set_page_config(page_title="BannerGenie Assistant (Refactored)", layout="wide", page_icon="🪄")
st.title("🪄 BannerGenie: Conversational Banner Design")

# --- API Key Status Check & Warnings ---
if not st.session_state.bannerbear_api_key_ok:
    st.error("🚨 Bannerbear API Key is MISSING. Please set it in your .env file and restart the app.")
    st.stop()
if not st.session_state.google_api_key_ok:
    st.warning("⚠️ Google (Gemini) API Key is MISSING. AI for understanding modifications will be disabled.")
if not st.session_state.freeimage_api_key_ok:
    st.warning("⚠️ Freeimage.host API Key is MISSING. Image uploads via chat will be disabled.")


# --- UI Placeholders for Dynamic Content ---
selected_template_placeholder = st.empty()
final_image_placeholder = st.empty()
pending_uploader_placeholder = st.empty()


# --- Callback Functions for UI Interactions ---
def handle_confirm_image_upload(uploaded_file, target_layer_name):
    """Called when user confirms an image upload."""
    with st.spinner(f"Uploading '{uploaded_file.name}' to image host..."):
        public_url, upload_error = freeimage_service.upload_image(uploaded_file)
    
    if public_url:
        mod_to_add = {"name": target_layer_name, "image_url": public_url}
        # Update or add modification
        found = False
        for i, mod in enumerate(st.session_state.current_modifications):
            if mod.get("name") == target_layer_name:
                st.session_state.current_modifications[i] = mod_to_add
                found = True; break
        if not found: st.session_state.current_modifications.append(mod_to_add)
        
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": f"✅ Image for '{target_layer_name}' uploaded and set to: {public_url}. {len(st.session_state.current_modifications)} change(s) pending. What's next?"
        })
        st.session_state.image_upload_for_layer = None # Clear flag
    else:
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": f"⚠️ Upload failed for '{target_layer_name}': {upload_error}. Please try again or cancel."
        })
    # Rerun will be handled by the main loop or button's natural behavior

def handle_cancel_image_upload(target_layer_name):
    st.session_state.image_upload_for_layer = None
    st.session_state.chat_history.append({"role": "assistant", "content": f"Okay, cancelled image upload for '{target_layer_name}'."})
    # Rerun will be handled

# --- Main Application Loop & Rendering ---

# Process template selection action triggered by button clicks (from ui_components)
if st.session_state.action_select_template_uid:
    uid_to_select = st.session_state.action_select_template_uid
    st.session_state.action_select_template_uid = None # Reset action flag immediately

    with st.spinner(f"Loading template UID: {uid_to_select}..."):
        details_data, error_msg = bannerbear_service.fetch_template_details(uid_to_select)
    
    assistant_response_content = ""
    if details_data:
        st.session_state.selected_template_uid = uid_to_select
        st.session_state.selected_template_details = details_data
        st.session_state.current_modifications = []
        st.session_state.final_generated_image_url = None
        st.session_state.final_generated_image_bytes = None
        st.session_state.image_upload_for_layer = None # Clear pending upload from prev template

        editable_layers_summary = "It has the following editable layers:\n"
        available_mods = details_data.get('available_modifications', [])
        if available_mods:
            for layer in available_mods:
                layer_name = layer.get('name', 'Unnamed')
                layer_type = "Unknown"
                if "text" in layer: layer_type = "Text"
                elif "image_url" in layer: layer_type = "Image"
                elif "color" in layer: layer_type = "Color"
                editable_layers_summary += f"- `{layer_name}` ({layer_type})\n"
            editable_layers_summary += "\nWhat would you like to change first?"
        else:
            editable_layers_summary = "This template doesn't seem to have specific editable layers listed."
        assistant_response_content = f"You've selected '{details_data.get('name', uid_to_select)}'. {editable_layers_summary}"
    else:
        assistant_response_content = f"I tried to select UID '{uid_to_select}' but couldn't get its details. Error: {error_msg or 'Unknown'}"
        st.session_state.selected_template_uid = None # Clear if failed
        st.session_state.selected_template_details = None
    
    st.session_state.chat_history.append({"role": "assistant", "content": assistant_response_content})
    st.rerun() # Rerun to update UI after selection


# Render dynamic UI parts using placeholders
with selected_template_placeholder:
    ui_components.display_selected_template_card(st.session_state.selected_template_details)

with final_image_placeholder:
    ui_components.display_final_generated_image(
        st.session_state.final_generated_image_bytes,
        st.session_state.final_generated_image_url,
        st.session_state.selected_template_uid
    )

with pending_uploader_placeholder:
    ui_components.display_pending_image_uploader_ui(
        st.session_state.image_upload_for_layer,
        on_upload_callback=handle_confirm_image_upload,
        on_cancel_callback=handle_cancel_image_upload
    )


# Display Chat History (must be AFTER processing actions that modify chat history)
chat_display_container = st.container()
with chat_display_container:
    for i, msg_data in enumerate(st.session_state.chat_history):
        ui_components.display_chat_history_item(msg_data, i, st.session_state.templates_list_details)
        # Consume display flag if it was set by this component
        if msg_data.get("display_templates_now"):
            if i < len(st.session_state.chat_history): # Check index validity
                 st.session_state.chat_history[i].pop("display_templates_now", None)


# --- Chat Input Processing ---
if prompt := st.chat_input("What would you like to do?"):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    
    # --- Command Processing Logic ---
    prompt_lower = prompt.lower().strip()
    assistant_response_content = ""
    # This flag determines if a st.rerun() is needed after processing the command
    # Most commands that update state or UI will need a rerun.
    needs_rerun = True 

    if not st.session_state.bannerbear_api_key_ok:
        assistant_response_content = "My connection to Bannerbear isn't working. API key is missing."
    
    elif prompt_lower == "show templates" or prompt_lower == "list templates":
        with st.spinner("Fetching templates from Bannerbear..."):
            templates_data, error_msg = bannerbear_service.fetch_all_templates_cached()
        if templates_data:
            st.session_state.templates_list_details = templates_data
            assistant_response_content = "Okay, here are your Bannerbear templates. Click one to select it."
            # Add a new message to history that will trigger the display
            st.session_state.chat_history.append({
                "role": "assistant", "content": assistant_response_content, "display_templates_now": True
            })
            assistant_response_content = "" # Avoid double message
        else:
            assistant_response_content = f"I couldn't fetch your templates. {error_msg or 'Unknown error.'}"

    elif prompt_lower.startswith("select template "): # Text fallback for selection
        if not st.session_state.templates_list_details:
            assistant_response_content = "Please ask to 'show templates' first."
        else:
            try:
                identifier = prompt.split(maxsplit=2)[2].strip()
                uid_to_select_text = None
                if identifier.isdigit():
                    idx = int(identifier)-1
                    if 0 <= idx < len(st.session_state.templates_list_details):
                        uid_to_select_text = st.session_state.templates_list_details[idx].get('uid')
                else:
                    for t_item in st.session_state.templates_list_details:
                        if t_item.get('uid') == identifier or t_item.get('name', '').lower() == identifier.lower():
                            uid_to_select_text = t_item.get('uid'); break
                if uid_to_select_text:
                    # Trigger the selection action state, main loop will handle it
                    st.session_state.action_select_template_uid = uid_to_select_text
                    assistant_response_content = f"Okay, attempting to select '{identifier}' by text..."
                else:
                    assistant_response_content = f"Couldn't find template '{identifier}' by text. Try using the buttons."
            except IndexError:
                 assistant_response_content = "Please specify which template after 'select template '."
            except Exception as e_txt_sel:
                assistant_response_content = f"Error with text selection: {e_txt_sel}"


    elif st.session_state.selected_template_details and \
         any(keyword in prompt_lower for keyword in ["change", "set", "update", "make", "use image", "set color", "modify"]):
        
        if not st.session_state.google_api_key_ok or not st.session_state.get('gemini_model_instance'):
            assistant_response_content = "AI modification parsing is disabled (Google API Key or Model issue)."
        else:
            available_mods_for_llm = []
            if 'available_modifications' in st.session_state.selected_template_details:
                for layer in st.session_state.selected_template_details['available_modifications']:
                    layer_name_llm = layer.get('name')
                    layer_type_str_llm = "Unknown"
                    if "text" in layer: layer_type_str_llm = "Text"
                    elif "image_url" in layer: layer_type_str_llm = "Image"
                    elif "color" in layer: layer_type_str_llm = "Color"
                    if layer_name_llm: available_mods_for_llm.append({"name": layer_name_llm, "type": layer_type_str_llm})

            if available_mods_for_llm:
                with st.spinner("AI is thinking..."): # Spinner for LLM call
                    parsed_modification, llm_error = llm_service.parse_modification_request(prompt, available_mods_for_llm)
                
                if parsed_modification:
                    layer_to_change = parsed_modification.get("layer_name")
                    mod_type = parsed_modification.get("modification_type","").lower()
                    new_val = parsed_modification.get("new_value")
                    actual_layer_names = [l['name'] for l in available_mods_for_llm]

                    if layer_to_change not in actual_layer_names:
                        assistant_response_content = f"AI suggested changing '{layer_to_change}', but I couldn't find that exact layer. Available: {', '.join(actual_layer_names)}."
                    
                    elif new_val == "USER_UPLOAD_PENDING" and mod_type == "image_url":
                        if st.session_state.freeimage_api_key_ok:
                            st.session_state.image_upload_for_layer = layer_to_change
                            assistant_response_content = f"Okay, to change the image for '{layer_to_change}', please use the uploader that just appeared above the chat."
                        else:
                            assistant_response_content = f"You want to change image for '{layer_to_change}', but image uploads are disabled (Freeimage API Key missing)."
                    
                    else: # Handle text, color, or direct image_url
                        bb_mod = {}
                        if mod_type == "text": bb_mod = {"name": layer_to_change, "text": new_val}
                        elif mod_type == "color": bb_mod = {"name": layer_to_change, "color": new_val}
                        elif mod_type == "image_url":
                            if isinstance(new_val, str) and new_val.startswith('http'):
                                bb_mod = {"name": layer_to_change, "image_url": new_val}
                            else:
                                assistant_response_content = f"For '{layer_to_change}', AI suggested an image URL, but value was '{new_val}'. If uploading, just say 'change image for {layer_to_change}'."
                        
                        if bb_mod:
                            found = False
                            for i, mod_item in enumerate(st.session_state.current_modifications):
                                if mod_item.get("name") == layer_to_change:
                                    st.session_state.current_modifications[i] = bb_mod; found = True; break
                            if not found: st.session_state.current_modifications.append(bb_mod)
                            assistant_response_content = f"Okay, noted: change '{layer_to_change}' to '{new_val}'. {len(st.session_state.current_modifications)} change(s) pending. Ask for more, or type 'generate banner'."
                        elif not assistant_response_content: # If bb_mod is empty and no specific error set
                            assistant_response_content = f"AI suggested changing '{layer_to_change}' (type '{mod_type}'), but I couldn't form a valid modification with value '{new_val}'."
                else: 
                    assistant_response_content = f"AI had trouble understanding that specific change. {llm_error or 'Could you try rephrasing?'}"
            else:
                assistant_response_content = "The selected template doesn't have clearly defined editable layers for AI modification."
    
    elif prompt_lower == "generate banner" or prompt_lower == "create banner":
        if not st.session_state.selected_template_uid:
            assistant_response_content = "Please select a template first."
        elif not st.session_state.current_modifications:
            assistant_response_content = "No changes made yet. Say 'generate with defaults' or tell me what to change."
        else:
            st.session_state.final_generated_image_url = None
            st.session_state.final_generated_image_bytes = None
            with st.spinner("Sending request to Bannerbear..."):
                initial_bb_response, bb_error = bannerbear_service.generate_image(
                    st.session_state.selected_template_uid, 
                    st.session_state.current_modifications
                )

            if bb_error:
                assistant_response_content = f"Bannerbear request failed: {bb_error}"
            elif initial_bb_response:
                final_url = None; status = initial_bb_response.get("status"); uid = initial_bb_response.get("uid")
                if status == "completed" and initial_bb_response.get("image_url_png"):
                    final_url = initial_bb_response.get("image_url_png")
                elif status == "pending" and uid:
                    with st.spinner(f"Bannerbear is working (UID: {uid}). Polling... This can take up to a minute."):
                        # Add polling messages directly to chat from within the service might be too noisy.
                        # We can update a general status message in the chat from here.
                        st.session_state.chat_history.append({"role": "assistant", "content": f"⏳ Bannerbear processing (UID: {uid}). Waiting..."})
                        # No rerun here to let spinner run. Polling function itself will add more detailed chat messages.
                        final_url, poll_error = bannerbear_service.poll_image_completion(uid)
                    if poll_error: assistant_response_content = f"Polling failed for UID {uid}: {poll_error}"
                # ... (other status handling for initial_bb_response) ...
                else: assistant_response_content = f"Bannerbear response unclear or not pending: {initial_bb_response.get('status', 'Unknown status')}. UID: {uid}"
                
                if final_url:
                    st.session_state.final_generated_image_url = final_url
                    try:
                        with st.spinner(f"Fetching final image from {final_url}..."):
                            img_resp = requests.get(final_url, timeout=45); img_resp.raise_for_status()
                            st.session_state.final_generated_image_bytes = img_resp.content
                        assistant_response_content = "🎉 Banner generated and fetched! Check it out above the chat."
                        # Optionally clear modifications:
                        # st.session_state.current_modifications = []
                    except requests.exceptions.RequestException as img_fetch_e:
                        assistant_response_content = f"Banner generated at {final_url}, but I couldn't fetch it: {img_fetch_e}"
                elif not assistant_response_content: # If final_url None and no specific poll_error message
                     assistant_response_content = "Banner generation did not complete successfully or URL was not retrieved."
            else: # initial_bb_response was None
                assistant_response_content = "Initial Bannerbear request failed to return a response."


    elif prompt_lower == "generate with defaults":
         if not st.session_state.selected_template_uid:
            assistant_response_content = "Please select a template first."
         else:
            st.session_state.current_modifications = [] 
            # Trigger generation (similar to "generate banner" but with empty mods)
            # This is a simplified version; a more robust way would be to refactor the generation logic
            # into a common function called by both "generate banner" and "generate with defaults".
            st.session_state.chat_history.append({"role": "user", "content": "generate with defaults (triggering)"}) # Log intent
            # Effectively, we re-route this to the "generate banner" logic by ensuring modifications are empty
            # and then let that logic run. For a cleaner approach, you might have a dedicated function.
            # For now, let's just say this:
            assistant_response_content = "Okay, preparing to generate with template defaults. Type 'generate banner' to confirm (after I clear any existing changes)."
            st.warning("To generate with defaults, first ensure no modifications are listed, then type 'generate banner'. This command path needs full implementation.")


    elif not assistant_response_content: # Fallback
        if st.session_state.selected_template_uid and st.session_state.selected_template_details:
            template_name = st.session_state.selected_template_details.get('name', 'the current template')
            assistant_response_content = (f"I can help modify '{template_name}'. Try 'change title to Super Sale'. When ready, say 'generate banner'. Or, 'show templates'.")
        else:
            assistant_response_content = ("Hello! How can I help? Try 'show templates' to begin.")

    # Append assistant's response to chat history
    if assistant_response_content:
        st.session_state.chat_history.append({"role": "assistant", "content": assistant_response_content})
    
    if needs_rerun:
        st.rerun()