import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai
import json
import io
import os
import re # For robust JSON parsing
from dotenv import load_dotenv # <--- IMPORT DOTENV

# --- Load environment variables from .env file ---
load_dotenv() # <--- LOAD THE .ENV FILE

# --- Initialize session state keys very early ---
# Try to get API key from environment first, then session state, then empty
if 'api_key' not in st.session_state:
    st.session_state.api_key = os.getenv("GOOGLE_API_KEY", "") # <--- GET FROM ENV

if 'template_structure' not in st.session_state:
    st.session_state.template_structure = None
if 'user_inputs' not in st.session_state:
    st.session_state.user_inputs = {}
if 'original_template_image' not in st.session_state:
    st.session_state.original_template_image = None
if 'original_template_dimensions' not in st.session_state:
    st.session_state.original_template_dimensions = None
if 'generated_card' not in st.session_state:
    st.session_state.generated_card = None


st.set_page_config(layout="wide", page_title="Property Card Generator")
st.title("AI-Powered Property Card Generator")

# --- Helper Functions ---
def get_gemini_response(image_bytes, prompt, api_key_to_use): # Renamed api_key to api_key_to_use
    """Sends image and prompt to Gemini and gets a structured response."""
    if not api_key_to_use: # Check the passed api_key
        st.error("Google API Key is not configured. Please set it in your .env file or enter it in the sidebar.")
        return None
    try:
        genai.configure(api_key=api_key_to_use) # Use the passed api_key
        # Check for model name, Gemini 1.5 Flash is 'gemini-1.5-flash-latest' or 'gemini-1.5-flash'
        # 'gemini-2.0-flash' is not a current valid model name as of my last update.
        # Let's assume you meant 'gemini-1.5-flash' or a similar valid one.
        # If 'gemini-2.0-flash' is indeed a new model, then it's fine.
        # For safety, I'll use 'gemini-1.5-flash'. Adjust if 'gemini-2.0-flash' is correct.
        model = genai.GenerativeModel('gemini-2.0-flash')
        image_part = {"mime_type": "image/png", "data": image_bytes}
        response = model.generate_content([prompt, image_part])
        return response.text
    except Exception as e:
        st.error(f"Error calling Gemini API: {e}")
        # Add more specific error for common API key issues
        if "API key not valid" in str(e) or "PERMISSION_DENIED" in str(e):
            st.error("The provided Google API Key seems to be invalid or lacks permissions for the Gemini API.")
        return None

# ... (clean_json_string, parse_gemini_output, hex_to_rgb functions remain the same) ...
def clean_json_string(json_string):
    """Attempts to clean common issues in LLM-generated JSON strings."""
    match = re.search(r"```json\s*([\s\S]*?)\s*```", json_string)
    if match:
        json_string = match.group(1)
    else:
        first_brace = json_string.find('{')
        last_brace = json_string.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            json_string = json_string[first_brace:last_brace+1]
    json_string = re.sub(r",\s*([\}\]])", r"\1", json_string)
    return json_string.strip()


def parse_gemini_output(response_text):
    """Parses the LLM's text response into a Python list of dictionaries."""
    if not response_text:
        return None
    try:
        cleaned_text = clean_json_string(response_text)
        template_structure = json.loads(cleaned_text)
        if isinstance(template_structure, list):
            return template_structure
        elif isinstance(template_structure, dict) and "elements" in template_structure and isinstance(template_structure["elements"], list):
            return template_structure["elements"]
        else:
            st.error("LLM response was not a valid JSON list of elements.")
            st.write("LLM Raw Response:", response_text)
            return None
    except json.JSONDecodeError as e:
        st.error(f"Failed to parse JSON from Gemini: {e}")
        st.text_area("Gemini Raw Response (for debugging JSON error):", response_text, height=200)
        return None

def hex_to_rgb(hex_color):
    """Converts a hex color string (e.g., #RRGGBB) to an RGB tuple."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = "".join([c*2 for c in hex_color])
    if len(hex_color) != 6:
        st.warning(f"Invalid hex color '{hex_color}'. Using black as default for text if error.")
        return (0, 0, 0)
    try:
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        st.warning(f"Invalid hex color format '{hex_color}'. Using black text as default.")
        return (0, 0, 0)

# --- Font ---
try:
    FONT_PATH = "OpenSans-Regular.ttf" # Make sure this font file is in the same directory
    ImageFont.truetype(FONT_PATH, 10)
except IOError:
    st.warning(f"Font file '{FONT_PATH}' not found. Trying 'arial.ttf'.")
    FONT_PATH = "arial.ttf" # Fallback to Arial
    try:
        ImageFont.truetype(FONT_PATH, 10)
    except IOError:
        st.warning(f"Font file 'arial.ttf' also not found. Text rendering might use a default system font and look different. "
                   "Download a .ttf font and place it in the same directory as app.py.")
        FONT_PATH = None


# --- LLM Prompt (remains the same) ---
LLM_PROMPT_TEMPLATE = """
Analyze the provided real estate property card image.
Identify all distinct editable elements: text fields (like address, price, agent name, features, etc.),
the main property image placeholder, the agent photo placeholder, and the company logo placeholder.

