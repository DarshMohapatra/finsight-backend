import pandas as pd
import json
import urllib.request
import re

def load_card_databases():
    _b = "https://raw.githubusercontent.com/DarshMohapatra/FINSIGHT/main/"
    def _g(f):
        try:
            with urllib.request.urlopen(_b+f, timeout=5) as resp: return json.load(resp)
        except Exception: return []
    return _g("card_master.json"), _g("card_rewards.json")

SC_CARD_MASTER, SC_CARD_REWARDS = load_card_databases()
SC_RWD  = {r["card_id"]: r["rates"] for r in SC_CARD_REWARDS}
SC_NAME = {c["card_id"]: c["bank"]+" "+c["card_name"] for c in SC_CARD_MASTER}
SC_COUNTRY = {c["card_id"]: c.get("country", "IN") for c in SC_CARD_MASTER}
SC_CMAP = {
    "Food & Dining":"Food & Dining", "Grocery":"Grocery",
    "Shopping":"Shopping", "Travel & Transport":"Travel", "Fuel":"Fuel",
    "Medical & Health":"Healthcare", "Entertainment":"Entertainment",
    "Bills & Utilities":"Utility", "Salary":"Other", "Other":"Other"}

def sc_best(amount, category, wallet):
    cat = SC_CMAP.get(category, "Other")
    bi, br, bc = "NONE", 0.0, 0.0
    wi, wr, wc = "NONE", 999.0, float("inf")
    for cid in wallet:
        rate = SC_RWD.get(cid, {}).get(cat, SC_RWD.get(cid, {}).get("Other", 0))
        cash = round(amount * rate / 100, 2)
        if cash > bc: bi, br, bc = cid, rate, cash
        if cash < wc: wi, wr, wc = cid, rate, cash
    return {"name": SC_NAME.get(bi, bi), "rate": br,
            "cash": bc, "base": round(amount/100, 2),
            "worst_name": SC_NAME.get(wi, wi), "worst_rate": wr,
            "worst_cash": wc if wc != float("inf") else 0.0}

def get_cards_for_currency(currency_code="IN"):
    # Streamlit allowed users to select the country, filtering cards by country code ("IN", "US")
    # SC_CARD_MASTER country fields are mostly "IN"
    _filtered = [c for c in SC_CARD_MASTER if c.get("country", "IN") == currency_code]
    return _filtered

def generate_smartcash_report(transactions, wallet_ids, currency_code="IN"):
    if not SC_CARD_MASTER:
        return {"success": False, "error": "Card database failed to load — check card_master.json"}
    
    if not wallet_ids:
        return {"success": False, "error": "No wallet cards provided"}
        
    df = pd.DataFrame(transactions)
    if df.empty or "WITHDRAWAL AMT" not in df.columns or "CATEGORY" not in df.columns:
        return {"success": False, "error": "Invalid transaction data format"}

    df["WITHDRAWAL AMT"] = pd.to_numeric(df["WITHDRAWAL AMT"], errors="coerce").fillna(0)
        
    sp = df[(df["WITHDRAWAL AMT"]>0) & df["CATEGORY"].notna() & (df["CATEGORY"]!="Salary")].copy()
    
    if sp.empty:
        return {"success": False, "error": "No valid spending transactions found"}

    rows = []
    for _, row in sp.iterrows():
        res = sc_best(row["WITHDRAWAL AMT"], row["CATEGORY"], wallet_ids)
        rows.append({
             "DATE": row.get("DATE", ""),
             "DESCRIPTION": row.get("TRANSACTION DETAILS", ""),
             "CATEGORY": row["CATEGORY"],
             "AMOUNT": row["WITHDRAWAL AMT"],
             "BEST_CARD": res["name"],
             "BEST_RATE": res["rate"],
             "BEST_CASHBACK": res["cash"],
             "BASELINE": res["base"],
             "EXTRA": round(res["cash"]-res["base"], 2),
             "WORST_CARD": res["worst_name"],
             "WORST_RATE": res["worst_rate"],
             "WORST_CASHBACK": res["worst_cash"],
             "MISSED": round(res["cash"]-res["worst_cash"], 2)
        })
        
    rdf = pd.DataFrame(rows)
    
    # Generate summary
    summary = (rdf.groupby("CATEGORY")
            .agg(spend=("AMOUNT","sum"), cashback=("BEST_CASHBACK","sum"),
                 txns=("AMOUNT","count"),
                 best_card=("BEST_CARD", lambda x: x.mode()[0]),
                 avg_rate=("BEST_RATE","mean"))
            .assign(extra=lambda x: x["cashback"] - (x["spend"]/100))
            .sort_values("spend", ascending=False).reset_index())
            
    # Auto-detect other good cards from the user's region
    all_region_cards = get_cards_for_currency(currency_code)
    wallet_set = set(wallet_ids)
    other_cards = [c for c in all_region_cards if c["card_id"] not in wallet_set]
    
    suggestions = []
    if other_cards:
        cat_spends = rdf.groupby("CATEGORY")["AMOUNT"].sum().to_dict()
        months_in_data = max(pd.to_datetime(df["DATE"], errors="coerce").dt.to_period("M").nunique(), 1)
        
        for oc in other_cards:
            oc_rates = SC_RWD.get(oc["card_id"], {})
            oc_cb = 0.0
            oc_best_cats = []
            for cat, sp_amt in cat_spends.items():
                mapped = SC_CMAP.get(cat, "Other")
                r = oc_rates.get(mapped, oc_rates.get("Other", 0))
                oc_cb += sp_amt * r / 100
                if r >= 3.0:
                    oc_best_cats.append({"category": mapped, "rate": r})
            oc_annual = oc_cb / months_in_data * 12
            net_annual = oc_annual - oc.get("annual_fee", 0)
            suggestions.append({
                "card": oc, "cb": oc_cb, "annual": oc_annual,
                "net": net_annual, "top_cats": sorted(oc_best_cats, key=lambda x: -x["rate"])[:3]
            })
        suggestions.sort(key=lambda x: -x["net"])

    return {
        "success": True,
        "results": rdf.to_dict(orient="records"),
        "summary": summary.to_dict(orient="records"),
        "suggestions": suggestions[:3],
        "available_cards": all_region_cards
    }
