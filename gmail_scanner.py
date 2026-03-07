import httpx

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"

# KNOWN BANK SENDER DOMAINS
BANK_SENDERS = [
    # India
    "hdfcbank.net", "hdfcbank.com",
    "icicibank.com",
    "sbicard.com", "onlinesbi.com", "sbi.co.in",
    "axisbank.com",
    "kotak.com",
    "yesbank.in",
    "indusind.com",
    "idfcfirstbank.com",
    "rblbank.com",
    "federalbank.co.in",
    "pnb.co.in",
    "bankofbaroda.in",
    "canarabank.in",
    # International
    "citibank.com",
    "sc.com",
    "hsbc.co.in", "hsbc.com",
    "chase.com",
    "bankofamerica.com",
    "wellsfargo.com",
    "barclays.co.uk", "barclays.com",
    "lloydsbank.com",
    "natwest.com",
    "td.com",
    "rbc.com",
    "anz.com",
    "commbank.com.au",
]

# FRIENDLY DISPLAY NAMES 
BANK_DISPLAY = {
    "hdfcbank.net":      "HDFC Bank",
    "hdfcbank.com":      "HDFC Bank",
    "icicibank.com":     "ICICI Bank",
    "sbicard.com":       "SBI Card",
    "onlinesbi.com":     "SBI",
    "axisbank.com":      "Axis Bank",
    "kotak.com":         "Kotak Bank",
    "yesbank.in":        "Yes Bank",
    "indusind.com":      "IndusInd Bank",
    "idfcfirstbank.com": "IDFC First Bank",
    "rblbank.com":       "RBL Bank",
    "citibank.com":      "Citibank",
    "chase.com":         "Chase",
    "bankofamerica.com": "Bank of America",
    "wellsfargo.com":    "Wells Fargo",
    "barclays.co.uk":    "Barclays",
    "barclays.com":      "Barclays",
    "lloydsbank.com":    "Lloyds Bank",
    "hsbc.co.in":        "HSBC",
    "hsbc.com":          "HSBC",
    "natwest.com":       "NatWest",
    "td.com":            "TD Bank",
    "rbc.com":           "RBC",
    "anz.com":           "ANZ",
    "commbank.com.au":   "Commonwealth Bank",
}


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def scan_for_statements(access_token, max_results=40, months=6):
    """
    Search Gmail for emails with PDF attachments that could be bank statements.
    Three-pass strategy (deduplicated by message ID):
      1) Emails from known bank sender domains with PDF attachments
      2) Any email with PDF attachment (catches self-sent, forwarded statements)
    After fetching metadata, we keep emails whose PDF filenames look like statements
    or come from known banks.
    """
    from datetime import datetime, timedelta

    h = _headers(access_token)
    after_date = (datetime.now() - timedelta(days=months * 30)).strftime("%Y/%m/%d")

    # -- Pass 1: known bank senders --
    sender_q = " OR ".join([f"from:{s}" for s in BANK_SENDERS[:15]])
    query1   = f"({sender_q}) has:attachment filename:pdf after:{after_date}"

    # -- Pass 2: ANY email with a PDF attachment (broad catch-all) --
    query2   = f"has:attachment filename:pdf after:{after_date}"

    seen_ids = set()
    all_refs = []

    for query in [query1, query2]:
        r = httpx.get(
            f"{GMAIL_API}/users/me/messages",
            headers=h,
            params={"q": query, "maxResults": max_results},
            timeout=20,
        )
        if r.status_code != 200:
            continue
        for ref in r.json().get("messages", []):
            if ref["id"] not in seen_ids:
                seen_ids.add(ref["id"])
                all_refs.append(ref)

    if not all_refs:
        return {"success": True, "emails": [], "count": 0}

    # Fetch metadata for up to 30 messages
    emails = []
    for ref in all_refs[:30]:
        meta = _get_message_meta(ref["id"], h)
        if meta:
            emails.append(meta)

    emails.sort(key=lambda e: e.get("date", ""), reverse=True)
    return {"success": True, "emails": emails, "count": len(emails)}


