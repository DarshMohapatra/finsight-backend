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

app = Flask(__name__)
# Adding CORS support and allow cross-origin requests
CORS(app, origins=["http://localhost:5173"])

# We need a temp folder to save uploaded files before pandas reads them
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
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
        
    result = generate_chat_response(transactions, history, message, currency)
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
