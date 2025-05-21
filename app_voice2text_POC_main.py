# app.py
import streamlit as st
from datetime import datetime 
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from util_functions import transcribe_audio, score_response, extract_score, log_to_sheet, upload_audio_to_drive
from st_audiorec import st_audiorec

# --- Secrets and Setup ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/drive.file"]
creds_dict = json.loads(st.secrets["GSHEET_CREDS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(st.secrets["AnswerStorage_Sheet_ID"]).sheet1
DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
DEEPGRAM_API_KEY = st.secrets["DEEPGRAM_API_KEY"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]
AUDIO_FOLDER_ID = st.secrets["AUDIO_FOLDER_ID"]

# --- Auth ---
if "password_attempts" not in st.session_state:
    st.session_state.password_attempts = 0
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("Interview Question Survey")
    st.session_state.password_input = st.text_input("Enter access password", type="password")
    if st.button("Submit Password"):
        if st.session_state.password_input == APP_PASSWORD:
            st.session_state.authenticated = True
        else:
            st.session_state.password_attempts += 1
            st.warning(f"Incorrect password. Attempts left: {3 - st.session_state.password_attempts}")
    st.stop()

# --- Session State ---
if "step" not in st.session_state:
    st.session_state.step = 1
if "audio_bytes" not in st.session_state:
    st.session_state.audio_bytes = None
if "transcript" not in st.session_state:
    st.session_state.transcript = ""
if "final_answer" not in st.session_state:
    st.session_state.final_answer = ""

# --- Constants ---
QUESTION = """
**Client goal**  
Our client is SuperSoda, a top-three beverage producer in the United States that has approached McKinsey for help designing its product launch strategy.  

**Situation description**  
As an integrated beverage company, SuperSoda leads its own brand design, marketing, and sales efforts. The company also owns its entire beverage supply chain, including production of concentrates, bottling and packaging, and distribution to retail outlets. SuperSoda has a considerable number of brands across carbonated and noncarbonated drinks, five large bottling plants throughout the country, and distribution agreements with most major retailers.

SuperSoda is evaluating the launch of a new product, a flavored sports drink called “Electro-Light.” Sports drinks are usually designed to replenish energy, with sugars, and electrolytes, or salts, in the body. However, Electro-Light has been formulated to focus more on the replenishment of electrolytes and has a lower sugar content compared to most other sports drinks. The company expects this new beverage to capitalize on the recent trend away from high-sugar products.

**McKinsey study**  
SuperSoda’s vice president of marketing has asked McKinsey to help analyze key factors surrounding the launch of Electro-Light and its own internal capabilities to support that effort.  

**Question**  
What key factors should SuperSoda consider when deciding whether or not to launch Electro-Light?
"""

RUBRIC = """
Score this case interview answer using the following criteria:
1. Whether the person clarified the context
2. Whether the person asked for time to consider the question
3. Whether the person came up with a framework with 3 to 4 buckets
4. Whether the person presented the buckets in a top-down format, where they introduce what's inside the 3 to 4 buckets
5. Whether the content of the buckets are specific to the case
6. Whether the person ended with a specific area to prioritize analysis of for the next question
Provide a score (poor, acceptable, or good) and 1 sentence of feedback for each criteria.
"""

# --- Step 1: Record or Upload ---
if st.session_state.step == 1:
    st.title("Interview Question Survey")
    st.markdown("### Step 1: Record or upload your answer")
    st.markdown(QUESTION)

    st.markdown("#### Option 1: Record")
    recorded_audio = st_audiorec()

    st.markdown("#### Option 2: Upload .wav or .m4a")
    uploaded_file = st.file_uploader("Upload audio file", type=["wav", "m4a"])

    audio_bytes = recorded_audio or (uploaded_file.read() if uploaded_file else None)

    if audio_bytes:
        st.session_state.audio_bytes = audio_bytes
    
        # # --- Upload to Google Drive ---
        # filename = f"response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        # try:
        #     file_id = upload_audio_to_drive(creds, audio_bytes, filename, AUDIO_FOLDER_ID)
        #     st.success(f"Audio uploaded to Drive (file ID: {file_id})")
        # except Exception as e:
        #     st.warning(f"Could not upload to Google Drive: {e}")
    
        # --- Transcribe ---
        with st.spinner("Transcribing..."):
            try:
                transcript = transcribe_audio(audio_bytes, DEEPGRAM_API_KEY)
                st.session_state.transcript = transcript
                st.session_state.step = 2
                st.rerun()
            except Exception as e:
                st.error(str(e))

# --- Step 2: Edit transcript ---
elif st.session_state.step == 2:
    st.markdown("### Step 2: Edit your answer transcript")
    st.session_state.final_answer = st.text_area("Edit if needed:", value=st.session_state.transcript, height=200)
    if st.button("Submit for Feedback"):
        st.session_state.step = 3
        st.rerun()

# --- Step 3: Feedback ---
elif st.session_state.step == 3:
    st.markdown("### Step 3: Feedback on your answer")
    with st.spinner("Scoring..."):
        try:
            feedback = score_response(DEEPSEEK_API_KEY, QUESTION, RUBRIC, st.session_state.final_answer)
            score = extract_score(feedback)
            logged = log_to_sheet(sheet, st.session_state.final_answer, feedback, score)
            st.success("Feedback complete and logged!")
            st.markdown("#### Feedback")
            st.write(feedback)
        except Exception as e:
            st.error(str(e))
