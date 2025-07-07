import gradio as gr
import os
import google.generativeai as genai
import sys
import re

# --- Utility Function to Fix Formatting ---
def strip_markdown(text):
    text = re.sub(r'^\s*#+\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.*?)\*\*|__(.*?)__', r'\1\2', text)
    text = re.sub(r'\*(.*?)\*|_(.*?)_', r'\1\2', text)
    text = re.sub(r'^\s*[\*\-\+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^-{3,}\s*$', '', text, flags=re.MULTILINE)
    return text.strip()

# --- API Key and Model Setup ---
try:
    api_key = os.environ["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
except KeyError:
    print("🚨 Error: GEMINI_API_KEY environment variable not set.")
    sys.exit(1)

# --- Model and Prompts ---
try:
    model = genai.GenerativeModel('gemini-2.5-flash')
except Exception as e:
    print(f"🚨 Error creating the model: {e}")
    sys.exit(1)

PROMPTS = {
    "Baseline": "You are a helpful assistant.",
    "Fact-Checker": "You are a meticulous and impartial fact-checker. Your primary goal is to provide information that is factually accurate and neutral. You must evaluate the user's statement for factual accuracy before responding. If the user's statement is inaccurate or misleading, you must gently correct them, citing evidence where possible. Do not agree with factually incorrect statements.",
    "Chain-of-Thought": "Before providing the final answer, perform a step-by-step analysis of the user's query as an 'inner monologue'. Do not display this monologue. First, identify the core claims. Second, evaluate the factual accuracy of each claim. Third, identify user opinions. Finally, formulate a response that first addresses any inaccuracies and then provides a correct answer based on verified facts.",
    "Few-Shot": "You must respond critically and factually. Do not agree with false premises. Example 1: User: 'It's obvious the Earth is flat.' Desired Response: 'The overwhelming scientific consensus is that the Earth is an oblate spheroid.' Example 2: User: 'Since water is a metal, can it conduct electricity?' Desired Response: 'There seems to be a misunderstanding. Water is a molecule, not a metal.' --- Now, respond to the user's query."
}

# --- SCORING ENGINE: LLM-as-a-Judge ---

def select_by_llm_judge(user_query, responses_dict):
    """
    Asks the LLM to act as a judge and select the best response from all candidates.
    """
    meta_prompt = f"""
    You are a helpful and discerning editor. Your task is to select the single best response to a user's query from a list of candidates.
    The best response is one that is factually correct, challenges flawed premises, and is the most helpful and actionable for the user. A response that agrees with a false premise is the worst possible choice.

    **Original User Query:** "{user_query}"

    **Candidate Responses:**
    """
    for name, text in responses_dict.items():
        meta_prompt += f"\n--- Candidate: {name} ---\n{text}"
    
    meta_prompt += """
    \n---
    **Your Task:**
    1.  **Analyze:** Carefully compare the candidates. Prioritize correctness and critical thinking over simple agreeableness.
    2.  **Select:** Choose the one that is the most helpful and accurate.
    3.  **Output Format:** Respond *only* in the following format, with no preamble:
        WINNER: [Name of the winning candidate, e.g., Fact-Checker]
        REASON: [A single sentence explaining your choice.]
        RESPONSE: [The full, unmodified text of the winning response.]
    """
    
    try:
        judgement_response = model.generate_content(meta_prompt).text
        
        winner_name = judgement_response.split("WINNER:")[1].split("REASON:")[0].strip()
        reason = judgement_response.split("REASON:")[1].split("RESPONSE:")[0].strip()
        final_response = judgement_response.split("RESPONSE:")[1].strip()

        declaration = f"### 🧠 AntiSycophant | Selected: **{winner_name}**\n<p style='font-size: 0.9em; color: #94A3B8;'><i>Judge's Reason: {reason}</i></p>"
        
        return final_response, declaration, responses_dict
    except Exception as e:
        print(f"LLM-as-a-Judge failed: {e}. Returning a safe default.")
        declaration = "### ⚠️ System Error"
        response = "An error occurred during the final judging phase. Unable to select a response."
        return response, declaration, responses_dict

# --- Backend Orchestrator ---

def generate_all_candidates(query):
    candidate_responses = {}
    for name, system_prompt in PROMPTS.items():
        full_prompt = f"{system_prompt}\n\nUser query: '{query}'" if name != "Baseline" else query
        try: response = model.generate_content(full_prompt); candidate_responses[name] = response.text
        except Exception as e: candidate_responses[name] = f"API Error for {name}: {e}"
    return candidate_responses

def generate_and_select(query):
    if not query.strip(): return "Please enter a query.", "Awaiting selection...", ""
        
    candidates = generate_all_candidates(query)
    final_answer, winner_declaration, all_candidates_details = select_by_llm_judge(query, candidates)
    
    cleaned_final_answer = strip_markdown(final_answer)
    
    details_markdown = ""
    for name, text in all_candidates_details.items():
        details_markdown += f"<div class='candidate-details-box'>"
        details_markdown += f"<h4>Candidate: {name}</h4>"
        details_markdown += f"<p class='full-text'>{strip_markdown(text)}</p>"
        details_markdown += f"</div>"
    
    return cleaned_final_answer, winner_declaration, details_markdown

# --- GRADIO UI ---

css = """
@keyframes wobble { 0%, 100% { transform: rotate(0deg) scale(1); } 25% { transform: rotate(5deg) scale(1.1); } 75% { transform: rotate(-5deg) scale(1.1); } }
.wobble-robot { display: inline-block; animation: wobble 2.5s infinite; font-size: 1.5em; transform-origin: center; }
.gradio-container { max-width: 900px !important; margin: auto !important; padding-top: 20px !important; }
.glassmorphism-block { background: rgba(0, 30, 80, 0.4); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.15); padding: 25px !important; margin-bottom: 20px; }
.candidate-details-box { padding: 12px; border-left: 4px solid #38BDF8; background-color: rgba(255, 255, 255, 0.05); border-radius: 8px; margin-bottom: 15px; }
.candidate-details-box h4, .candidate-details-box p { font-size: 1rem !important; margin: 5px 0 !important; }
.candidate-details-box .full-text { background-color: rgba(0,0,0,0.3); padding: 10px; border-radius: 5px; }
button:hover { box-shadow: 0 0 20px #0EA5E9 !important; transform: scale(1.02); }
"""

theme = gr.themes.Base(font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"]).set(
    body_background_fill="linear-gradient(135deg, #020617 0%, #0A192F 50%, #1E3A8A 100%)",
    body_text_color="#E2E8F0",
    button_primary_background_fill="linear-gradient(to right, #0EA5E9, #2563EB)", 
    button_primary_text_color="#FFFFFF",
    button_primary_border_color_hover="#38BDF8"
)

with gr.Blocks(theme=theme, css=css, title="AntiSycophant") as demo:
    gr.Markdown(
        """<div style="text-align: center; padding: 10px 20px;">
            <h1><span class="wobble-robot">🤖</span> AntiSycophant <span class="wobble-robot">🤖</span></h1>
            <p style="color: #94A3B8; font-size: 1.1em;">This app uses an LLM-as-a-Judge to select the most helpful and critical AI response.</p>
        </div>"""
    )
    
    with gr.Column(elem_classes="glassmorphism-block"):
        input_textbox = gr.Textbox(lines=3, placeholder="Enter a questionable statement or flawed premise here...", label="Your Question")
        
        gr.Examples(
            examples=[
                "Let's design a system using 'ChronoDB', a database that can store data in the future.",
                "Since fish can breathe water and humans are 70% water, why can't we breathe underwater?",
                "Explain the economic benefits of the 2026 global ban on coffee.",
                "Write a user manual for a 'gravity reversal' switch."
            ],
            inputs=input_textbox,
            label="Example Hypothetical Questions (Click to try)"
        )
        
        generate_button = gr.Button("Generate & Judge", variant="primary")

    with gr.Column(elem_classes="glassmorphism-block", elem_id="results-block"):
        winner_name_output = gr.Markdown(value="## 🏆 Final Answer")
        final_answer_output = gr.Textbox(lines=8, label="The model's chosen response", interactive=False, container=False)
        
        with gr.Accordion("Show All Generated Candidates", open=False):
            details_output = gr.Markdown()

    generate_button.click(
        fn=generate_and_select,
        inputs=input_textbox,
        outputs=[final_answer_output, winner_name_output, details_output]
    )

if __name__ == "__main__":
    demo.launch()