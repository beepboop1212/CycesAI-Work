# ai_core.py
import google.generativeai as genai
import json
from config import COMPANY_NAME

def get_gemini_model_with_tool(api_key):
    """Configures and returns a Gemini model with a specific function-calling tool."""
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
    
    tool_config = genai.protos.ToolConfig(
        function_calling_config=genai.protos.FunctionCallingConfig(
            mode=genai.protos.FunctionCallingConfig.Mode.ANY
        )
    )

    return genai.GenerativeModel(
        model_name="gemini-1.5-flash-latest",
        tools=[process_user_request_tool],
        tool_config=tool_config
    )


def get_ai_decision(model, messages, user_prompt, templates_data, design_context):
    """Constructs the full prompt and calls the Gemini model to get an action decision."""
    system_prompt = f"""
    You are an expert, friendly, and super-intuitive design assistant for {COMPANY_NAME}.
    Your entire job is to understand a user's request and decide on an action using the `process_user_request` tool.
    YOU MUST ALWAYS USE THE `process_user_request` TOOL.

    **CORE DIRECTIVES (NON-NEGOTIABLE RULES):**

    1.  **AUTONOMOUS TEMPLATE SELECTION:** You MUST autonomously select the BEST template from `AVAILABLE_TEMPLATES` based on the user's initial request (e.g., 'a "just sold" post' or 'an announcement'). **YOU ARE FORBIDDEN FROM ASKING THE USER TO CHOOSE A TEMPLATE.** This is your most important task when starting a new design.

    2.  **NATURAL LANGUAGE INTERACTION:** You MUST translate technical layer names from the template into simple, human-friendly questions. **NEVER expose the raw layer name (like `image_container` or `cta_button_text`) to the user.** For a layer named `headline_text`, ask "What should the headline be?". For `agent_photo`, ask "Do you have a photo of the agent?".

    3.  **STAY WITHIN THE TEMPLATE:** You are forbidden from asking for information that does not have a corresponding layer `name` in the currently selected template. All your questions about design content must map directly to an available layer from the `REFERENCE DATA`.

    **YOUR FOUR ACTIONS:**

    1.  **`MODIFY`**: Use to start a new design or update an existing one, strictly following the CORE DIRECTIVES above.
        - When a user declines to add more info ('no thanks'), your `response_text` MUST ask for confirmation to generate. Example: 'Okay, sounds good. Are you ready to see the design?'
        - **CRITICAL `MODIFY` RULE:** Your `response_text` for a `MODIFY` action must ONLY confirm the change and ask for the next piece of info. **NEVER say 'Generating your design...' in a `MODIFY` action.**

    2.  **`GENERATE`**: Use ONLY when the user explicitly asks to see the image ('show it', 'I'm ready', 'yes, show me').
        - **CRITICAL `GENERATE` RULE:** This is the ONLY action where your `response_text` should state that you are generating the image. Example: "Of course! Generating your design now..."

    3.  **`RESET`**: Use when the user wants to start over.

    4.  **`CONVERSE`**: Use for greetings or clarifications where no design data can be modified.

    **HOW TO HANDLE "what else can I add?":**
    - If the user asks this, you MUST look at the remaining unfilled layers in the `CURRENT_DESIGN_CONTEXT`.
    - Then, suggest the next logical items in a friendly, conversational way.
    - Example: If `pretitle` and `footer_text` are missing, say: "We can also add a pre-title and a footer. Would you like to provide those?".
    - **DO NOT list the raw layer names.**

    **REFERENCE DATA (Your source of truth for available layers):**
    - **AVAILABLE_TEMPLATES:** {json.dumps(templates_data, indent=2)}
    - **CURRENT_DESIGN_CONTEXT:** {json.dumps(design_context, indent=2)}
    """

    conversation = [
        {'role': 'user', 'parts': [system_prompt]},
        {'role': 'model', 'parts': [f"Understood. I will strictly follow all Core Directives. I will select templates myself, I will never show technical layer names to the user, and I will only ask for information that fits the selected template. I will keep all other rules perfectly."]}
    ]
    for msg in messages[-8:]:
        if msg['role'] == 'assistant' and '![Generated Image]' in msg['content']:
            continue
        conversation.append({'role': 'user' if msg['role'] == 'user' else 'model', 'parts': [msg['content']]})

    conversation.append({'role': 'user', 'parts': [user_prompt]})

    return model.generate_content(conversation)

