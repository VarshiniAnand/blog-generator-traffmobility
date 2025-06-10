from flask import Flask, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import time
import os


app = Flask(__name__)

# === CONFIGURATION ===
HF_API_TOKEN = os.environ.get("HF_API_TOKEN")
MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.3"
HF_MODEL_URL = f"https://api-inference.huggingface.co/models/{MODEL_NAME}"
GOOGLE_SHEET_NAME = "Automate Blog Posts"
WORKSHEET_NAME = "Basic"
CREDENTIALS_FILE = "automateblogposts-c59de57c8731.json"

headers = {
    "Authorization": f"Bearer {HF_API_TOKEN}",
    "Content-Type": "application/json"
}

def generate(prompt):
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 300,
            "temperature": 0.7,
            "top_p": 0.9,
            "do_sample": True
        }
    }
    try:
        response = requests.post(HF_MODEL_URL, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and "generated_text" in result[0]:
                return result[0]["generated_text"].strip()
            else:
                return "[Error: Invalid response format]"
        else:
            return f"[Error {response.status_code}]: {response.text}"
    except Exception as e:
        return f"[Error: {str(e)}]"

def connect_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    return client.open(GOOGLE_SHEET_NAME).worksheet(WORKSHEET_NAME)

@app.route("/generate", methods=["POST"])
def generate_blog():
    sheet = connect_sheet()
    data = sheet.get_all_records()

    for i, row in enumerate(data):
        row_num = i + 2  # header offset
        title = row.get("Title", "").strip()
        prompt = row.get("Prompt", "").strip()
        status = row.get("Status", "").strip().lower()

        if not prompt or status in ("done", "generated ✅", "completed"):
            continue

        meta_desc = generate(f"Write an SEO meta description for: {title}")
        header = generate(f"Write a compelling blog header for: {title}")
        content = generate(prompt)
        keywords = generate(f"List 5 SEO keywords for: {title}")

        if any(val.startswith("[Error") for val in [meta_desc, header, content, keywords]):
            continue

        update_range = f"C{row_num}:J{row_num}"
        update_values = [[
            meta_desc, "", header, content, "", "Generated ✅", "", keywords
        ]]
        sheet.update(update_range, update_values)
        time.sleep(2)

    return jsonify({"status": "success"}), 200

# Required for Render
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