For each element, provide:
1.  `id`: A unique, descriptive, underscore_separated ID (e.g., "address_line_1", "property_image", "agent_name", "company_logo").
2.  `type`: One of "text", "image_placeholder", "logo_placeholder".
3.  `label`: A user-friendly label for an input field (e.g., "Property Address Line 1", "Main Property Photo").
4.  `placeholder_text` (ONLY for type "text"): The example text seen in the template.
5.  `position_bbox`: An approximate bounding box [x_top_left, y_top_left, width, height] in pixels.
    The image dimensions are {width}x{height} pixels. Be as precise as possible with coordinates and dimensions.
    The origin (0,0) is the top-left corner of the image.
6.  `font_family_hint` (ONLY for type "text"): A hint for the font family (e.g., "sans-serif", "Brandon Grotesque", "Helvetica Neue"). If unsure, suggest "sans-serif".
7.  `font_size_px` (ONLY for type "text"): Approximate font size in pixels (e.g., 24, 12).
8.  `font_color_hex` (ONLY for type "text"): Approximate font color in HEX format (e.g., "#003366", "#FFFFFF").
9.  `text_alignment` (ONLY for type "text"): Suggested text alignment ("left", "center", "right"). Default to "left" if unsure.

Return the output as a single, valid JSON list of objects, where each object represents an element.
Ensure the JSON is well-formed and can be directly parsed. Do not include any explanations outside the JSON structure.

Example for one text element:
{{
    "id": "price",
    "type": "text",
    "label": "Price",
    "placeholder_text": "$389,990",
    "position_bbox": [500, 50, 150, 30],
    "font_family_hint": "sans-serif",
    "font_size_px": 28,
    "font_color_hex": "#0A2145",
    "text_alignment": "left"
}}
Example for one image placeholder:
{{
    "id": "property_image",
    "type": "image_placeholder",
    "label": "Main Property Photo",
    "position_bbox": [50, 150, 600, 400]
}}

