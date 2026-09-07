
from fastapi.testclient import TestClient
from app.main import app
client=TestClient(app)
def test_health_like_summary():
    r=client.get("/api/summary"); assert r.status_code==200; assert r.json()["resources"]>0
def test_anomalies():
    r=client.get("/api/anomalies"); assert r.status_code==200; assert len(r.json())>0
def test_spend():
    r=client.get("/api/spend"); assert r.status_code==200; assert len(r.json())>0
def test_experiment():
    r=client.get("/api/experiment"); assert r.status_code==200; assert r.json()["proposed"]["notification_latency"]<=15
def test_notifications():
    r=client.get("/api/notifications"); assert r.status_code==200
