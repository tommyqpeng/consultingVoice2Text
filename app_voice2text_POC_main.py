import streamlit as st
import requests
import json
import gspread
import re
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from st_audiorec import st_audiorec

# --- Setup ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GSHEET_CREDS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(st.secrets["AnswerStorage_Sheet_ID"]).sheet1

DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
DEEPGRAM_API_KEY = st.secrets["DEEPGRAM_API_KEY"]
APP_PASSWORD = st.secrets["APP_PASSWORD"]

# --- Auth ---
if "password_attempts" not in st.session_state:
    st.session_state.password_attempts = 0
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "step" not in st.session_state:
    st.session_state.step = 1
if "audio_bytes" not in st.session_state:
    st.session_state.audio_bytes = None
if "transcript" not in st.session_state:
    st.session_state.transcript = ""
if "final_answer" not in st.session_state:
    st.session_state.final_answer = ""

st.title("Interview Question Survey")

if st.session_state.password_attempts >= 3:
    st.error("Too many incorrect attempts. Reload the page to try again.")
    st.stop()

if not st.session_state.authenticated:
    st.session_state.password_input = st.text_input("Enter access password", type="password")
    if st.button("Submit Password"):
        if st.session_state.password_input == APP_PASSWORD:
            st.session_state.authenticated = True
        else:
            st.session_state.password_attempts += 1
            st.warning(f"Incorrect password. Attempts left: {3 - st.session_state.password_attempts}")
    st.stop()

# --- Case Question ---
question = """
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

# --- Step 1: Show Question and Record ---
if st.session_state.step == 1:
    st.markdown("### Interview Question")
    st.markdown(question)
    st.markdown("### Step 1: Record your answer")
    audio_bytes = st_audiorec()

    if audio_bytes:
        st.session_state.audio_bytes = audio_bytes
        st.session_state.step = 2
        st.rerun()

# --- Step 2: Playback & Option to Re-record ---
elif st.session_state.step == 2:
    st.markdown("### Step 2: Listen to your answer")
    st.audio(st.session_state.audio_bytes, format="audio/wav")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Rerecord"):
            st.session_state.audio_bytes = None
            st.session_state.step = 1
            st.rerun()
    with col2:
        if st.button("Transcribe"):
            with st.spinner("Transcribing with Deepgram..."):
                response = requests.post(
                    "https://api.deepgram.com/v1/listen",
                    headers={
                        "Authorization": f"Token {DEEPGRAM_API_KEY}",
                        "Content-Type": "audio/wav"
                    },
                    data=st.session_state.audio_bytes
                )

                if response.status_code == 200:
                    st.session_state.transcript = response.json()["results"]["channels"][0]["alternatives"][0]["transcript"]
                    st.session_state.step = 3
                    st.rerun()
                else:
                    st.error("Transcription failed.")
                    st.code(response.text)

# --- Step 3: Show editable transcript ---
elif st.session_state.step == 3:
    st.markdown("### Step 3: Review and edit your transcript")
    st.session_state.final_answer = st.text_area("Edit your answer:", value=st.session_state.transcript, height=200)

    if st.button("Submit for Feedback"):
        st.session_state.step = 4
        st.rerun()

# --- Step 4: Score answer and show feedback ---
elif st.session_state.step == 4:
    st.markdown("### Step 4: Feedback on your answer")

    with st.spinner("Scoring your response..."):
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a McKinsey case interview coach scoring responses."},
                {"role": "user", "content": f"{RUBRIC}\n\nInterview question:\n{question}\n\nCandidate's answer:\n{st.session_state.final_answer}"}
            ],
            "temperature": 0.4
        }

        response = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, data=json.dumps(payload))

        if response.status_code == 200:
            feedback = response.json()["choices"][0]["message"]["content"]
            st.success("Scoring complete.")
            st.markdown("### Feedback")
            st.write(feedback)

            scores = [int(s) for s in re.findall(r"\b([0-9]{1,2}|100)\b", feedback)]
            avg_score = round(sum(scores) / len(scores), 1) if scores else "N/A"

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([timestamp, st.session_state.final_answer.strip(), feedback.strip(), avg_score])
            st.info("Your answer has been logged.")
        else:
            st.error(f"Deepseek API error: {response.status_code}")
            st.code(response.text)
