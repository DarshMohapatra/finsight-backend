import pandas as pd
from categorizer import categorize, detect_currency, CURRENCY_CONFIG
from parser import extract_df

def _normalize_columns(df):
    df.columns = df.columns.str.strip()
    direct_map = {
        "CATEGORY": "TRANSACTION DETAILS", "TYPE": "TRANSACTION DETAILS",
        "NARRATION": "TRANSACTION DETAILS", "DESCRIPTION": "TRANSACTION DETAILS",
        "PARTICULARS": "TRANSACTION DETAILS", "DETAILS": "TRANSACTION DETAILS",
        "REMARKS": "TRANSACTION DETAILS", "CHEQUENO": "TRANSACTION DETAILS",
        "CHEQUE NO": "TRANSACTION DETAILS", "MODE": "TRANSACTION DETAILS",
        "TIMESTAMP": "DATE", "TRANSACTION DATE": "DATE", "TXN DATE": "DATE",
        "TRANS DATE": "DATE", "VALUE DATE": "DATE", "POSTING DATE": "DATE",
        "ENTRY DATE": "DATE",
        "DEBIT": "WITHDRAWAL AMT", "DEBIT AMT": "WITHDRAWAL AMT",
        "DR": "WITHDRAWAL AMT", "WITHDRAWALS": "WITHDRAWAL AMT",
        "AMOUNT DEBITED": "WITHDRAWAL AMT", "WD": "WITHDRAWAL AMT",
        "MONEY OUT": "WITHDRAWAL AMT", "OUTFLOW": "WITHDRAWAL AMT",
        "PAID OUT": "WITHDRAWAL AMT", "EXPENSE": "WITHDRAWAL AMT",
        "AMOUNT PAID": "WITHDRAWAL AMT", "PAYMENT AMT": "WITHDRAWAL AMT",
        "SPEND": "WITHDRAWAL AMT", "SPENDING": "WITHDRAWAL AMT",
        "DEBIT AMOUNT": "WITHDRAWAL AMT", "WITHDRAWAL AMOUNT": "WITHDRAWAL AMT",
        "CREDIT": "DEPOSIT AMT", "CREDIT AMT": "DEPOSIT AMT",
        "CR": "DEPOSIT AMT", "DEPOSITS": "DEPOSIT AMT",
        "AMOUNT CREDITED": "DEPOSIT AMT",
        "MONEY IN": "DEPOSIT AMT", "INFLOW": "DEPOSIT AMT",
        "PAID IN": "DEPOSIT AMT", "INCOME": "DEPOSIT AMT",
        "AMOUNT RECEIVED": "DEPOSIT AMT", "CREDIT AMOUNT": "DEPOSIT AMT",
        "DEPOSIT AMOUNT": "DEPOSIT AMT",
        "BALANCE": "BALANCE AMT", "CLOSING BALANCE": "BALANCE AMT",
        "RUNNING BALANCE": "BALANCE AMT", "BAL": "BALANCE AMT",
    }

    new_cols = {}
    already_mapped = set()
    for col in df.columns:
        key = col.upper().strip()
        if key in direct_map:
            tgt = direct_map[key]
            if tgt not in df.columns and tgt not in already_mapped:
                new_cols[col] = tgt
                already_mapped.add(tgt)
    df = df.rename(columns=new_cols)

    cols_upper = {c.upper().strip(): c for c in df.columns}
    date_c   = ["DATE", "TRANSACTION DATE", "TXN DATE", "VALUE DATE", "TIMESTAMP", "POSTING DATE"]
    detail_c = ["TRANSACTION DETAILS", "PARTICULARS", "NARRATION", "DESCRIPTION", "REMARKS", "DETAILS", "TYPE", "CATEGORY", "MODE", "CHEQUE", "TRANS DETAILS"]
    wd_c     = ["WITHDRAWAL AMT", "WITHDRAWALS", "WITHDRAWAL", "DEBIT", "DEBIT AMT", "DR", "AMOUNT DEBITED", "WD AMT", "MONEY OUT", "OUTFLOW", "PAID OUT", "EXPENSE", "SPENDING", "PAYMENT AMT", "DEBIT AMOUNT", "WITHDRAWAL AMOUNT"]
    dep_c    = ["DEPOSIT AMT", "DEPOSITS", "DEPOSIT", "CREDIT", "CREDIT AMT", "CR", "AMOUNT CREDITED", "MONEY IN", "INFLOW", "PAID IN", "INCOME", "AMOUNT RECEIVED", "CREDIT AMOUNT", "DEPOSIT AMOUNT"]
    bal_c    = ["BALANCE AMT", "BALANCE", "CLOSING BALANCE", "RUNNING BALANCE", "BAL"]

    def find(cands):
        for c in cands:
            if c in cols_upper: return cols_upper[c]
        for c in cands:
            for cu, co in cols_upper.items():
                if c in cu or cu in c: return co
        return None

    col_map = {}
    for tgt, cands in [("DATE", date_c), ("TRANSACTION DETAILS", detail_c),
                       ("WITHDRAWAL AMT", wd_c), ("DEPOSIT AMT", dep_c), ("BALANCE AMT", bal_c)]:
        f = find(cands)
        if f and tgt not in df.columns:
            col_map[f] = tgt
    df = df.rename(columns=col_map)

    if "TRANSACTION DETAILS" not in df.columns:
        already_used = {"DATE", "WITHDRAWAL AMT", "DEPOSIT AMT", "BALANCE AMT"}
        candidates = [c for c in df.columns if c not in already_used]
        best_col, best_score = None, 0
        for col in candidates:
            try:
                vals = df[col].dropna().astype(str)
                score = vals[~vals.str.match(r"^[\d.,\s\-]+$")].nunique()
                if score > best_score:
                    best_score, best_col = score, col
            except Exception: pass
        if best_col and best_score > 0:
            df = df.rename(columns={best_col: "TRANSACTION DETAILS"})
        else:
            df["TRANSACTION DETAILS"] = ""

    if "WITHDRAWAL AMT" not in df.columns:
        cols_upper_now = {c.upper().strip(): c for c in df.columns}
        amount_names = ["AMOUNT", "TRANSACTION AMOUNT", "TXN AMT", "TXN AMOUNT", "TRANSACTION VALUE", "NET AMOUNT", "NET AMT"]
        amt_col = None
        mapped_targets = {"DATE", "TRANSACTION DETAILS", "DEPOSIT AMT", "BALANCE AMT"}
        for alias in amount_names:
            if alias in cols_upper_now and cols_upper_now[alias] not in mapped_targets:
                amt_col = cols_upper_now[alias]
                break
        if not amt_col:
            for alias in amount_names:
                for cu, co in cols_upper_now.items():
                    if co in mapped_targets: continue
                    if alias in cu or cu in alias:
                        amt_col = co
                        break
                if amt_col: break

        if amt_col:
            amt_vals = pd.to_numeric(
                df[amt_col].astype(str).str.replace(",", "", regex=False)
                .str.replace("Rs.", "", regex=False).str.replace("₹", "", regex=False)
                .str.replace("Rs", "", regex=False).str.strip(),
                errors="coerce").fillna(0)
            type_names = ["TYPE", "TRANSACTION TYPE", "TXN TYPE", "DR/CR", "DRCR", "CR/DR"]
            type_col = None
            for tn in type_names:
                if tn in cols_upper_now and cols_upper_now[tn] not in mapped_targets:
                    type_col = cols_upper_now[tn]
                    break
            if type_col:
                type_vals = df[type_col].astype(str).str.upper().str.strip()
                is_debit = type_vals.str.contains(r"DR|DEBIT|D\b|WITHDRAWAL|WD|OUT", na=False)
                df["WITHDRAWAL AMT"] = amt_vals.where(is_debit, 0).abs()
                if "DEPOSIT AMT" not in df.columns:
                    df["DEPOSIT AMT"] = amt_vals.where(~is_debit, 0).abs()
            else:
                has_negatives = (amt_vals < 0).any()
                if has_negatives:
                    df["WITHDRAWAL AMT"] = amt_vals.clip(upper=0).abs()
                    if "DEPOSIT AMT" not in df.columns: df["DEPOSIT AMT"] = amt_vals.clip(lower=0)
                else:
                    df["WITHDRAWAL AMT"] = amt_vals.abs()
                    if "DEPOSIT AMT" not in df.columns: df["DEPOSIT AMT"] = 0

        elif "DEPOSIT AMT" in df.columns:
            dep_raw = pd.to_numeric(
                df["DEPOSIT AMT"].astype(str).str.replace(",", "", regex=False)
                .str.replace("Rs.", "", regex=False).str.replace("₹", "", regex=False)
                .str.replace("Rs", "", regex=False).str.strip(), errors="coerce").fillna(0)
            if (dep_raw < 0).any():
                df["WITHDRAWAL AMT"] = dep_raw.clip(upper=0).abs()
                df["DEPOSIT AMT"] = dep_raw.clip(lower=0)
            elif "BALANCE AMT" in df.columns:
                try:
                    bal = pd.to_numeric(
                        df["BALANCE AMT"].astype(str).str.replace(",", "", regex=False)
                        .str.replace("Rs.", "", regex=False).str.replace("₹", "", regex=False)
                        .str.replace("Rs", "", regex=False).str.strip(), errors="coerce")
                    wd = bal.shift(1) + dep_raw - bal
                    df["WITHDRAWAL AMT"] = wd.fillna(0).clip(lower=0)
                except Exception: df["WITHDRAWAL AMT"] = 0
            else: df["WITHDRAWAL AMT"] = 0

    if "DATE" not in df.columns:
        raise ValueError("Cannot find DATE column. Ensure your file has a date column.")
    for col in ["WITHDRAWAL AMT", "DEPOSIT AMT", "BALANCE AMT"]:
        if col not in df.columns: df[col] = 0
    return df


