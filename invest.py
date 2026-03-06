import pandas as pd
import json
import urllib.request

def load_mu_databases():
    _b = "https://raw.githubusercontent.com/DarshMohapatra/FINSIGHT/main/"
    def _gj(f):
        try:
            with urllib.request.urlopen(_b+f, timeout=10) as resp: return json.load(resp)
        except Exception as e:
            print(f"MU DB load failed: {e}")
            return {}
    
    instr = _gj("indian_instruments.json")
    xirr  = _gj("xirr_simulation.json")
    mc    = _gj("monte_carlo_projections.json")
    return instr, xirr, mc

MU_INSTR_RAW, MU_XIRR, MU_MC = load_mu_databases()
MU_INSTRUMENTS = MU_INSTR_RAW.get("instruments", []) if isinstance(MU_INSTR_RAW, dict) else []
MU_DISCLAIMER  = MU_INSTR_RAW.get("sebi_disclaimer", "") if isinstance(MU_INSTR_RAW, dict) else ""

def mu_compute_roundups(transactions, threshold=10):
    df = pd.DataFrame(transactions)
    if "WITHDRAWAL AMT" not in df.columns or "DATE" not in df.columns:
        return {"success": False, "error": "Invalid transaction data"}
    
    df["WITHDRAWAL AMT"] = pd.to_numeric(df["WITHDRAWAL AMT"], errors="coerce").fillna(0)
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
    
    df_w = df[df["WITHDRAWAL AMT"] > 0].copy()
    if df_w.empty:
        return {"success": False, "error": "No withdrawal transactions found"}

    remainder = df_w["WITHDRAWAL AMT"] % threshold
    df_w["ROUNDUP"] = threshold - remainder
    df_w.loc[remainder == 0, "ROUNDUP"] = threshold
    
    monthly = (df_w.groupby(df_w["DATE"].dt.to_period("M"))
               .agg(roundup_total=("ROUNDUP", "sum"), txn_count=("ROUNDUP", "count"))
               .reset_index())
               
    monthly["DATE"] = monthly["DATE"].astype(str)
    
    total_corpus = float(df_w["ROUNDUP"].sum())
    monthly_avg  = total_corpus / max(len(monthly), 1)
    total_txns   = len(df_w)
    avg_per_txn  = total_corpus / max(total_txns, 1)

    # Note: XIRR data is mostly pre-computed for ₹10 threshold.
    # We scale amounts for the user's selected threshold.
    scale = threshold / 10.0
    scaled_xirr = {}
    if MU_XIRR:
        for k, v in MU_XIRR.items():
            scaled_xirr[k] = {
                "total_invested": v.get("total_invested", 0) * scale,
                "current_value": v.get("current_value", 0) * scale,
                "absolute_gain": v.get("absolute_gain", 0) * scale,
                "vs_fd_delta": v.get("vs_fd_delta", 0) * scale,
                "xirr_pct": v.get("xirr_pct", 0)
            }

    mc_data = MU_MC.get(str(threshold), {})

    return {
        "success": True,
        "corpus_stats": {
            "total_corpus": total_corpus,
            "monthly_avg": monthly_avg,
            "total_txns": total_txns,
            "avg_per_txn": avg_per_txn
        },
        "monthly_data": monthly.to_dict(orient="records"),
        "instruments": MU_INSTRUMENTS,
        "xirr": scaled_xirr,
        "mc": mc_data,
        "disclaimer": MU_DISCLAIMER
    }
