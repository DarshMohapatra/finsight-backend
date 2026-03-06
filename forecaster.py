import pandas as pd
import numpy as np

def generate_forecast(transactions_dict):
    if not transactions_dict:
        return {"success": False, "error": "No transactions provided"}
    
    df = pd.DataFrame(transactions_dict)
    
    if "WITHDRAWAL AMT" not in df.columns or "DATE" not in df.columns:
        return {"success": False, "error": "Missing required transaction columns"}
        
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
    df = df.dropna(subset=["DATE"])
    
    if "ALERT_LEVEL" in df.columns:
        df_fc = df[df["ALERT_LEVEL"] == 0].copy()
    elif "IS_ANOMALY" in df.columns:
        df_fc = df[df["IS_ANOMALY"] == 0].copy()
    else:
        df_fc = df.copy()
        
    df_fc["WITHDRAWAL AMT"] = pd.to_numeric(df_fc["WITHDRAWAL AMT"], errors="coerce").fillna(0)
    
    ms = df_fc.groupby(df_fc["DATE"].dt.to_period("M"))["WITHDRAWAL AMT"].sum().reset_index()
    ms.columns = ["ds", "y"]
    ms["ds"] = ms["ds"].dt.to_timestamp()
    ms = ms.sort_values("ds").reset_index(drop=True)
    
    n = len(ms)
    if n == 0 or ms["y"].sum() == 0:
        return {"success": False, "error": "Not enough data"}
        
    values = ms["y"].values.astype(float)
    last_date = ms["ds"].max()
    
    x = np.arange(n, dtype=float)
    if n >= 2:
        try:
            slope, intercept = np.polyfit(x, values, 1)
        except Exception:
            slope, intercept = 0.0, float(values.mean())
    else:
        slope, intercept = 0.0, float(values[0])
        
    overall_avg = float(values.mean())
    ms["cal_month"] = ms["ds"].dt.month
    cal_avg = ms.groupby("cal_month")["y"].mean()
    seasonal = {}
    for m_num in range(1, 13):
        if m_num in cal_avg.index and overall_avg > 0:
            seasonal[m_num] = float(cal_avg[m_num]) / overall_avg
        else:
            seasonal[m_num] = 1.0
            
    future_dates = pd.date_range(last_date + pd.DateOffset(months=1), periods=6, freq="MS")
    predicted = []
    for i, fdate in enumerate(future_dates):
        trend_val = intercept + slope * (n + i)
        s_ratio = seasonal.get(fdate.month, 1.0)
        pred = max(float(trend_val * s_ratio), 0)
        predicted.append(pred)
        
    if n >= 3:
        trend_fitted = intercept + slope * x
        residuals = values - trend_fitted
        std_y = float(residuals.std())
    elif n == 2:
        std_y = float(abs(values[1] - values[0]) * 0.3)
    else:
        std_y = overall_avg * 0.15
        
    if std_y < 1:
        std_y = overall_avg * 0.1
        
    lower = [max(p - std_y * (0.5 + 0.1 * i), p * 0.1) for i, p in enumerate(predicted)]
    upper = [p + std_y * (0.5 + 0.1 * i) for i, p in enumerate(predicted)]
    
    # --- THIS PART FIXES THE BROKEN GRAPH LINE ---
    chart_data = []
    for i in range(len(ms)):
        chart_data.append({
            "month": ms["ds"].iloc[i].strftime("%b"),
            "actual": float(ms["y"].iloc[i]),
            "predicted": None,
            "range": None
        })
        
    if len(ms) > 0:
        last_val = float(ms["y"].iloc[-1])
        # Force the last historical point to ALSO act as the first predicted point
        chart_data[-1]["predicted"] = last_val
        chart_data[-1]["range"] = [last_val, last_val]

    for i, p in enumerate(predicted):
        month_label = future_dates[i].strftime("%b")
        chart_data.append({
            "month": f"{month_label} (F)",
            "actual": None,
            "predicted": float(p),
            "range": [float(lower[i]), float(upper[i])]
        })
        
    # --- TABLE FIX: ONLY PASS PREDICTIONS ---
    table_data = []
    for i, p in enumerate(predicted):
        table_data.append({
            "month": future_dates[i].strftime("%b %Y"),
            "predicted": float(p),
            "lowest": float(lower[i]),
            "highest": float(upper[i])
        })
        
    if len(ms) > 0 and predicted:
        last_actual = float(ms["y"].iloc[-1])
        next_pred = float(predicted[0])
        if last_actual > 0:
            pct_change = ((next_pred - last_actual) / last_actual) * 100
            trend = "increase" if pct_change > 0 else "decrease"
        else:
            pct_change = 0
            trend = "increase"
    else:
        pct_change = 0
        trend = "increase"
        
    if "CATEGORY" in df_fc.columns:
        cat_spend = df_fc.groupby("CATEGORY")["WITHDRAWAL AMT"].sum().sort_values(ascending=False)
        top_cats = cat_spend.head(4).index.tolist()
        top_categories = []
        for cat in top_cats:
            cat_df = df_fc[df_fc["CATEGORY"] == cat]
            cat_ms = cat_df.groupby(cat_df["DATE"].dt.to_period("M"))["WITHDRAWAL AMT"].sum()
            cat_last = float(cat_ms.iloc[-1]) if len(cat_ms) > 0 else 0
            cat_mean = float(cat_ms.mean()) if len(cat_ms) > 0 else 0
            cat_proj = max(cat_mean * 1.05, cat_last * 0.95)
            cat_pct = ((cat_proj - cat_last) / cat_last * 100) if cat_last > 0 else 0
            top_categories.append({
                "name": cat,
                "predicted": float(cat_proj),
                "trend": "increase" if cat_pct > 0 else "decrease",
                "percentage": round(abs(cat_pct), 1)
            })
    else:
        top_categories = []

    return {
        "success": True,
        "headline_trend": trend,
        "headline_percentage": round(abs(pct_change), 1),
        "chart_data": chart_data,
        "table_data": table_data,
        "top_categories": top_categories
    }
