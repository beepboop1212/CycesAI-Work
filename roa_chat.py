import streamlit as st
import os
import requests
from dotenv import load_dotenv
import json
import google.generativeai as genai
import time
import base64

# --- 1. CONFIGURATION & BRANDING (No changes here) ---
load_dotenv()
COMPANY_NAME = "Realty of America"
COMPANY_LOGO_URL = "https://iili.io/FCoWCx9.png"
BANNERBEAR_API_ENDPOINT = "https://api.bannerbear.com/v2"
FREEIMAGE_API_ENDPOINT = "https://freeimage.host/api/1/upload"


# --- 2. API HELPER FUNCTIONS (No changes here) ---

def bb_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}

@st.cache_resource(show_spinner="Warming up the Design Studio...")
def load_all_template_details(api_key):
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

def create_image_async(api_key, template_uid, modifications):
    payload = {"template": template_uid, "modifications": modifications}
    try:
        response = requests.post(f"{BANNERBEAR_API_ENDPOINT}/images", headers=bb_headers(api_key), json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Error creating image: {e}")
        return None

def poll_for_image_completion(api_key, image_object):
    polling_url = image_object.get("self")
    if not polling_url: return None

    for _ in range(30):
        time.sleep(1)
        try:
            response = requests.get(polling_url, headers=bb_headers(api_key))
            response.raise_for_status()
            polled_object = response.json()
            if polled_object['status'] == 'completed':
                return polled_object
            if polled_object['status'] == 'failed':
                print(f"Image generation failed on Bannerbear's side: {polled_object}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"API Error polling for image: {e}")
            return None
    return None

def upload_image_to_public_url(api_key, image_bytes):
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
            return None
    except requests.exceptions.RequestException as e:
        print(f"Connection error during image upload: {e}")
        return None


# --- 3. GEMINI AI "BRAIN" (No changes here) ---

def get_gemini_model_with_tool(api_key):
    if not api_key: return None
    genai.configure(api_key=api_key)

    process_user_request_tool = genai.protos.FunctionDeclaration(
        name="process_user_request",
        description="Processes a user's design request by deciding on a specific action. This is the only tool you can use.",
        parameters=genai.protos.Schema(
            type=genai.protos.Type.OBJECT,
            properties={
                "action": genai.protos.Schema(type=genai.protos.Type.STRING, description="The action to take. Must be one of: MODIFY, GENERATE, RESET, CONVERSE."),
                "template_uid": genai.protos.Schema(type=genai.protos.Type.STRING, description="Required if action is MODIFY. The UID of the template to use."),
                "modifications": genai.protos.Schema(
                    type=genai.protos.Type.ARRAY,
                    description="Required if action is MODIFY. A list of layer modifications to apply.",
                    items=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={ "name": genai.protos.Schema(type=genai.protos.Type.STRING), "text": genai.protos.Schema(type=genai.protos.Type.STRING), "image_url": genai.protos.Schema(type=genai.protos.Type.STRING), "color": genai.protos.Schema(type=genai.protos.Type.STRING)},
                        required=["name"]
                    )
                ),
                "response_text": genai.protos.Schema(type=genai.protos.Type.STRING, description=f"A friendly, user-facing message in the persona of a {COMPANY_NAME} assistant."),
            },
            required=["action", "response_text"]
        )
    )
    return genai.GenerativeModel(model_name="gemini-1.5-flash-latest", tools=[process_user_request_tool])

def get_ai_decision(model, messages, user_prompt, templates_data, design_context):
    system_prompt = f"""
    You are an expert, friendly, and super-intuitive design assistant for {COMPANY_NAME}.
    Your entire job is to understand an agent's natural language request and immediately decide on ONE of four actions using the `process_user_request` tool. You are an action-taker.

    **YOUR FOUR ACTIONS (You MUST choose one):**

    1.  **`MODIFY`**: **This is your most important action.** Use it to start a new design or update an existing one.
        - **Starting a New Design:** If the user wants to create something (e.g., 'make a flyer for 123 Main St'), you MUST autonomously select the BEST template from `AVAILABLE_TEMPLATES` and use this `MODIFY` action to apply all initial details.
        - **Updating a Design:** If a design is in progress, use this to add or change details.
        - **Post-Generation Tweak:** If an image was just shown and the user wants a specific change ("make the price red"), use this.
        - **Post-Generation New Layout:** If an image was just shown and the user wants a different style ("I don't like this layout"), you MUST pick a NEW template_uid, re-apply all previous modifications, and use this action.
        - **THE GENTLE NUDGE:** After a `MODIFY` action, if there are still obvious missing fields in the design (like price, address, agent_name, photo, etc.), your `response_text` MUST ask for ONE of them to guide the user. For example: "Got it, the price is set. What's the property address?" or "Great, address added. Do you have a photo for the listing?". Do this for the first 2-3 modifications to help the user complete the design quickly.

    2.  **`GENERATE`**: Use this ONLY when the user is finished and wants to see the final image. They will say things like "okay show it to me", "let's see it", "I'm ready", "make the image".
        - Your `response_text` should be a confirmation like "Of course! Generating your design now..."

    3.  **`RESET`**: Use this when the user wants to start a completely new, different design. They will say things like "let's do an open house flyer next", "start over".
        - Your `response_text` should confirm you are starting fresh (e.g., "You got it! Starting a new design. What are we creating?").

    4.  **`CONVERSE`**: Use this ONLY for secondary situations, like greetings ("hi") or if you MUST ask a clarifying question. Do NOT use this if you can take a `MODIFY` action instead.

    **CRITICAL RULES:**
    - **AUTONOMOUS SELECTION:** **NEVER** ask the user to choose a template. Select the best one yourself based on their request and the template names/layers in `AVAILABLE_TEMPLATES`.
    - **PRICE FORMATTING:** If a user gives a price (e.g., "950,000" or "the price is 950k"), you MUST format the `text` value with a dollar sign and commas (e.g., "$950,000").
    - **IMMEDIATE ACTION:** Your first response to a design request MUST be the `MODIFY` action. Do not ask for information you can infer. Take action immediately.

    **REFERENCE DATA (Do not repeat in your response):**
    - **AVAILABLE_TEMPLATES (with full layer details):** {json.dumps(templates_data, indent=2)}
    - **CURRENT_DESIGN_CONTEXT (The design we are building right now):** {json.dumps(design_context, indent=2)}
    """
    
    conversation = [{'role': 'user', 'parts': [system_prompt]}, {'role': 'model', 'parts': [f"Understood. I am an action-oriented design assistant for {COMPANY_NAME}. I will autonomously select templates, use the `MODIFY` action, and gently nudge the user for more information to complete the design."]}]
    for msg in messages[-8:]:
        if msg['role'] == 'assistant' and '![Generated Image]' in msg['content']: continue
        conversation.append({'role': 'user' if msg['role'] == 'user' else 'model', 'parts': [msg['content']]})
    conversation.append({'role': 'user', 'parts': [user_prompt]})

    return model.generate_content(conversation)


# --- 4. STREAMLIT APPLICATION ---
st.set_page_config(page_title=f"{COMPANY_NAME} AI Designer", layout="centered", page_icon="🏠")
st.image(COMPANY_LOGO_URL, width=200)
st.title("AI Design Assistant")

BB_API_KEY = os.getenv("BANNERBEAR_API_KEY")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
FREEIMAGE_API_KEY = os.getenv("FREEIMAGE_API_KEY")

def initialize_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": f"Hello! I'm your AI design assistant from {COMPANY_NAME}. How can I help you create marketing materials today?"}]
    if "gemini_model" not in st.session_state:
        st.session_state.gemini_model = get_gemini_model_with_tool(GEMINI_API_KEY)
    if "rich_templates_data" not in st.session_state:
        st.session_state.rich_templates_data = load_all_template_details(BB_API_KEY)
    if "design_context" not in st.session_state:
        st.session_state.design_context = {"template_uid": None, "modifications": []}
    if "staged_file_bytes" not in st.session_state:
        st.session_state.staged_file_bytes = None
    if "file_was_processed" not in st.session_state:
        st.session_state.file_was_processed = False
    # TWEAK 1 FIX: Add a new state variable to manage the processing flow.
    if "processing_prompt" not in st.session_state:
        st.session_state.processing_prompt = None

def handle_ai_decision(decision):
    action = decision.get("action")
    response_text = decision.get("response_text", "I'm not sure how to proceed.")
    trigger_generation = False

    if action == "MODIFY":
        new_template_uid = decision.get("template_uid")
        if new_template_uid and new_template_uid != st.session_state.design_context.get("template_uid"):
            if st.session_state.design_context.get("template_uid"): trigger_generation = True
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
        with st.spinner("Our design studio is creating your image..."):
            initial_response = create_image_async(BB_API_KEY, context['template_uid'], context['modifications'])
            if not initial_response: return "❌ **Error:** I couldn't start the image generation process."
            final_image = poll_for_image_completion(BB_API_KEY, initial_response)
            if final_image and final_image.get("image_url_png"):
                response_text += f"\n\n![Generated Image]({final_image['image_url_png']})"
            else:
                response_text = "❌ **Error:** The image generation timed out or failed. Please try again."
    return response_text

initialize_session_state()

if not all([st.session_state.gemini_model, st.session_state.rich_templates_data, BB_API_KEY, FREEIMAGE_API_KEY]):
    st.error("Application cannot start. Please check your API keys in the .env file and restart.", icon="🛑")
    st.stop()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"], unsafe_allow_html=True)

uploaded_file = st.file_uploader("Attach an image (e.g., a listing photo or headshot)", type=["png", "jpg", "jpeg"])
if uploaded_file:
    if not st.session_state.file_was_processed:
        st.session_state.staged_file_bytes = uploaded_file.getvalue()
        st.success("✅ Image attached! It will be included with your next message.")

# TWEAK 1 FIX: The main `if prompt` block is now much simpler.
# It just prepares for the processing, which happens in the block below.
if prompt := st.chat_input("e.g., 'Create a 'Just Sold' post for 123 Oak St.'"):
    st.session_state.file_was_processed = False
    st.session_state.messages.append({"role": "user", "content": prompt})
    # Add a temporary "thinking" message immediately.
    st.session_state.messages.append({"role": "assistant", "content": "🤔"})
    # Set the prompt to be processed and rerun.
    st.session_state.processing_prompt = prompt
    st.rerun()

# TWEAK 1 FIX: This new block handles the actual work on the *next* script run.
# This completely separates processing from initial display, fixing the bug.
if st.session_state.processing_prompt:
    prompt_to_process = st.session_state.processing_prompt
    
    final_prompt_for_ai = prompt_to_process
    if st.session_state.staged_file_bytes:
        with st.spinner("Uploading your image..."):
            image_url = upload_image_to_public_url(FREEIMAGE_API_KEY, st.session_state.staged_file_bytes)
            st.session_state.staged_file_bytes = None
            if image_url:
                final_prompt_for_ai = f"Image context: The user has uploaded an image, its URL is {image_url}. Their text command is: '{prompt_to_process}'"
                st.session_state.file_was_processed = True
            else:
                final_prompt_for_ai = None

    response_text = "I'm sorry, I'm having trouble connecting to my creative circuits. Could you please try again in a moment?"
    if final_prompt_for_ai:
        ai_response = get_ai_decision(st.session_state.gemini_model, st.session_state.messages, final_prompt_for_ai, st.session_state.rich_templates_data, st.session_state.design_context)
        if ai_response and ai_response.candidates and ai_response.candidates[0].content.parts[0].function_call:
            decision = dict(ai_response.candidates[0].content.parts[0].function_call.args)
            response_text = handle_ai_decision(decision)
        else:
            print(f"DEBUG: AI did not return a function call. Response: {ai_response}")

    # Update the last message (the "thinking" one) with the real response.
    st.session_state.messages[-1] = {"role": "assistant", "content": response_text}
    # Clear the processing flag.
    st.session_state.processing_prompt = None
    # Rerun one last time to show the final response.
    st.rerun()
