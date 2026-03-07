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


def scan_for_statements(access_token, max_results=40):
    """
    Search Gmail for emails from known banks that have PDF attachments.
    Returns { success, emails: [...], count }
    """
    h = _headers(access_token)

    # Building Gmail search query
    sender_q = " OR ".join([f"from:{s}" for s in BANK_SENDERS[:15]])
    query    = f"({sender_q}) has:attachment filename:pdf"

    r = httpx.get(
        f"{GMAIL_API}/users/me/messages",
        headers=h,
        params={"q": query, "maxResults": max_results},
        timeout=20,
    )

    if r.status_code != 200:
        return {"success": False, "error": f"Gmail API error {r.status_code}: {r.text}"}

    message_refs = r.json().get("messages", [])
    if not message_refs:
        return {"success": True, "emails": [], "count": 0}

    # Fetch metadata for up to 25 messages
    emails = []
    for ref in message_refs[:25]:
        meta = _get_message_meta(ref["id"], h)
        if meta:
            emails.append(meta)

    # Sort newest first
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