def _get_message_meta(message_id, headers):
    """Fetch subject, sender, date and PDF attachment list for one message."""
    r = httpx.get(
        f"{GMAIL_API}/users/me/messages/{message_id}",
        headers=headers,
        params={
            "format": "metadata",
            "metadataHeaders": ["From", "Subject", "Date"],
        },
        timeout=15,
    )
    if r.status_code != 200:
        return None

    data        = r.json()
    hmap        = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
    attachments = []
    _walk_parts(data.get("payload", {}), message_id, attachments)

    if not attachments:
        return None  # skip if no PDF found

    sender_raw  = hmap.get("From", "")
    bank_name   = _resolve_bank_name(sender_raw)

    # If sender isn't a known bank, try to detect bank from attachment filenames
    if bank_name == sender_raw or not any(d in sender_raw.lower() for d in BANK_DISPLAY):
        for att in attachments:
            detected = _detect_bank_from_filename(att.get("filename", ""))
            if detected:
                bank_name = detected
                break

    return {
        "id":          message_id,
        "subject":     hmap.get("Subject", "(No Subject)"),
        "from":        sender_raw,
        "bank_name":   bank_name,
        "date":        hmap.get("Date", ""),
        "attachments": attachments,
    }


def _walk_parts(part, message_id, result):
    """Recursively walk MIME parts to collect PDF attachment metadata."""
    mime   = part.get("mimeType", "")
    fname  = part.get("filename", "")
    body   = part.get("body", {})
    att_id = body.get("attachmentId")

    if att_id and (mime == "application/pdf" or fname.lower().endswith(".pdf")):
        result.append({
            "attachment_id": att_id,
            "filename":      fname or "statement.pdf",
            "size_kb":       round(body.get("size", 0) / 1024, 1),
            "message_id":    message_id,
        })

    for sub in part.get("parts", []):
        _walk_parts(sub, message_id, result)


FILENAME_BANK_HINTS = {
    "hdfc":          "HDFC Bank",
    "icici":         "ICICI Bank",
    "sbi":           "SBI",
    "axis":          "Axis Bank",
    "kotak":         "Kotak Bank",
    "indusind":      "IndusInd Bank",
    "idfc":          "IDFC First Bank",
    "rbl":           "RBL Bank",
    "yes bank":      "Yes Bank",
    "yesbank":       "Yes Bank",
    "federal":       "Federal Bank",
    "canara":        "Canara Bank",
    "pnb":           "PNB",
    "baroda":        "Bank of Baroda",
    "citi":          "Citibank",
    "chase":         "Chase",
    "bofa":          "Bank of America",
    "bankofamerica": "Bank of America",
    "wellsfargo":    "Wells Fargo",
    "wells fargo":   "Wells Fargo",
    "barclays":      "Barclays",
    "lloyds":        "Lloyds Bank",
    "hsbc":          "HSBC",
    "natwest":       "NatWest",
    "td bank":       "TD Bank",
    "anz":           "ANZ",
    "commbank":      "Commonwealth Bank",
    "sc ":           "Standard Chartered",
}


def _detect_bank_from_filename(filename):
    """Try to detect a bank name from the PDF filename."""
    lower = filename.lower()
    for hint, display in FILENAME_BANK_HINTS.items():
        if hint in lower:
            return display
    return None


def _resolve_bank_name(from_header):
    """
    Try to map a raw From header to a friendly bank name.
    e.g. "HDFC Bank <alerts@hdfcbank.net>" → "HDFC Bank"
    """
    lower = from_header.lower()
    for domain, display in BANK_DISPLAY.items():
        if domain in lower:
            return display
    # Fall back to the display name part before <email>
    import re
    m = re.match(r'^([^<]+)', from_header)
    return m.group(1).strip() if m else from_header