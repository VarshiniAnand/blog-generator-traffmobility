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
CREDENTIALS_FILE = "/etc/secrets/automateblogposts.json"  # updated path for secret file

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
        print("🔁 Received request:", request.json)
        response = requests.post(HF_MODEL_URL, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and "generated_text" in result[0]:
                return result[0]["generated_text"].strip()
            else:
                return "[Error: Invalid response format]"
        else:
            return f"[Error {response.status_code}]: {response.text}"
    except requests.exceptions.Timeout:
        return "[Error: Hugging Face request timed out]"
    except Exception as e:
        return f"[Error: {str(e)}]"

def connect_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    return client.open(GOOGLE_SHEET_NAME).worksheet(WORKSHEET_NAME)

@app.route("/generate", methods=["POST"])
def generate_blog():
    try:
        row_num = int(request.json.get("row", 0))  # expects 2-based row number
        if row_num < 2:
            return jsonify({"error": "Invalid row number"}), 400

        sheet = connect_sheet()
        row_values = sheet.row_values(row_num)

        # Pad row to at least 3 columns to prevent IndexError
        while len(row_values) < 3:
            row_values.append("")

        title = row_values[0].strip()
        prompt = row_values[1].strip()
        status = row_values[2].strip().lower()

        if not prompt or status in ("done", "generated ✅", "completed"):
            return jsonify({"message": "No generation needed"}), 200

        meta_desc = generate(f"Write an SEO meta description for: {title}")
        header = generate(f"Write a compelling blog header for: {title}")
        content = generate(prompt)
        keywords = generate(f"List 5 SEO keywords for: {title}")

        if any(val.startswith("[Error") for val in [meta_desc, header, content, keywords]):
            return jsonify({"error": "One or more generation tasks failed"}), 500

        update_values = [[
            meta_desc, "", header, content, "", "Generated ✅", "", keywords
        ]]
        sheet.update(f"C{row_num}:J{row_num}", update_values)

        return jsonify({"status": "success", "row": row_num}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Render-compatible launch
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
