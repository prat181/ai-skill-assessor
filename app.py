import streamlit as st
import json
import os
from groq import Groq
from dotenv import load_dotenv
from PyPDF2 import PdfReader

# Load Environment Variables
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    st.error("Missing API Key. Please check your .env file.")
    st.stop()

# Initialize Groq Client
client = Groq(api_key=api_key)
MODEL_NAME = 'llama-3.1-8b-instant'

# --- Helper Function: Extract Text from PDF ---
def extract_text_from_pdf(pdf_file):
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        if page.extract_text():
            text += page.extract_text()
    return text

# Session State Management
if "current_phase" not in st.session_state:
    st.session_state.current_phase = "input"
    st.session_state.extracted_data = None
    st.session_state.skills_to_test = []
    st.session_state.current_skill_index = 0
    st.session_state.assessment_results = {}
    st.session_state.current_question = None

st.set_page_config(page_title="AI Skill Assessor", layout="wide")
st.title(" AI-Powered Skill Assessment Agent")

# --- PHASE 1: Document Input ---
if st.session_state.current_phase == "input":
    st.header("1. Upload Documents")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Job Description")
        jd_file = st.file_uploader("Upload JD (PDF)", type="pdf", key="jd_upload")
        jd_text = st.text_area("Or paste JD here", height=150)
        
    with col2:
        st.subheader("Candidate Resume")
        resume_file = st.file_uploader("Upload Resume (PDF)", type="pdf", key="res_upload")
        resume_text = st.text_area("Or paste Resume here", height=150)

    if st.button("Initialize Assessment", type="primary"):
        final_jd = extract_text_from_pdf(jd_file) if jd_file else jd_text
        final_resume = extract_text_from_pdf(resume_file) if resume_file else resume_text
        
        if final_jd and final_resume:
            with st.spinner("AI is analyzing documents..."):
                try:
                    extraction_prompt = f"""
                    You are an expert HR AI. Extract the following from these documents and output ONLY a valid JSON object. Do not include any other text or markdown formatting.
                    
                    Required JSON structure:
                    {{
                        "target_role": "Job Title",
                        "claimed_skills_found": ["Skill 1", "Skill 2", "Skill 3"]
                    }}

                    Job Description:
                    {final_jd}

                    Candidate Resume:
                    {final_resume}
                    """
                    
                    response = client.chat.completions.create(
                        messages=[{"role": "user", "content": extraction_prompt}],
                        model=MODEL_NAME,
                        response_format={"type": "json_object"}
                    )
                    
                    st.session_state.extracted_data = json.loads(response.choices[0].message.content)
                    st.session_state.skills_to_test = st.session_state.extracted_data.get("claimed_skills_found", [])[:3]
                    st.session_state.current_phase = "interview"
                    st.rerun()
                except Exception as e:
                    st.error(f"Error during extraction: {e}")
        else:
            st.warning("Please provide both documents.")

# --- PHASE 2: Interview Loop ---
elif st.session_state.current_phase == "interview":
    role = st.session_state.extracted_data.get('target_role', 'Position')
    st.header(f"Interviewer Bot: {role}")
    
    curr_idx = st.session_state.current_skill_index
    skills = st.session_state.skills_to_test
    
    if curr_idx < len(skills):
        skill = skills[curr_idx]
        st.write(f"**Step {curr_idx + 1} of {len(skills)}: Assessing {skill}**")
        
        if st.session_state.current_question is None:
            with st.spinner("Thinking..."):
                ask_prompt = f"You are a strict technical interviewer. Ask exactly ONE practical, scenario-based question about {skill} for a {role} role. Output ONLY the question text, nothing else."
                q_res = client.chat.completions.create(
                    messages=[{"role": "user", "content": ask_prompt}],
                    model=MODEL_NAME
                )
                st.session_state.current_question = q_res.choices[0].message.content
                st.rerun()
        
        st.info(st.session_state.current_question)
        
        with st.form(key="answer_form", clear_on_submit=True):
            user_answer = st.text_area("Your Response:")
            if st.form_submit_button("Submit Answer") and user_answer:
                with st.spinner("Evaluating..."):
                    eval_prompt = f"""
                    Evaluate this interview answer strictly. Output ONLY a valid JSON object. Do not include markdown formatting.
                    
                    Required JSON structure:
                    {{
                        "score": [number 1-5],
                        "feedback": "Your detailed feedback string"
                    }}
                    
                    Question: {st.session_state.current_question}
                    Answer: {user_answer}
                    """
                    e_res = client.chat.completions.create(
                        messages=[{"role": "user", "content": eval_prompt}],
                        model=MODEL_NAME,
                        response_format={"type": "json_object"}
                    )
                    st.session_state.assessment_results[skill] = json.loads(e_res.choices[0].message.content)
                    st.session_state.current_skill_index += 1
                    st.session_state.current_question = None
                    st.rerun()
    else:
        st.session_state.current_phase = "report"
        st.rerun()

# --- PHASE 3: Final Report ---
elif st.session_state.current_phase == "report":
    st.header("Assessment Results & Learning Plan")
    with st.spinner("Generating final report..."):
        plan_prompt = f"Generate a clean, structured learning plan based on these results: {json.dumps(st.session_state.assessment_results)}. Use markdown headers and bullet points."
        plan = client.chat.completions.create(
            messages=[{"role": "user", "content": plan_prompt}],
            model=MODEL_NAME
        )
        st.markdown(plan.choices[0].message.content)
    
    if st.button("Start New Assessment"):
        st.session_state.clear()
        st.rerun()
