import secrets
import re
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

from .agents import (
    parse_intent,
    discover_providers,
    rank_providers,
    simulate_booking,
    schedule_followup
)
from .mock_data import SERVICE_PROVIDERS, AREA_COORDS
from .accounts import COOKIE, account_for, database, password_hash, session_digest, start_session

PROJECT_ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(title="Service Orchestrator API - Karachi")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", include_in_schema=False)
def homepage():
    return FileResponse(PROJECT_ROOT / "index.html", media_type="text/html")


@app.get("/manifest.json", include_in_schema=False)
def web_manifest():
    return FileResponse(
        PROJECT_ROOT / "frontend" / "manifest.json",
        media_type="application/manifest+json",
    )


@app.get("/assets/account.css", include_in_schema=False)
def account_styles():
    return FileResponse(PROJECT_ROOT / "frontend" / "account.css", media_type="text/css")


@app.get("/assets/account.js", include_in_schema=False)
def account_script():
    return FileResponse(PROJECT_ROOT / "frontend" / "account.js", media_type="text/javascript")


class OrchestrationRequest(BaseModel):
    user_input: str = Field(min_length=1, max_length=500)

class BookingRequest(BaseModel):
    provider_id: int
    time_slot: str
    reminder_minutes: int = 60

class StatusUpdateRequest(BaseModel):
    booking_id: str
    status: str

@app.post("/orchestrate")
def orchestrate(request: OrchestrationRequest):
    """Full pipeline: Parse -> Discover -> Rank"""
    all_logs = []
    
    # 1. Parse Intent
    intent_data = parse_intent(request.user_input)
    all_logs.extend(intent_data["logs"])
    
    service_type = intent_data.get("service_type")
    location = intent_data.get("location")
    
    if not service_type:
        return {
            "success": False,
            "message": "Could not detect service type. Please be more specific.",
            "logs": all_logs
        }
    
    # 2. Discover
    discovery_data = discover_providers(service_type, location, SERVICE_PROVIDERS)
    all_logs.extend(discovery_data["logs"])
    providers = discovery_data["providers"]
    
    if not providers:
        return {
            "success": False,
            "message": f"No {service_type} found in our records.",
            "logs": all_logs
        }
    
    # 3. Rank
    ranking_data = rank_providers(providers, location)
    all_logs.extend(ranking_data["logs"])
    
    return {
        "success": True,
        "intent": intent_data,
        "providers": ranking_data["ranked"],
        "location_coordinates": AREA_COORDS[location],
        "logs": all_logs
    }

class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=90)


@app.post("/account/{action}")
def account_action(action: str, credentials: Credentials, request: Request, response: Response):
    if action not in {"signup", "login"}:
        raise HTTPException(404)
    email = credentials.email.strip().lower()
    name = credentials.name.strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(422, "Enter a valid email address.")
    with database() as execute:
        if action == "signup":
            if not name:
                raise HTTPException(422, "Enter your name.")
            salt = secrets.token_hex(16)
            password = salt + ":" + password_hash(credentials.password, salt)
            row = execute(
                "INSERT INTO accounts VALUES (?, ?, ?) ON CONFLICT (email) DO NOTHING RETURNING email",
                (email, name, password),
            ).fetchone()
            if not row:
                raise HTTPException(409, "An account already exists for this email.")
        else:
            row = execute("SELECT name, password FROM accounts WHERE email = ?", (email,)).fetchone()
            salt, expected = row[1].split(":") if row else ("00" * 16, "")
            if not secrets.compare_digest(password_hash(credentials.password, salt), expected) or not row:
                raise HTTPException(401, "Email or password is incorrect.")
            name = row[0]
        start_session(execute, request, response, email)
    return {"email": email, "name": name}


@app.get("/account")
def profile(request: Request):
    with database() as execute:
        return account_for(execute, request)


@app.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        with database() as execute:
            execute("DELETE FROM sessions WHERE token = ?", (session_digest(token),))
    response.delete_cookie(COOKIE)
    return {"success": True}


@app.get("/requests")
def list_requests(request: Request):
    with database() as execute:
        email = account_for(execute, request)["email"]
        rows = execute(
            "SELECT payload, status FROM requests WHERE email = ? ORDER BY created DESC",
            (email,),
        ).fetchall()
    return [{**json.loads(payload), "status": status} for payload, status in rows]


@app.post("/book-service")
def book_service(booking_request: BookingRequest, request: Request):
    provider = next((provider for provider in SERVICE_PROVIDERS if provider["id"] == booking_request.provider_id), None)
    if not provider or booking_request.time_slot not in provider["available_slots"]:
        raise HTTPException(422, "Choose an available provider and time.")
    if booking_request.reminder_minutes not in {30, 60, 120}:
        raise HTTPException(422, "Choose a valid reminder time.")
    with database() as execute:
        email = account_for(execute, request)["email"]
        result = simulate_booking(provider, booking_request.time_slot, provider["service_type"])
        booking = result["booking"]
        followup = schedule_followup(booking, booking_request.reminder_minutes)
        execute("INSERT INTO requests VALUES (?, ?, ?, ?, ?)", (
            booking["booking_id"], email, json.dumps(booking), booking["status"], booking["timestamp"],
        ))
    return {"success": True, "booking": booking, "reminder": followup["reminder_time"],
            "logs": result["logs"] + followup["logs"]}


@app.post("/update-status")
def update_status(update: StatusUpdateRequest, request: Request):
    previous = {"provider_notified": "confirmed", "en_route": "provider_notified", "completed": "en_route"}
    if update.status not in previous:
        raise HTTPException(422, "Invalid status.")
    with database() as execute:
        email = account_for(execute, request)["email"]
        row = execute(
            "UPDATE requests SET status = ? WHERE id = ? AND email = ? AND status = ? RETURNING id",
            (update.status, update.booking_id, email, previous[update.status]),
        ).fetchone()
    if not row:
        raise HTTPException(409, "This request cannot advance from its current status.")
    return {"success": True, "new_status": update.status}


@app.get("/providers")
def get_all_providers():
    return SERVICE_PROVIDERS

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
