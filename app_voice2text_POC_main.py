# app.py
import streamlit as st
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from util_functions import transcribe_audio, score_response, extract_score, log_to_sheet
import streamlit.components.v1 as components
import base64

# --- Secrets and Setup ---
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

# --- Step 1: Record ---
if st.session_state.step == 1:
    st.title("Interview Question Survey")
    st.markdown("### Step 1: Record your answer")
    st.markdown(QUESTION)

    components.html("""
    <!DOCTYPE html>
    <html>
      <body>
        <p><strong>Record your answer:</strong></p>
        <button id=\"start\">Start Recording</button>
        <button id=\"stop\" disabled>Stop Recording</button>
        <audio id=\"player\" controls></audio>

        <script>
          let mediaRecorder;
          let audioChunks = [];

          const startBtn = document.getElementById("start");
          const stopBtn = document.getElementById("stop");
          const player = document.getElementById("player");

          startBtn.onclick = async () => {
            audioChunks = [];
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);

            mediaRecorder.ondataavailable = e => {
              audioChunks.push(e.data);
            };

            mediaRecorder.onstop = async () => {
              const blob = new Blob(audioChunks, { type: "audio/wav" });
              player.src = URL.createObjectURL(blob);
              const reader = new FileReader();
              reader.onloadend = () => {
                const base64data = reader.result.split(',')[1];
                localStorage.setItem('audioBlob', base64data);
                location.reload();
              };
              reader.readAsDataURL(blob);
            };

            mediaRecorder.start();
            startBtn.disabled = true;
            stopBtn.disabled = false;
          };

          stopBtn.onclick = () => {
            mediaRecorder.stop();
            startBtn.disabled = false;
            stopBtn.disabled = true;
          };
        </script>
      </body>
    </html>
    """, height=300)

    if not st.session_state.audio_bytes:
        audio_blob = st.query_params.get("audioBlob", [None])[0]
        if audio_blob:
            st.session_state.audio_bytes = base64.b64decode(audio_blob)
            st.query_params.clear()

    if st.session_state.audio_bytes:
        st.audio(st.session_state.audio_bytes, format="audio/wav")
        if st.button("✅ Next Step"):
            with st.spinner("Transcribing..."):
                try:
                    transcript = transcribe_audio(st.session_state.audio_bytes, DEEPGRAM_API_KEY)
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
