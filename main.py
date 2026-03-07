import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Our newly split logic files
import auth
import analyzer
from ai_advisor import generate_chat_response
from forecaster import generate_forecast
import smartcash
import invest
import gmail_auth
import gmail_scanner
import gmail_fetcher

app = Flask(__name__)
# Adding CORS support and allow cross-origin requests
CORS(app, resources={r"/*": {"origins": "*"}})


# Vercel's filesystem is read-only except /tmp
UPLOAD_FOLDER = '/tmp/uploads' if os.environ.get('VERCEL') else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ----- AUTH ENDPOINTS -----
@app.post("/auth/login")
def login():
    data = request.get_json()
    result = auth._login(data["email"], data["password"])
    return jsonify(result), 200 if result.get("success") else 401

@app.post("/auth/signup")
def signup():
    data = request.get_json()
    result = auth._signup(data["email"], data["password"], data["name"], data["age"])
    return jsonify(result), 200 if result.get("success") else 400

@app.post("/auth/reset-password")
def reset_password():
    data = request.get_json()
    result = auth._reset_password(data["email"], data["new_password"])
    return jsonify(result), 200 if result.get("success") else 400

@app.post("/auth/save-statements")
def save_statements():
    data = request.json
    result = auth._save_statements(data["user_id"], data["records"], data.get("filename", "Cloud Backup"))
    return jsonify(result), 200 if result.get("success") else 500

@app.get("/auth/statements/<user_id>")
def load_statements(user_id):
    result = auth._load_statements(user_id)
    return jsonify(result), 200 if result.get("success") else 500

@app.delete("/auth/account")
def delete_account():
    data = request.json
    result = auth._delete_account(data["user_id"])
    return jsonify(result), 200 if result.get("success") else 500

# ── SAVED CARDS ───────────────────────────────────────────────────
@app.get("/auth/cards/<user_id>")
def get_saved_cards(user_id):
    return jsonify(auth._load_cards(user_id))

@app.post("/auth/cards")
def save_card():
    data = request.json
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "user_id required"}), 400
    return jsonify(auth._save_card(user_id, data))

@app.delete("/auth/cards")
def delete_card():
    data = request.json
    user_id = data.get("user_id")
    card_db_id = data.get("card_db_id")
    if not user_id or not card_db_id:
        return jsonify({"success": False, "error": "user_id and card_db_id required"}), 400
    return jsonify(auth._delete_card(user_id, card_db_id))

# ----- UPLOAD ENDPOINT -----
@app.post("/api/upload")
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400

    password = request.form.get("password", "")

    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            # Processing the file via our newly split analyzer logic
            result = analyzer.process_uploaded_file(filepath, filename, password)
            return jsonify(result), 200 if result.get("success") else 400
        except ValueError as e:
            # Catching known errors like incorrect password
            return jsonify({"success": False, "error": str(e)}), 400
        except Exception as e:
            # Printing the FULL traceback to the Flask terminal
            import traceback
            traceback.print_exc()
            # Catching unknown errors
            return jsonify({"success": False, "error": f"Failed to process file: {str(e)}"}), 500
        finally:
            # Deleting the file from the server immediately after processing for privacy
            if os.path.exists(filepath):
                os.remove(filepath)
# ── GMAIL ─────────────────────────────────────────────────────────
@app.post("/api/gmail/validate")
def gmail_validate():
    """
    Validate Google OAuth token and confirm gmail.readonly scope is granted.
    Body: { access_token }
    Returns: { success, email, scopes }
    """
    data  = request.json
    token = data.get("access_token", "")
    if not token:
        return jsonify({"success": False, "error": "No token provided"}), 400
    result = gmail_auth.validate_token(token)
    return jsonify(result), 200 if result.get("success") else 401


@app.post("/api/gmail/scan")
def gmail_scan():
    """
    Scan Gmail inbox for bank statement emails with PDF attachments.
    Body: { access_token }
    Returns: { success, emails: [{id, subject, from, bank_name, date, attachments}], count }
    """
    data  = request.json
    token = data.get("access_token", "")
    if not token:
        return jsonify({"success": False, "error": "No token provided"}), 400
    result = gmail_scanner.scan_for_statements(token)
    return jsonify(result), 200 if result.get("success") else 500


@app.post("/api/gmail/fetch")
def gmail_fetch():
    """
    Download a Gmail PDF attachment, analyze it, return transactions.
    Body: { access_token, message_id, attachment_id, filename, password? }
    Returns: same shape as /api/upload → { success, transactions, summary, currency }
    """
    data          = request.json
    token         = data.get("access_token", "")
    message_id    = data.get("message_id", "")
    attachment_id = data.get("attachment_id", "")
    filename      = data.get("filename", "statement.pdf")
    password      = data.get("password", "")

    if not all([token, message_id, attachment_id]):
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    result = gmail_fetcher.fetch_and_process(
        token, message_id, attachment_id, filename, password,
        analyzer=analyzer,
    )
    return jsonify(result), 200 if result.get("success") else 400


@app.post("/api/gmail/revoke")
def gmail_revoke():
    """Revoke the OAuth token — called when user closes the dialog."""
    data  = request.json
    token = data.get("access_token", "")
    if token:
        gmail_auth.revoke_token(token)
    return jsonify({"success": True})


# ----- FORECAST ENDPOINT -----
@app.post("/api/forecast")
def fetch_forecast():
    data = request.json
    transactions = data.get('transactions', [])
    result = generate_forecast(transactions)
    return jsonify(result)

# ----- AI CHAT ENDPOINT -----
@app.post("/api/chat")
def ask_ai():
    data = request.json
    transactions = data.get("transactions", [])
    history = data.get("history", [])
    message = data.get("message", "")
    currency = data.get("currency", "IN")
    
    if not message:
        return jsonify({"error": "Empty message"}), 400
        
    profile = data.get("profile", None)
    result = generate_chat_response(transactions, history, message, currency, profile)
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)

    # ----- SMARTCASH ENDPOINT -----
@app.route("/api/smartcash/cards", methods=["GET"])
def get_available_cards():
    currency = request.args.get("currency", "IN")
    cards = smartcash.get_cards_for_currency(currency)
    return jsonify({"success": True, "cards": cards})

@app.post("/api/smartcash/analyze")
def analyze_smartcash():
    data = request.json
    transactions = data.get("transactions", [])
    wallet_ids = data.get("wallet", [])
    currency = data.get("currency", "IN")
    
    result = smartcash.generate_smartcash_report(transactions, wallet_ids, currency)
    return jsonify(result), 200 if result.get("success") else 400


# ----- INVEST / MICROROUNDUP ENDPOINT -----
@app.post("/api/invest/analyze")
def analyze_invest():
    data = request.json
    transactions = data.get("transactions", [])
    threshold = int(data.get("threshold", 10))
    
    result = invest.mu_compute_roundups(transactions, threshold)
    return jsonify(result), 200 if result.get("success") else 400


# ----- HEALTH CHECK -----
@app.get("/")
def health():
    return jsonify({"status": "ok", "message": "FinSight API running!"})

if __name__ == '__main__':
    # Use the PORT environment variable if it exists, otherwise default to 8000
    import os
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