IMPORTANT:
- Do not invent elements not present.
- For the given template, identify elements like "JUST LISTED", address lines, price, features (bedroom, bath, SF), agent name, phone, website, the main image, agent photo, and ROA logo.
- The ROA logo should be `type: "logo_placeholder"`. The agent photo should be `type: "image_placeholder"`. The main house image is `type: "image_placeholder"`.
- Be very careful with the `position_bbox` values. They are critical.
"""

# --- Streamlit UI ---
st.sidebar.header("Configuration")

# API Key Handling - Load from .env, allow override via UI if needed
env_api_key = os.getenv("GOOGLE_API_KEY")
if env_api_key:
    if 'api_key' not in st.session_state or not st.session_state.api_key: # If session state is empty, fill from env
        st.session_state.api_key = env_api_key
    st.sidebar.success("API Key loaded from .env file.")
    # You might want to make the text_input disabled or just informational
    # For now, we'll still allow overriding it via UI, which updates session_state.api_key
#     st.session_state.api_key = st.sidebar.text_input(
#         "Google API Key (loaded from .env):",
#         type="password",
#         value=st.session_state.api_key # Value comes from session_state
#     )
# else:
#     st.sidebar.warning("API Key not found in .env file. Please enter it below.")
#     st.session_state.api_key = st.sidebar.text_input(
#         "Enter your Google API Key:",
#         type="password",
#         value=st.session_state.api_key # Value comes from session_state
#     )


uploaded_template_file = st.sidebar.file_uploader("1. Upload Template Image (PNG or JPG)", type=["png", "jpg", "jpeg"])
st.session_state.canvas_bg_color = st.sidebar.color_picker(
    "2. Choose Background Color for New Card", "#FFFFFF"
)


col1, col2 = st.columns(2)

with col1:
    st.subheader("Template Preview")
    if uploaded_template_file:
        pil_image = Image.open(uploaded_template_file)
        st.session_state.original_template_image = pil_image
        st.session_state.original_template_dimensions = pil_image.size
        st.image(pil_image, caption="Uploaded Template (Layout Reference)", use_container_width=True)

        if st.button("Analyze Template with Gemini"):
            if not st.session_state.api_key: # Check API key in session_state
                st.error("Google API Key is not configured. Please set it in your .env file or enter it in the sidebar.")
            else:
                with st.spinner("Analyzing template with Gemini... This might take a moment."):
                    temp_image_for_gemini = st.session_state.original_template_image.copy()
                    if temp_image_for_gemini.mode == 'RGBA':
                        temp_image_for_gemini = temp_image_for_gemini.convert('RGB')

                    img_byte_arr = io.BytesIO()
                    temp_image_for_gemini.save(img_byte_arr, format='PNG')
                    image_bytes = img_byte_arr.getvalue()

                    width, height = st.session_state.original_template_dimensions
                    prompt_with_dims = LLM_PROMPT_TEMPLATE.format(width=width, height=height)

                    # Pass the API key from session_state to the function
                    response_text = get_gemini_response(image_bytes, prompt_with_dims, st.session_state.api_key)
                    if response_text:
                        st.session_state.template_structure = parse_gemini_output(response_text)
                        if st.session_state.template_structure:
                            st.success("Template analyzed successfully! Fill in the details below.")
                            st.session_state.user_inputs = {}
                        else:
                            st.error("Failed to get a valid structure from Gemini. Check the response above if shown.")
                    else:
                        st.error("No response or error from Gemini API.")
    else:
        st.info("Upload a template image to begin.")
        st.session_state.original_template_image = None
        st.session_state.original_template_dimensions = None

with col2:
    st.subheader("Enter Property Details")
    # ... (the rest of the column 2 UI for data input remains the same) ...
    if st.session_state.template_structure:
        sorted_elements = sorted(
            st.session_state.template_structure,
            key=lambda x: 0 if 'image' in x.get('type', '') or 'logo' in x.get('type', '') else 1
        )

        for i, element in enumerate(sorted_elements):
            el_id = element.get("id", f"element_{i}")
            el_type = element.get("type")
            el_label = element.get("label", f"Element {i+1}")

            if el_type == "text":
                placeholder = element.get("placeholder_text", "")
                st.session_state.user_inputs[el_id] = st.text_input(
                    el_label,
                    value=st.session_state.user_inputs.get(el_id, placeholder),
                    key=f"input_{el_id}"
                )
            elif el_type in ["image_placeholder", "logo_placeholder"]:
                st.session_state.user_inputs[el_id] = st.file_uploader(
                    el_label,
                    type=["png", "jpg", "jpeg"],
                    key=f"input_{el_id}"
                )
            else:
                st.warning(f"Unknown element type: {el_type} for element ID: {el_id}")

# --- Generate Property Card Button (moved out of col2 to be full width below columns) ---
# This button's indentation was incorrect in the provided code, it should be at the main script level, not inside `with col2:`
if st.button("Generate Property Card", type="primary"): # Check indentation
    if not st.session_state.original_template_dimensions:
        st.error("Please upload and analyze a template image first to get its dimensions.")
    elif not st.session_state.template_structure:
        st.error("Template structure not found. Please analyze the template first.")
    elif not st.session_state.api_key: # Add API key check here too before generation
        st.error("Google API Key is not configured. Please ensure it's in your .env or entered in the sidebar.")
    else:
        # --- START DEBUGGING: Visualize LLM BBoxes ---
        # You can keep or remove this debug section as needed # CHECK1
        # if st.checkbox("Show LLM's Proposed Bounding Boxes on Template (Debug)", value=False): # Make it optional
        if st.session_state.original_template_image and st.session_state.template_structure:
            debug_image = st.session_state.original_template_image.copy()
            if debug_image.mode != 'RGB':
                debug_image = debug_image.convert('RGB')
            debug_draw = ImageDraw.Draw(debug_image)
            box_colors = ["red", "green", "blue", "yellow", "purple", "orange"]
            color_idx = 0
            for i_debug, element_debug in enumerate(st.session_state.template_structure):
                bbox_debug = element_debug.get("position_bbox")
                el_label_debug = element_debug.get("label", f"Elem {i_debug}")
                if bbox_debug and len(bbox_debug) == 4:
                    x_d, y_d, w_d, h_d = bbox_debug
                    try:
                        current_color = box_colors[color_idx % len(box_colors)]
                        debug_draw.rectangle([x_d, y_d, x_d + w_d, y_d + h_d], outline=current_color, width=3)
                        color_idx += 1
                    except Exception as e_debug:
                        st.warning(f"Error drawing debug box for {el_label_debug}: {e_debug}")
                else:
                    st.warning(f"Invalid or missing bbox for debugging: {el_label_debug}")
            st.image(debug_image, caption="DEBUG: LLM's Proposed Bounding Boxes on Template", use_container_width=True)
        # --- END DEBUGGING ---

        with st.spinner("Generating your property card..."):
            canvas_width, canvas_height = st.session_state.original_template_dimensions
            bg_color_hex = st.session_state.canvas_bg_color
            bg_color_rgb = hex_to_rgb(bg_color_hex)
            output_image = Image.new('RGB', (canvas_width, canvas_height), bg_color_rgb)
            if output_image.mode != 'RGBA':
                output_image = output_image.convert('RGBA')
            draw = ImageDraw.Draw(output_image)

            for element in st.session_state.template_structure:
                el_id = element.get("id")
                el_type = element.get("type")
                bbox = element.get("position_bbox")

                if not el_id or not el_type or not bbox or len(bbox) != 4:
                    st.warning(f"Skipping malformed element: {element.get('label', 'Unknown')}")
                    continue

                user_value = st.session_state.user_inputs.get(el_id)
                x, y, w, h = bbox

                if el_type == "text" and user_value:
                    text_to_draw = str(user_value)
                    font_size = element.get("font_size_px", 12)
                    font_color_hex = element.get("font_color_hex", "#000000")
                    font_color_rgb = hex_to_rgb(font_color_hex)
                    alignment = element.get("text_alignment", "left")

                    try:
                        if FONT_PATH:
                            font = ImageFont.truetype(FONT_PATH, font_size)
                        else: # Fallback if FONT_PATH is None (all attempts failed)
                            st.warning(f"No valid font path. Using Pillow's basic default font for {el_id}.")
                            font = ImageFont.load_default()
                    except Exception as e:
                        st.warning(f"Could not load font for '{el_id}'. Using default. Error: {e}")
                        font = ImageFont.load_default()

                    text_x, text_y = x, y
                    # Calculate text width for alignment
                    try:
                        # Pillow 9.2.0+ textlength, older textbbox
                        if hasattr(draw, 'textlength'):
                            text_width = draw.textlength(text_to_draw, font=font)
                        else:
                            text_bbox_size = draw.textbbox((0,0), text_to_draw, font=font)
                            text_width = text_bbox_size[2] - text_bbox_size[0]
                    except Exception as e_text_width:
                        st.warning(f"Could not determine text width for alignment for {el_id}: {e_text_width}. Defaulting to no alignment adjustment.")
                        text_width = w # Fallback, might not be ideal

                    if alignment == "right":
                        text_x = x + w - text_width
                    elif alignment == "center":
                        text_x = x + (w - text_width) / 2
                    
                    draw.text((text_x, text_y), text_to_draw, font=font, fill=font_color_rgb)

                elif el_type in ["image_placeholder", "logo_placeholder"] and user_value:
                    try:
                        uploaded_img_bytes = user_value.getvalue()
                        new_image = Image.open(io.BytesIO(uploaded_img_bytes))
                        
                        if new_image.mode != 'RGBA' and new_image.format == 'PNG':
                            new_image = new_image.convert('RGBA')
                        elif new_image.mode != 'RGB' and new_image.format != 'PNG':
                            new_image = new_image.convert('RGB')

                        new_image.thumbnail((w, h), Image.Resampling.LANCZOS)
                        paste_x = x + (w - new_image.width) // 2
                        paste_y = y + (h - new_image.height) // 2
                        
                        if new_image.mode == 'RGBA':
                            output_image.paste(new_image, (paste_x, paste_y), new_image)
                        else:
                            output_image.paste(new_image, (paste_x, paste_y))
                    except Exception as e:
                        st.error(f"Error processing image for {el_label}: {e}")
            
            st.session_state.generated_card = output_image
            st.success("Property card generated!")

# Display generated card
if st.session_state.generated_card:
    st.subheader("Generated Property Card")
    st.image(st.session_state.generated_card, caption="Final Property Card", use_container_width=True)
    
    buf = io.BytesIO()
    st.session_state.generated_card.save(buf, format="PNG")
    byte_im = buf.getvalue()
    st.download_button(
        label="Download Card",
        data=byte_im,
        file_name="property_card.png",
        mime="image/png"
    )

st.markdown("---")
st.markdown("Built with Streamlit, Pillow, and Google Gemini. Ensure necessary font files (e.g., OpenSans-Regular.ttf or arial.ttf) are in the app directory.")