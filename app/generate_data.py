
from pathlib import Path
import numpy as np, pandas as pd
from datetime import datetime, timedelta
BASE=Path(__file__).resolve().parent.parent
OUT=BASE/"data"/"cloud_spend.csv"

def generate(n=12000, seed=42):
    rng=np.random.default_rng(seed)
    orgs=[("ORG-01","Northstar"),("ORG-02","Vertex"),("ORG-03","BluePeak"),("ORG-04","Orbit")]
    teams=["Payments","Platform","Data","Media","Identity"]
    rows=[]
    start=datetime(2026,1,1)
    resources=[f"fn-{i:03d}" for i in range(1,81)]
    for i in range(n):
        ts=start+timedelta(hours=i//80)
        rid=resources[i%80]; oi=i%4; org_id,org=orgs[oi]
        team=teams[i%len(teams)]
        base=.25+rng.random()*.55
        inv=int(rng.lognormal(7,0.5)); req=int(inv*(1.5+rng.random()*2))
        duration=float(rng.normal(180,35)); memory=int(rng.choice([256,512,1024]))
        err=max(0,float(rng.normal(.01,.006))); retries=int(rng.poisson(3))
        scenario="NORMAL"; dep=None; dep_ts=pd.NaT; cfg=None; cfg_ts=pd.NaT
        # periodic injected anomalies
        if i%977==0 and i>0:
            scenario="DEPLOYMENT_DRIVEN"; base*=3.4; duration*=2.4
            dep=f"v{2+i%7}.{i%10}"; dep_ts=ts-timedelta(minutes=20)
        elif i%1231==0 and i>0:
            scenario="CONFIGURATION_DRIVEN"; memory*=2; base*=2.6
            cfg="MEMORY_INCREASE"; cfg_ts=ts-timedelta(minutes=15)
        elif i%733==0 and i>0:
            scenario="TRAFFIC_DRIVEN"; inv*=4; req*=4; base*=4.0
        elif i%619==0 and i>0:
            scenario="WORKLOAD_DRIVEN"; duration*=1.8; base*=2.0
        elif i%557==0 and i>0:
            scenario="RESOURCE_DRIVEN"; base*=2.8
        cost=max(.01,base*(1+0.002*duration/100)*(1+err*2)+rng.normal(0,.025))
        owner=f"{team} Owner {i%4+1}"
        rows.append([ts,org_id,org, f"T-{i%20:02d}",team,rid,f"{rid}-{team.lower()}","Serverless Function",
                     "ap-south-1","prod",f"U-{i%400:03d}",owner,owner.lower().replace(" ",".")+"@example.com",
                     cost,inv,req,duration,memory,int(5+rng.random()*30),err,retries,round(rng.uniform(10,80),1),
                     dep,dep_ts,cfg,cfg_ts,scenario])
    cols=["timestamp","organisation_id","organisation_name","team_id","team_name","resource_id","resource_name","resource_type",
          "region","environment","owner_id","owner_name","owner_email","hourly_cost","invocation_count","request_count",
          "execution_duration_ms","memory_mb","concurrency","error_rate","retry_count","cpu_utilization","deployment_version",
          "deployment_timestamp","configuration_change_type","configuration_change_timestamp","ground_truth_root_cause"]
    df=pd.DataFrame(rows,columns=cols)
    df["request_count_change_pct"]=df.groupby("resource_id")["request_count"].pct_change().fillna(0)*100
    df["memory_mb_change_pct"]=df.groupby("resource_id")["memory_mb"].pct_change().fillna(0)*100
    OUT.parent.mkdir(exist_ok=True); df.to_csv(OUT,index=False); return OUT

if __name__=="__main__":
    print(generate())