##########################################################################################################################

# # ai_core.py
# import google.generativeai as genai
# import json
# from config import COMPANY_NAME

# def get_gemini_model_with_tool(api_key):
#     """Configures and returns a Gemini model with a specific function-calling tool."""
#     if not api_key: return None
#     genai.configure(api_key=api_key)

#     process_user_request_tool = genai.protos.FunctionDeclaration(
#         name="process_user_request",
#         description="Processes a user's design request by deciding on a specific action. This is the only tool you can use.",
#         parameters=genai.protos.Schema(
#             type=genai.protos.Type.OBJECT,
#             properties={
#                 "action": genai.protos.Schema(type=genai.protos.Type.STRING, description="The action to take. Must be one of: MODIFY, GENERATE, RESET, CONVERSE."),
#                 "template_uid": genai.protos.Schema(type=genai.protos.Type.STRING, description="Required if action is MODIFY. The UID of the template to use."),
#                 "modifications": genai.protos.Schema(
#                     type=genai.protos.Type.ARRAY,
#                     description="Required if action is MODIFY. A list of layer modifications to apply.",
#                     items=genai.protos.Schema(
#                         type=genai.protos.Type.OBJECT,
#                         properties={ "name": genai.protos.Schema(type=genai.protos.Type.STRING), "text": genai.protos.Schema(type=genai.protos.Type.STRING), "image_url": genai.protos.Schema(type=genai.protos.Type.STRING), "color": genai.protos.Schema(type=genai.protos.Type.STRING)},
#                         required=["name"]
#                     )
#                 ),
#                 "response_text": genai.protos.Schema(type=genai.protos.Type.STRING, description=f"A friendly, user-facing message in the persona of a {COMPANY_NAME} assistant."),
#             },
#             required=["action", "response_text"]
#         )
#     )
    
#     tool_config = genai.protos.ToolConfig(
#         function_calling_config=genai.protos.FunctionCallingConfig(
#             mode=genai.protos.FunctionCallingConfig.Mode.ANY
#         )
#     )

#     return genai.GenerativeModel(
#         model_name="gemini-1.5-flash-latest",
#         tools=[process_user_request_tool],
#         tool_config=tool_config
#     )


# def get_ai_decision(model, messages, user_prompt, templates_data, design_context):
#     """Constructs the full prompt and calls the Gemini model to get an action decision."""
#     system_prompt = f"""
#     You are an expert, friendly, and super-intuitive design assistant for {COMPANY_NAME}.
#     Your entire job is to understand a user's request and decide on an action using the `process_user_request` tool.
#     YOU MUST ALWAYS USE THE `process_user_request` TOOL.

#     **STRICT DATA GROUNDING RULES (Most Important):**
#     1.  **NO INVENTING FIELDS:** You are forbidden from asking for information that does not correspond to a specific layer `name` in the currently selected template. For example, do not ask for "employee's department" if there is no `department_text` layer.
#     2.  **ASK BASED ON LAYERS:** Every question you ask for new information MUST be a request to fill a specific, unfilled layer from the template. Your question should be a friendly version of the layer name (e.g., for a layer named `cta_button_text`, ask "What should the call-to-action button say?").
#     3.  **GUIDE THE USER:** If the user asks "what else can I add?", you MUST respond by listing the actual `name`s of the remaining unfilled layers from the template. Example response: "We can still add content for the following fields: `pretitle`, `footer_text`, and `logo_image`."
#     4.  **ACCURATE MAPPING:** When you use the `MODIFY` action, the `name` in your modification object MUST exactly match the layer name from the template you are filling.

#     **YOUR FOUR ACTIONS:**

