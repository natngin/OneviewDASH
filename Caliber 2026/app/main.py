import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.routers import health, kpi, performance, alarms, energy, ml_alarm, ml_simulator, incidents, sandbox, actions

app = FastAPI(
    title="ONEVIEW — Intelligent Manufacturing Command Center API",
    description="REST API powering the ONEVIEW Predictive Alarm, Equipment Performance, and Energy Monitoring Dashboard.",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(health.router)
app.include_router(kpi.router)
app.include_router(performance.router)
app.include_router(alarms.router)
app.include_router(energy.router)
app.include_router(ml_alarm.router)
app.include_router(ml_simulator.router)
app.include_router(incidents.router)
app.include_router(sandbox.router)
app.include_router(actions.router)

# Locate DASHBOARD folder
DASHBOARD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "DASHBOARD"))
INDEX_HTML = os.path.join(DASHBOARD_DIR, "index.html")

@app.get("/", include_in_schema=False)
async def serve_index():
    return FileResponse(INDEX_HTML)

# Mount remaining static assets from DASHBOARD
if os.path.exists(DASHBOARD_DIR):
    app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
