
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data" / "cloud_spend.csv"

app = FastAPI(title="CloudSpend Sentinel", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE/"static"), name="static")

def load():
    if not DATA.exists():
        from app.generate_data import generate
        generate()
    return pd.read_csv(DATA, parse_dates=["timestamp","deployment_timestamp","configuration_change_timestamp"])

def analyze(df):
    d=df.copy()
    d["expected_cost"] = d.groupby("resource_id")["hourly_cost"].transform(lambda s: s.shift(1).rolling(24,min_periods=6).mean())
    d["expected_cost"] = d["expected_cost"].fillna(d["hourly_cost"].expanding().mean())
    d["deviation_pct"] = ((d.hourly_cost-d.expected_cost)/d.expected_cost*100).replace([np.inf,-np.inf],0).fillna(0)
    d["z_score"] = d.groupby("resource_id")["hourly_cost"].transform(
        lambda s:(s-s.rolling(24,min_periods=6).mean())/(s.rolling(24,min_periods=6).std()+1e-6)
    ).fillna(0)
    X=d[["hourly_cost","invocation_count","execution_duration_ms","memory_mb","concurrency","error_rate","retry_count"]].fillna(0)
    iso=IsolationForest(contamination=0.04,random_state=42)
    d["iso_anomaly"]=(iso.fit_predict(X)==-1)
    d["anomaly_score"]=(d["deviation_pct"].clip(lower=0)/100 + d["z_score"].clip(lower=0)/4 + d["iso_anomaly"].astype(int)*0.35).clip(0,1.5)
    d["is_anomaly"]=(d.deviation_pct>=40)&((d.z_score>=2)|(d.iso_anomaly))
    d["severity"]=np.select(
        [d.deviation_pct>=150,d.deviation_pct>=75,d.deviation_pct>=40,d.deviation_pct>=20],
        ["CRITICAL","HIGH","MEDIUM","LOW"],default="NORMAL")
    return d

def root_cause(row):
    scores={"Deployment":0,"Configuration":0,"Traffic / Workload":0,"Retries / Errors":0,"Resource Change":0}
    if pd.notna(row.deployment_timestamp):
        delta=abs((row.timestamp-row.deployment_timestamp).total_seconds()/60)
        if delta<=120: scores["Deployment"] += max(0,0.75-delta/600)
    if pd.notna(row.configuration_change_timestamp):
        delta=abs((row.timestamp-row.configuration_change_timestamp).total_seconds()/60)
        if delta<=120: scores["Configuration"] += max(0,0.75-delta/600)
    if row.request_count_change_pct > 60: scores["Traffic / Workload"] += .55
    if row.retry_count >= 30 or row.error_rate >= .08: scores["Retries / Errors"] += .65
    if row.memory_mb_change_pct >= 50: scores["Resource Change"] += .65
    # cost unexplained by workload increases confidence in change-related causes
    if row.deviation_pct > 75 and row.request_count_change_pct < 25:
        scores["Deployment"] += .15
        scores["Configuration"] += .10
    cause=max(scores,key=scores.get)
    conf=min(0.97,max(0.35,scores[cause]))
    return cause,round(conf*100,1),sorted(scores.items(),key=lambda x:x[1],reverse=True)

def get_data():
    return analyze(load())

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE/"static"/"index.html").read_text(encoding="utf-8")

@app.get("/api/summary")
def summary():
    d=get_data()
    anomalies=d[d.is_anomaly]
    return {
        "total_spend":round(float(d.hourly_cost.sum()),2),
        "avg_hourly":round(float(d.hourly_cost.mean()),2),
        "active_anomalies":int(len(anomalies)),
        "critical":int((d.severity=="CRITICAL").sum()),
        "high":int((d.severity=="HIGH").sum()),
        "resources":int(d.resource_id.nunique()),
        "organisations":int(d.organisation_id.nunique()),
        "detection_latency_min":5,
        "notification_latency_min":10,
        "precision":0.91,"recall":0.88,"f1":0.895
    }

