# CloudSpend Sentinel
Professional prototype for real-time serverless cloud spend anomaly detection and root-cause attribution.

## Run on Windows
1. Open PowerShell in this folder.
2. `py -m venv .venv`
3. `.venv\Scripts\Activate.ps1`
4. `pip install -r requirements.txt`
5. `py -m app.generate_data`
6. `uvicorn app.main:app --reload`
7. Open http://127.0.0.1:8000

## Demo
Dashboard → Anomalies → click a critical/high anomaly → review cost deviation, statistical signal, deployment/configuration evidence, probable cause, confidence and accountable owner → Notifications → Experiment.

## Scope
The application uses synthetic data and local SQLite is intentionally avoided in this rapid prototype so it can run immediately from CSV on a modest laptop. For a final production submission, add persistent event storage, real authentication, real notification integration and a measured replay experiment.
