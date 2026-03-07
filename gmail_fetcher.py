import httpx
import base64
import os
import tempfile

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"


def fetch_and_process(access_token, message_id, attachment_id, filename, password="", analyzer=None):
    """
    1. Download the PDF attachment bytes from Gmail
    2. Write to a temp file
    3. Run through analyzer.process_uploaded_file()
    4. Delete temp file
    Returns same dict shape as /api/upload → { success, transactions, summary, currency }
    """
    if analyzer is None:
        return {"success": False, "error": "Analyzer module not provided"}

    headers = {"Authorization": f"Bearer {access_token}"}

    # Download attachment
    r = httpx.get(
        f"{GMAIL_API}/users/me/messages/{message_id}/attachments/{attachment_id}",
        headers=headers,
        timeout=30,
    )
    if r.status_code != 200:
        return {"success": False, "error": f"Could not download attachment: HTTP {r.status_code}"}

    raw_b64 = r.json().get("data", "")
    if not raw_b64:
        return {"success": False, "error": "Attachment data was empty"}

    # Gmail uses URL-safe base64 — add padding just in case
    pdf_bytes = base64.urlsafe_b64decode(raw_b64 + "==")

    # Write to temp file
    suffix   = os.path.splitext(filename)[-1] or ".pdf"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        # Run existing analyzer pipeline
        result = analyzer.process_uploaded_file(tmp_path, filename, password)
        return result

    except ValueError as e:
        # Wrong password etc.
        return {"success": False, "error": str(e)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": f"Failed to process attachment: {str(e)}"}
    finally:
        # Always clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)