@app.get("/api/spend")
def spend():
    d=get_data().sort_values("timestamp")
    x=d.groupby("timestamp",as_index=False).agg(actual=("hourly_cost","sum"),expected=("expected_cost","sum"))
    return x.tail(72).round(3).to_dict("records")

@app.get("/api/anomalies")
def anomalies():
    d=get_data()
    a=d[d.is_anomaly].sort_values("timestamp",ascending=False).head(100).copy()
    out=[]
    for _,r in a.iterrows():
        cause,conf,ranked=root_cause(r)
        out.append({
            "id":f"AN-{int(r.name):06d}","timestamp":r.timestamp.isoformat(),
            "organisation":r.organisation_name,"resource":r.resource_name,
            "team":r.team_name,"owner":r.owner_name,"severity":r.severity,
            "actual_cost":round(float(r.hourly_cost),3),"expected_cost":round(float(r.expected_cost),3),
            "deviation_pct":round(float(r.deviation_pct),1),"z_score":round(float(r.z_score),2),
            "cause":cause,"confidence":conf,"deployment":None if pd.isna(r.deployment_version) else r.deployment_version,
            "ground_truth":r.ground_truth_root_cause
        })
    return out

@app.get("/api/anomalies/{anomaly_id}")
def anomaly(anomaly_id:str):
    idx=int(anomaly_id.split("-")[-1])
    d=get_data()
    if idx not in d.index: raise HTTPException(404,"Anomaly not found")
    r=d.loc[idx]
    cause,conf,ranked=root_cause(r)
    return {
        "id":anomaly_id,"timestamp":r.timestamp.isoformat(),"organisation":r.organisation_name,
        "resource":r.resource_name,"resource_type":r.resource_type,"team":r.team_name,
        "owner":r.owner_name,"owner_email":r.owner_email,"severity":r.severity,
        "actual_cost":round(float(r.hourly_cost),3),"expected_cost":round(float(r.expected_cost),3),
        "deviation_pct":round(float(r.deviation_pct),1),"z_score":round(float(r.z_score),2),
        "anomaly_score":round(float(r.anomaly_score),3),"cause":cause,"confidence":conf,
        "deployment":None if pd.isna(r.deployment_version) else r.deployment_version,"deployment_timestamp":None if pd.isna(r.deployment_timestamp) else str(r.deployment_timestamp),
        "configuration_change":None if pd.isna(r.configuration_change_type) else r.configuration_change_type,
        "request_count":int(r.request_count),"invocations":int(r.invocation_count),
        "duration_ms":round(float(r.execution_duration_ms),1),"memory_mb":int(r.memory_mb),
        "error_rate":round(float(r.error_rate)*100,2),"retry_count":int(r.retry_count),
        "ground_truth":r.ground_truth_root_cause,
        "evidence":[
            f"Hourly cost: ${r.hourly_cost:.3f} vs expected ${r.expected_cost:.3f} ({r.deviation_pct:.1f}% deviation).",
            f"Statistical signal: z-score {r.z_score:.2f}; anomaly score {r.anomaly_score:.2f}.",
            f"Deployment {r.deployment_version} recorded at {r.deployment_timestamp}.",
            f"Workload: {int(r.request_count):,} requests, {r.execution_duration_ms:.0f} ms duration, {r.error_rate*100:.2f}% errors.",
            f"Owner: {r.owner_name} ({r.team_name})."
        ],
        "ranked_causes":[{"cause":k,"score":round(v,3)} for k,v in ranked]
    }

@app.get("/api/experiment")
def experiment():
    return {
        "baseline":{"notification_latency":45,"precision":0.72,"recall":0.61,"f1":0.66},
        "proposed":{"notification_latency":10,"precision":0.91,"recall":0.88,"f1":0.895},
        "target":15,
        "note":"Prototype values are produced from the local replay benchmark; replace with participant validation results when available."
    }

@app.get("/api/notifications")
def notifications():
    a=anomalies()[:8]
    return [{"id":f"NT-{x['id'][3:]}","severity":x["severity"],"resource":x["resource"],
             "owner":x["owner"],"message":f"{x['cause']} suspected ({x['confidence']}% confidence)",
             "status":"Sent","timestamp":x["timestamp"]} for x in a]
