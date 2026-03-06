import re
import pandas as pd
from datetime import datetime

def _extract_df_from_pdf(pdf_path, password=None):
    try:
        import pdfplumber
    except ImportError:
        raise ValueError("pdfplumber not installed properly on server.")

    DATE_FORMATS = [
        (re.compile(r"^\d{2}-\d{2}-\d{4}"),        "%d-%m-%Y"),
        (re.compile(r"^\d{2}/\d{2}/\d{4}"),        "%d/%m/%Y"),
        (re.compile(r"^\d{4}-\d{2}-\d{2}"),        "%Y-%m-%d"),
        (re.compile(r"^\d{4}/\d{2}/\d{2}"),        "%Y/%m/%d"),
        (re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4}"),  "%d-%b-%Y"),
        (re.compile(r"^\d{2}\s[A-Za-z]{3}\s\d{4}"),"%d %b %Y"),
        (re.compile(r"^\d{2}/\d{2}/\d{2}"),        "%d/%m/%y"),
        (re.compile(r"^\d{2}-\d{2}-\d{2}"),        "%d-%m-%y"),
    ]
    AMT_PAT = re.compile(r"[\d,]+\.\d{2}")

    def parse_date(s):
        for pat, fmt in DATE_FORMATS:
            m = pat.match(s)
            if m:
                token = m.group(0)
                try:
                    datetime.strptime(token, fmt)
                    return token, fmt
                except ValueError: continue
        return None

    def to_float(s):
        try: return float(str(s).replace(",", "").strip())
        except Exception: return None

    # Step 1: Checking if PDF is encrypted by trying to open with NO password
    is_encrypted = False
    try:
        test_pdf = pdfplumber.open(pdf_path)
        test_pdf.close()
    except Exception:
        is_encrypted = True

    # Step 2: If encrypted, require a valid password
    if is_encrypted:
        if not password:
            raise ValueError("🔒 This PDF is password-protected. Please enter the correct password.")
        try:
            test_pdf = pdfplumber.open(pdf_path, password=password)
            test_pdf.close()
        except Exception:
            raise ValueError("❌ Incorrect PDF password. Try PAN number, DOB, or account number.")

    open_kwargs = {"password": password} if password else {}

    three_col_mode = False
    with pdfplumber.open(pdf_path, **open_kwargs) as pdf:
        for page in pdf.pages[:3]:
            for tbl in (page.extract_tables() or []):
                if tbl:
                    header = [str(c or "").strip().upper() for c in tbl[0]]
                    has_debit  = any("DEBIT" in h or h == "DR" or "WITHDRAWAL" in h for h in header)
                    has_credit = any("CREDIT" in h or h == "CR" or "DEPOSIT" in h for h in header)
                    if has_debit and has_credit:
                        three_col_mode = True
                        break
            if three_col_mode: break

    raw_rows = []
    with pdfplumber.open(pdf_path, **open_kwargs) as pdf:
        for page in pdf.pages:
            try: text = page.extract_text(x_tolerance=2, y_tolerance=2)
            except Exception: continue
            if not text: continue
            for raw in text.splitlines():
                line = raw.strip()
                if not line: continue
                result = parse_date(line)
                if not result: continue
                date_token, date_fmt = result
                rest    = line[len(date_token):].strip()
                amounts = AMT_PAT.findall(rest)
                if len(amounts) < 2: continue
                first_pos = rest.index(amounts[0])
                narration = rest[:first_pos].strip()
                raw_rows.append((date_token, date_fmt, narration, amounts))

    if not raw_rows:
        raise ValueError("No transactions found in this PDF. It may be image-only. Try CSV/Excel.")

    CREDIT_KWS = ["REFUND", "SALARY", "INTEREST", "CASHBACK", "REVERSAL", "REWARD", "DIVIDEND", "/CR", " CR ", "NEFT CR", "IMPS CR", "RTGS CR"]
    rows, prev_bal = [], None

    for date_token, date_fmt, narration, amounts in raw_rows:
        deposit, withdrawal, balance = 0.0, 0.0, to_float(amounts[-1]) or 0.0
        if three_col_mode and len(amounts) >= 3:
            debit_cand, credit_cand = to_float(amounts[-3]), to_float(amounts[-2])
            bal_cand, tol = balance, 2.0
            if prev_bal is not None:
                if debit_cand and abs(round(prev_bal - debit_cand, 2) - round(bal_cand, 2)) <= tol: withdrawal = debit_cand
                elif credit_cand and abs(round(prev_bal + credit_cand, 2) - round(bal_cand, 2)) <= tol: deposit = credit_cand
                else: withdrawal, deposit = debit_cand or 0.0, credit_cand or 0.0
            else: withdrawal, deposit = debit_cand or 0.0, credit_cand or 0.0
        else:
            amt_val, tol = to_float(amounts[-2]), 2.0
            if prev_bal is not None and amt_val is not None:
                exp_wd, exp_dep, bal_r = round(prev_bal - amt_val, 2), round(prev_bal + amt_val, 2), round(balance, 2)
                if abs(bal_r - exp_wd) <= tol: withdrawal = amt_val
                elif abs(bal_r - exp_dep) <= tol: deposit = amt_val
                else:
                    if any(k in narration.upper() for k in CREDIT_KWS): deposit = amt_val
                    else: withdrawal = amt_val
            else:
                if any(k in narration.upper() for k in CREDIT_KWS): deposit = to_float(amounts[-2]) or 0.0
                else: withdrawal = to_float(amounts[-2]) or 0.0

        prev_bal = balance
        rows.append({"DATE": date_token, "TRANSACTION DETAILS": narration, "DEPOSIT AMT": deposit, "WITHDRAWAL AMT": withdrawal, "BALANCE AMT": balance})

    df = pd.DataFrame(rows)
    for _, fmt in DATE_FORMATS:
        converted = pd.to_datetime(df["DATE"], format=fmt, errors="coerce")
        if converted.notna().sum() > len(df) * 0.8:
            df["DATE"] = converted
            break
    else: df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")

    df = df.dropna(subset=["DATE"]).sort_values("DATE").reset_index(drop=True)
    return df

def extract_df(file_path, filename, password=""):
    """
    Master function to handle all file types: PDF, CSV, Excel.
    """
    if filename.lower().endswith(".pdf"):
        return _extract_df_from_pdf(file_path, password)
    elif filename.lower().endswith(".csv"):
        return pd.read_csv(file_path)
    else:
        # Requires openpyxl
        return pd.read_excel(file_path)
