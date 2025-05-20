import requests
from datetime import datetime
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# --- upload any audio file to Google Drive ---
def upload_audio_to_drive(service_account_creds, file_bytes, filename, folder_id):
    service = build('drive', 'v3', credentials=service_account_creds)

    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }

    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype='audio/wav')
    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()

    return uploaded_file.get('id')

# --- Transcribe with Deepgram ---
def transcribe_audio(audio_bytes: bytes, api_key: str) -> str:
    response = requests.post(
        "https://api.deepgram.com/v1/listen",
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "audio/wav"
        },
        data=audio_bytes
    )
    if response.status_code == 200:
        return response.json()["results"]["channels"][0]["alternatives"][0]["transcript"]
    else:
        raise RuntimeError(f"Transcription failed: {response.text}")

# --- Score response with Deepseek ---
def score_response(deepseek_api_key: str, question: str, rubric: str, answer: str) -> str:
    headers = {
        "Authorization": f"Bearer {deepseek_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a McKinsey case interview coach scoring responses."},
            {"role": "user", "content": f"{rubric}\n\nInterview question:\n{question}\n\nCandidate's answer:\n{answer}"}
        ],
        "temperature": 0.4
    }
    response = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        raise RuntimeError(f"Deepseek scoring failed: {response.status_code}: {response.text}")

# --- Extract numeric score from feedback text ---
def extract_score(feedback: str) -> float:
    scores = [int(s) for s in re.findall(r"\b([0-9]{1,2}|100)\b", feedback)]
    return round(sum(scores) / len(scores), 1) if scores else None

# --- Log answer in Google Sheet ---
def log_to_sheet(sheet, answer: str, feedback: str, score: float):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        sheet.append_row([timestamp, answer.strip(), feedback.strip(), score])
        return True
    except Exception as e:
        raise RuntimeError(f"Google Sheets logging failed: {str(e)}")