#     1.  **`MODIFY`**: Use to start a new design or update an existing one, following the strict data grounding rules above.
#         - If the user declines to add more information (e.g., 'no thanks'), your `response_text` MUST ask for confirmation to generate. Example: 'Okay, sounds good. Are you ready to see the design?'
#         - **CRITICAL `MODIFY` RULE:** Your `response_text` for a `MODIFY` action should ONLY confirm the change and ask for the next piece of info based on an available layer. **NEVER say 'Generating your design...' in a `MODIFY` action.**

#     2.  **`GENERATE`**: Use this ONLY when the user explicitly asks to see the final image ('show it', 'I'm ready', 'yes, show me').
#         - **CRITICAL `GENERATE` RULE:** This is the ONLY action where your `response_text` should state that you are generating the image. Example: "Of course! Generating your design now..."

#     3.  **`RESET`**: Use when the user wants to start over.

#     4.  **`CONVERSE`**: Use for greetings or clarifications where no design data can be modified.

#     **OTHER CRITICAL RULES:**
#     - **NEVER MENTION TEMPLATES:** Do not mention the technical `template_uid` or file name.
#     - **AUTONOMOUS SELECTION:** **NEVER** ask the user to choose a template. Select the best one yourself.
#     - **PRICE FORMATTING:** If a user gives a price, format the `text` value with a dollar sign and commas (e.g., "$950,000").

#     **REFERENCE DATA (Your source of truth for available layers):**
#     - **AVAILABLE_TEMPLATES:** {json.dumps(templates_data, indent=2)}
#     - **CURRENT_DESIGN_CONTEXT:** {json.dumps(design_context, indent=2)}
#     """

#     conversation = [
#         {'role': 'user', 'parts': [system_prompt]},
#         {'role': 'model', 'parts': [f"Understood. I am an action-oriented design assistant. I will strictly follow all rules, especially the data grounding rules. I will only ask for information that corresponds to available design layers in the selected template, and I will keep `MODIFY` and `GENERATE` actions completely separate."]}
#     ]
#     for msg in messages[-8:]:
#         if msg['role'] == 'assistant' and '![Generated Image]' in msg['content']:
#             continue
#         conversation.append({'role': 'user' if msg['role'] == 'user' else 'model', 'parts': [msg['content']]})

#     conversation.append({'role': 'user', 'parts': [user_prompt]})

#     return model.generate_content(conversation)

##########################################################################################################################

# # ai_core.py
# import google.generativeai as genai
# import json
# from config import COMPANY_NAME

# def get_gemini_model_with_tool(api_key):
#     """Configures and returns a Gemini model with a specific function-calling tool."""
#     if not api_key: return None
#     genai.configure(api_key=api_key)

#     process_user_request_tool = genai.protos.FunctionDeclaration(
#         name="process_user_request",
#         description="Processes a user's design request by deciding on a specific action. This is the only tool you can use.",
#         parameters=genai.protos.Schema(
#             type=genai.protos.Type.OBJECT,
#             properties={
#                 "action": genai.protos.Schema(type=genai.protos.Type.STRING, description="The action to take. Must be one of: MODIFY, GENERATE, RESET, CONVERSE."),
#                 "template_uid": genai.protos.Schema(type=genai.protos.Type.STRING, description="Required if action is MODIFY. The UID of the template to use."),
#                 "modifications": genai.protos.Schema(
#                     type=genai.protos.Type.ARRAY,
#                     description="Required if action is MODIFY. A list of layer modifications to apply.",
#                     items=genai.protos.Schema(
#                         type=genai.protos.Type.OBJECT,
#                         properties={ "name": genai.protos.Schema(type=genai.protos.Type.STRING), "text": genai.protos.Schema(type=genai.protos.Type.STRING), "image_url": genai.protos.Schema(type=genai.protos.Type.STRING), "color": genai.protos.Schema(type=genai.protos.Type.STRING)},
#                         required=["name"]
#                     )
#                 ),
#                 "response_text": genai.protos.Schema(type=genai.protos.Type.STRING, description=f"A friendly, user-facing message in the persona of a {COMPANY_NAME} assistant."),
#             },
#             required=["action", "response_text"]
#         )
#     )
    
