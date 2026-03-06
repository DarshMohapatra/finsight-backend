import httpx
from passlib.hash import pbkdf2_sha256

# ── SUPABASE CONFIG ──────────────────────────────────────────────
SUPABASE_URL = "https://rvgmqmfmbknxxdyqpcgz.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJ2Z21xbWZtYmtueHhkeXFwY2d6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI2MzE0NTUsImV4cCI6MjA4ODIwNzQ1NX0.8J0rgNuwM0WGDduHQiuDG6PxcrrPP4h62Uh2U1Hp3nA"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}
REST = f"{SUPABASE_URL}/rest/v1"

# ── HELPERS ──────────────────────────────────────────────────────
def _hash_pw(p):
    return pbkdf2_sha256.hash(p)

def _verify_pw(p, h):
    if h.startswith("$2b$") or h.startswith("$2a$"):
        return False
    return pbkdf2_sha256.verify(p, h)

# ── AUTH ─────────────────────────────────────────────────────────
def _login(email, password):
    email = email.strip().lower()
    r = httpx.get(
        f"{REST}/users", headers=HEADERS,
        params={"email": f"eq.{email}", "select": "id,email,display_name,age,password_hash"}
    )
    if r.status_code != 200:
        return {"success": False, "error": "Database error"}
    users = r.json()
    if not users:
        return {"success": False, "error": "Email not found."}
    u = users[0]
    if not _verify_pw(password, u["password_hash"]):
        return {"success": False, "error": "Incorrect password. If you used the old app, please reset your password."}
    pr = httpx.get(f"{REST}/user_preferences", headers=HEADERS,
                   params={"user_id": f"eq.{u['id']}", "select": "*"})
    prefs = pr.json()[0] if pr.json() else {}
    return {
        "success": True,
        "user_id": u["id"],
        "email": u.get("email", email),
        "display_name": u["display_name"],
        "name": u["display_name"],
        "age": u["age"],
        "prefs": prefs
    }

def _signup(email, password, name, age):
    email = email.strip().lower()
    r = httpx.get(f"{REST}/users", headers=HEADERS,
                  params={"email": f"eq.{email}", "select": "id"})
    if r.json():
        return {"success": False, "error": "Email already registered."}
    r = httpx.post(f"{REST}/users", headers=HEADERS,
                   json={"email": email, "display_name": name, "age": age,
                         "password_hash": _hash_pw(password)})
    if r.status_code not in (200, 201):
        return {"success": False, "error": f"Signup failed: {r.text}"}
    uid = r.json()[0]["id"]
    httpx.post(f"{REST}/user_preferences", headers=HEADERS, json={"user_id": uid})
    return {"success": True, "user_id": uid, "display_name": name, "name": name, "age": age, "prefs": {}}

def _reset_password(email, new_pw):
    email = email.strip().lower()
    r = httpx.get(f"{REST}/users", headers=HEADERS,
                  params={"email": f"eq.{email}", "select": "id"})
    if not r.json():
        return {"success": False, "error": "Email not found."}
    httpx.patch(f"{REST}/users", headers=HEADERS,
                params={"email": f"eq.{email}"},
                json={"password_hash": _hash_pw(new_pw)})
    return {"success": True}

# ── STATEMENTS ───────────────────────────────────────────────────
def _save_statements(user_id, records, filename):
    """
    Save analyzed transactions to Supabase tagged with filename.
    Full row stored in metadata JSONB so load can reconstruct exactly.
    """
    saved = 0
    errors = []
    for i in range(0, len(records), 100):
        batch = records[i:i+100]
        payload = []
        for rec in batch:
            rec["_source_file"] = filename  # tag so Statement History can group by file
            payload.append({
                "user_id":     user_id,
                "date":        str(rec.get("DATE", "")),
                "description": rec.get("TRANSACTION DETAILS", ""),
                "amount":      rec.get("WITHDRAWAL AMT", 0) or rec.get("DEPOSIT AMT", 0),
                "type":        "withdrawal" if rec.get("WITHDRAWAL AMT", 0) > 0 else "deposit",
                "category":    rec.get("CATEGORY", "Other"),
                "currency":    rec.get("CURRENCY", "IN"),
                "metadata":    rec
            })
        r = httpx.post(f"{REST}/transactions", headers=HEADERS, json=payload)
        if r.status_code in (200, 201):
            saved += len(batch)
        else:
            print(f"[save_statements] Supabase error {r.status_code}: {r.text}")
            errors.append(r.text)

    if errors:
        return {"success": False, "error": f"Partial save — {saved} saved. Error: {errors[0]}"}
    return {"success": True, "saved": saved}


def _load_statements(user_id):
    """Load all saved transactions using pagination to bypass the 1000 rows limit."""
    all_records = []
    limit = 1000
    offset = 0
    
    while True:
        r = httpx.get(
            f"{REST}/transactions", headers=HEADERS,
            params={
                "user_id": f"eq.{user_id}", 
                "select": "metadata", 
                "limit": limit, 
                "offset": offset
            }
        )
        if r.status_code != 200:
            print(f"[load_statements] Supabase error {r.status_code}: {r.text}")
            return {"success": False, "error": f"Could not fetch statements: {r.text}"}
        
        data = r.json()
        batch = [row["metadata"] for row in data if row.get("metadata")]
        all_records.extend(batch)
        
        # If we received fewer than 1000 rows, it means we've reached the end
        if len(data) < limit:
            break
            
        offset += limit
        
    return {"success": True, "records": all_records}


def _delete_account(user_id):
    """Permanently delete user — cascade handles transactions and preferences."""
    r = httpx.delete(f"{REST}/users", headers=HEADERS,
                     params={"id": f"eq.{user_id}"})
    return {"success": r.status_code in (200, 204)}