# ── MAIN PIPELINE: UPLOAD LOGIC ────────────────────────────

def process_uploaded_file(file_path, filename, password=""):
    """
    Reads the file via the new parser, normalizes it, categorizes, and runs anomaly detection.
    Returns JSON dictionary.
    """
    # 1. Read using the new Parser
    df = extract_df(file_path, filename, password)
    
    # 2. Normalize columns
    df = _normalize_columns(df)

    # 3. Detect and set currency
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
    currency = detect_currency(df)

    # 4. Clean numbers
    for col in ["WITHDRAWAL AMT", "DEPOSIT AMT", "BALANCE AMT"]:
        df[col] = (df[col].astype(str).str.replace(",", "", regex=False)
                   .str.replace("Rs.", "", regex=False).str.replace("₹", "", regex=False)
                   .str.replace("Rs", "", regex=False).str.replace("$", "", regex=False)
                   .str.replace("£", "", regex=False).str.replace("A$", "", regex=False)
                   .str.replace("C$", "", regex=False).str.replace("USD", "", regex=False)
                   .str.replace("GBP", "", regex=False).str.replace("CAD", "", regex=False)
                   .str.replace("AUD", "", regex=False).str.strip())
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df = df[(df["WITHDRAWAL AMT"] > 0) | (df["DEPOSIT AMT"] > 0)].copy()
    df.dropna(subset=["DATE"], inplace=True)

    if len(df) == 0:
        return {"success": False, "error": "No transactions found after filtering."}

    # 5. Categorize using the Categorizer module
    df["CATEGORY"] = df["TRANSACTION DETAILS"].apply(categorize)

    # 6. Anomaly Detection Engine
    _csym = CURRENCY_CONFIG.get(currency, CURRENCY_CONFIG["IN"])["symbol"]
    _HIGH_VAR_CATS = {"Travel & Transport", "UPI Payment", "Shopping", "Card Payment", "Online Payment", "Bill Payment"}
    _cat_type_map = {}
    _sp = df[df["WITHDRAWAL AMT"]>0].copy()
    _sp["_MP"] = _sp["DATE"].dt.to_period("M")
    _tm = df["DATE"].dt.to_period("M").nunique()
    
    for _cat, _grp in _sp.groupby("CATEGORY"):
        _ms = _grp.groupby("_MP")["WITHDRAWAL AMT"].sum()
        _ar = _ms.shape[0] / _tm if _tm > 0 else 0
        _cv = (_ms.std()/_ms.mean()) if _ms.std()>0 and _ms.mean()>0 else 0
        _rm = _ms.rolling(3, min_periods=1).mean()
        _cat_type_map[_cat] = {
            "type": "A" if _ar>=0.6 and _cv<0.25 else ("B" if _ar>=0.4 else "C"),
            "mm"  : float(_ms.mean()),
            "hmx" : float(_grp["WITHDRAWAL AMT"].max()),
            "rm"  : {str(k):float(v) for k,v in _rm.items()}
        }
        
    df["ALERT_LEVEL"]  = 0
    df["ALERT_REASON"] = ""
    _am = {}
    def _aa(_i, _lv, _rs):
        if _i not in _am or _lv > _am[_i][0]: _am[_i] = (_lv, _rs)
        
    for _cat, _pf in _cat_type_map.items():
        _cr = _sp[_sp["CATEGORY"]==_cat].copy()
        if _cr.empty: continue
        _ct, _mm, _hmx, _rms = _pf["type"], _pf["mm"], _pf["hmx"], _pf["rm"]
        _is_hv = _cat in _HIGH_VAR_CATS
        
        if _ct == "A":
            _t_hard = 2.5 if _is_hv else 1.5
            _t_soft = 2.0 if _is_hv else 1.2
            for _i, _row in _cr.iterrows():
                _rv = _rms.get(str(_row["_MP"]), _mm) or _mm
                if _rv <= 0: continue
                _rt = _row["WITHDRAWAL AMT"] / _rv
                if _rt >= _t_hard: _aa(_i, 3, f"{_cat}: {_csym}{_row['WITHDRAWAL AMT']:,.0f} is {_rt:.1f}x expected {_csym}{_rv:,.0f} — significant spike.")
                elif _rt >= _t_soft: _aa(_i, 2, f"{_cat}: {_csym}{_row['WITHDRAWAL AMT']:,.0f} is {_rt:.1f}x expected {_csym}{_rv:,.0f} — above normal.")
        elif _ct == "B":
            _t_hard = 4.0 if _is_hv else 2.9
            _t_soft = 3.0 if _is_hv else 1.9
            _cmo = _cr.groupby("_MP")["WITHDRAWAL AMT"].sum()
            for _mp, _mt in _cmo.items():
                _rv = _rms.get(str(_mp), _mm) or _mm
                if _rv <= 0: continue
                _rt = _mt / _rv
                _sb = _cr[(_cr["_MP"] == _mp) & (_cr["WITHDRAWAL AMT"] > 0)]
                if _sb.empty: continue
                _ai = _sb["WITHDRAWAL AMT"].idxmax()
                if _rt > _t_hard: _aa(_ai, 3, f"{_cat}: Monthly {_csym}{_mt:,.0f} is {_rt:.1f}x rolling avg {_csym}{_rv:,.0f} — extreme spike.")
                elif _rt > _t_soft: _aa(_ai, 2, f"{_cat}: Monthly {_csym}{_mt:,.0f} is {_rt:.1f}x rolling avg {_csym}{_rv:,.0f} — unusually high.")
        elif _ct == "C":
            _cs = _cr.sort_values("DATE")
            for _i, _row in _cs.iterrows():
                _pr = _cs[(_cs["DATE"] < _row["DATE"]) & (_cs["DATE"] >= _row["DATE"] - pd.Timedelta(days=60))]
                _pc = len(_pr)
                if not _is_hv:
                    if _pc >= 2: _aa(_i, 3, f"{_cat}: {_pc+1} transactions in 60 days — unusually frequent.")
                    elif _pc == 1: _aa(_i, 2, f"{_cat}: 2nd transaction in {(_row['DATE'] - _pr['DATE'].max()).days}d — typically rare.")
                if _hmx > 0 and _row["WITHDRAWAL AMT"] > _hmx * 1.5: _aa(_i, 3, f"{_cat}: {_csym}{_row['WITHDRAWAL AMT']:,.0f} is 1.5x+ historical max {_csym}{_hmx:,.0f}.")
                
    for _i, (_lv, _rs) in _am.items():
        df.at[_i, "ALERT_LEVEL"] = _lv
        df.at[_i, "ALERT_REASON"] = _rs
        
    df["IS_ANOMALY"] = (df["ALERT_LEVEL"] > 0).astype(int)
    
    # 7. Final Prep for UI
    df["DATE"] = df["DATE"].dt.strftime("%Y-%m-%d")
    df = df.fillna("")
    
    # 8. Summary calculation
    total_spent = float(df["WITHDRAWAL AMT"].sum())
    total_income = float(df["DEPOSIT AMT"].sum())
    txn_count = len(df)
    months = len(_sp["_MP"].unique()) if len(_sp) > 0 else 1
    
    return {
        "success": True,
        "currency": currency,
        "transactions": df.to_dict(orient="records"),
        "summary": {
            "total_spent": total_spent,
            "total_income": total_income,
            "txn_count": txn_count,
            "months": months,
            "avg_monthly_spend": round(total_spent / max(months, 1), 2)
        }
    }