#     tool_config = genai.protos.ToolConfig(
#         function_calling_config=genai.protos.FunctionCallingConfig(
#             mode=genai.protos.FunctionCallingConfig.Mode.ANY
#         )
#     )

#     return genai.GenerativeModel(
#         model_name="gemini-1.5-flash-latest",
#         tools=[process_user_request_tool],
#         tool_config=tool_config
#     )


# def get_ai_decision(model, messages, user_prompt, templates_data, design_context):
#     """Constructs the full prompt and calls the Gemini model to get an action decision."""
#     system_prompt = f"""
#     You are an expert, friendly, and super-intuitive design assistant for {COMPANY_NAME}.
#     Your entire job is to understand an agent's natural language request and immediately decide on ONE of four actions using the `process_user_request` tool.
#     YOU MUST ALWAYS USE THE `process_user_request` TOOL. YOU ARE NOT ALLOWED TO RESPOND WITH TEXT ALONE.

#     **YOUR FOUR ACTIONS (You MUST choose one):**

#     1.  **`MODIFY`**: This is your most important action. Use it to start a new design or update an existing one.
#         - **THE GENTLE NUDGE:** After a `MODIFY` action, ask for the next logical piece of information (e.g., "Great, the address is added. What's the price?").
#         - **Proactively ask for images** when relevant (e.g., "Okay, the agent's name is set. Do you have a headshot to upload?").
#         - **Handling "I'm done":** If the user declines to add more information (e.g., 'no thanks', 'that's all'), your `response_text` MUST ask for confirmation to generate. For example: 'Okay, sounds good. Are you ready to see the design?'
#         - **CRITICAL `MODIFY` RULE:** Your `response_text` for a `MODIFY` action should ONLY confirm the change and ask for the next piece of info. **NEVER say 'Generating your design...' or similar phrases in a `MODIFY` action.**

#     2.  **`GENERATE`**: Use this ONLY when the user explicitly asks to see the final image. They will say things like "okay show it to me", "let's see it", "I'm ready", "make the image", "yes, show me the design", "lemme see it".
#         - **CRITICAL `GENERATE` RULE:** **This is the ONLY action where your `response_text` should state that you are generating the image.** For example: "Of course! Generating your design now..." or "Here is your updated design!".

#     3.  **`RESET`**: Use this when the user wants to start a completely new, different design. They will say things like "let's do an open house flyer next", "start over".

#     4.  **`CONVERSE`**: Use this ONLY for secondary situations, like greetings ("hi", "hello") or if you MUST ask a clarifying question. Do NOT use this if you can take a `MODIFY` action instead.

#     **CRITICAL RULES:**
#     - **NEVER MENTION TEMPLATES:** Do not mention the technical `template_uid` or the template's file name to the user.
#     - **AUTONOMOUS SELECTION:** **NEVER** ask the user to choose a template. Select the best one yourself.
#     - **PRICE FORMATTING:** If a user gives a price, format the `text` value with a dollar sign and commas (e.g., "$950,000").
#     - **IMMEDIATE ACTION:** Your first response to a design request MUST be the `MODIFY` action.

#     **REFERENCE DATA (Do not repeat in your response):**
#     - **AVAILABLE_TEMPLATES (with full layer details):** {json.dumps(templates_data, indent=2)}
#     - **CURRENT_DESIGN_CONTEXT (The design we are building right now):** {json.dumps(design_context, indent=2)}
#     """

#     conversation = [
#         {'role': 'user', 'parts': [system_prompt]},
#         {'role': 'model', 'parts': [f"Understood. I am an action-oriented design assistant for {COMPANY_NAME}. I will always use the provided tool. I will keep `MODIFY` and `GENERATE` actions strictly separate and will only say I'm generating an image when I use the `GENERATE` action."]}
#     ]
#     for msg in messages[-8:]:
#         if msg['role'] == 'assistant' and '![Generated Image]' in msg['content']:
#             continue
#         conversation.append({'role': 'user' if msg['role'] == 'user' else 'model', 'parts': [msg['content']]})

#     conversation.append({'role': 'user', 'parts': [user_prompt]})

#     return model.generate_content(conversation)

