import os
import json
import random
import string
from datetime import datetime, timedelta

BOOKINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "bookings.json")


def parse_intent(user_input: str) -> dict:
    logs = []
    logs.append(f"[INTENT AGENT] Received input: {user_input}")

    text = user_input.lower()

    urdu_words = ["chahiye", "mujhe", "karo", "hai", "kal", "subah", "mein", "ka", "ki", "ko"]
    if any(w in text for w in urdu_words):
        lang = "Roman Urdu"
    elif any(ord(c) > 1535 for c in user_input):
        lang = "Urdu"
    else:
        lang = "English"
    logs.append(f"[INTENT AGENT] Detected language: {lang}")

    service_map = {
        "AC Technician": ["ac", "air condition", "cooling", "ac technician", "thanda"],
        "Plumber": ["plumber", "plumbing", "pipe", "leak", "paani", "water", "nal"],
        "Electrician": ["electrician", "electric", "wiring", "bijli", "light", "switch"],
        "Tutor": ["tutor", "teacher", "padhai", "study", "math", "science", "ustad"],
        "Beautician": ["beautician", "beauty", "makeup", "salon", "mehndi", "facial"],
        "Carpenter": ["carpenter", "wood", "furniture", "darwaza", "door", "almari", "lakri"]
    }

    service_type = None
    for stype, keywords in service_map.items():
        if any(kw in text for kw in keywords):
            service_type = stype
            break
    logs.append(f"[INTENT AGENT] Extracted service_type: {service_type}")

    area_map = {
        "gulshan": "Gulshan-e-Iqbal",
        "gulshan-e-iqbal": "Gulshan-e-Iqbal",
        "dha": "DHA Phase 6",
        "defence": "DHA Phase 6",
        "clifton": "Clifton",
        "pechs": "PECHS",
        "nazimabad": "Nazimabad",
        "north nazimabad": "North Nazimabad",
        "bahadurabad": "Bahadurabad",
        "saddar": "Saddar",
        "gulberg": "Gulberg",
        "fb area": "FB Area",
        "korangi": "Korangi",
        "liaquatabad": "Liaquatabad",
    }

    location = None
    for key, label in area_map.items():
        if key in text:
            location = label
            break

    if not location:
        location = "Gulshan-e-Iqbal"
        logs.append(f"[INTENT AGENT] No location found, defaulting to Gulshan-e-Iqbal")
    else:
        logs.append(f"[INTENT AGENT] Extracted location: {location}")

    time_val = None
    if "kal" in text or "tomorrow" in text:
        time_val = "Tomorrow"
    elif "aaj" in text or "today" in text:
        time_val = "Today"
    if "subah" in text or "morning" in text:
        time_val = (time_val + " " if time_val else "") + "Morning (9AM-12PM)"
    elif "dopahar" in text or "afternoon" in text:
        time_val = (time_val + " " if time_val else "") + "Afternoon (12PM-3PM)"
    elif "sham" in text or "evening" in text:
        time_val = (time_val + " " if time_val else "") + "Evening (4PM-7PM)"
    if not time_val:
        time_val = "Flexible"
    logs.append(f"[INTENT AGENT] Extracted time: {time_val}")

    return {
        "service_type": service_type,
        "location": location,
        "time": time_val,
        "language": lang,
        "logs": logs
    }


def discover_providers(service_type: str, location: str, all_providers: list) -> dict:
    logs = []
    logs.append(f"[DISCOVERY AGENT] Searching for: {service_type} near {location}")

    if not service_type:
        logs.append("[DISCOVERY AGENT] No service type provided, returning empty")
        return {"providers": [], "logs": logs}

    filtered = [
        p for p in all_providers
        if p["service_type"].lower() == service_type.lower()
    ]

    if not filtered:
        logs.append(f"[DISCOVERY AGENT] No exact match found. Expanding search.")
        filtered = sorted(all_providers, key=lambda x: x["rating"], reverse=True)[:2]
        logs.append(f"[DISCOVERY AGENT] Fallback: returning top {len(filtered)} rated providers")
    else:
        logs.append(f"[DISCOVERY AGENT] Found {len(filtered)} providers: {[p['name'] for p in filtered]}")

    return {"providers": filtered, "logs": logs}


def rank_providers(providers: list) -> dict:
    logs = []
    logs.append(f"[RANKING AGENT] Evaluating {len(providers)} candidates")
    logs.append(f"[RANKING AGENT] Decision criteria: proximity to user location, service rating, slot availability")
    logs.append(f"[RANKING AGENT] Applying weighted scoring model")
    logs.append("[RANKING AGENT] Formula: (1/distance * 0.4) + (rating/5 * 0.4) + (slots/3 * 0.2)")

    ranked = []
    for p in providers:
        dist_score = (1 / (p["distance_from_g13_km"] + 0.1)) * 0.4
        rating_score = (p["rating"] / 5.0) * 0.4
        slots_score = (len(p["available_slots"]) / 3.0) * 0.2
        total_score = round(dist_score + rating_score + slots_score, 3)

        reasoning = (
            f"Distance {p['distance_from_g13_km']}km (score: {round(dist_score,3)}) + "
            f"Rating {p['rating']}* (score: {round(rating_score,3)}) + "
            f"{len(p['available_slots'])} slots (score: {round(slots_score,3)})"
        )

        p_copy = dict(p)
        p_copy["score"] = total_score
        p_copy["reasoning"] = reasoning
        ranked.append(p_copy)
        logs.append(f"[RANKING AGENT] {p['name']}: total score = {total_score}")

    ranked.sort(key=lambda x: x["score"], reverse=True)
    for i, p in enumerate(ranked):
        logs.append(f"[RANKING AGENT] Rank {i+1}: {p['name']} ({p['score']})")

    if ranked:
        logs.append(f"[RANKING AGENT] DECISION: Recommending {ranked[0]['name']} - highest composite score of {ranked[0]['score']}")
        logs.append(f"[RANKING AGENT] Reasoning: {ranked[0]['reasoning']}")

    return {"ranked": ranked, "logs": logs}


def simulate_booking(provider: dict, time_slot: str, service_type: str) -> dict:
    logs = []
    booking_id = "BK-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    logs.append(f"[BOOKING AGENT] Generating booking ID: {booking_id}")

    booking = {
        "booking_id": booking_id,
        "provider_name": provider["name"],
        "provider_phone": provider.get("phone", "N/A"),
        "provider_area": provider.get("area", "N/A"),
        "service_type": service_type,
        "slot": time_slot,
        "price_per_hour": provider.get("price_per_hour", 0),
        "status": "confirmed",
        "timestamp": datetime.now().isoformat()
    }

    logs.append(f"[BOOKING AGENT] Provider assigned: {provider['name']}")
    logs.append(f"[BOOKING AGENT] Slot confirmed: {time_slot}")

    try:
        bookings = []
        if os.path.exists(BOOKINGS_FILE):
            with open(BOOKINGS_FILE, "r") as f:
                try:
                    bookings = json.load(f)
                except Exception:
                    bookings = []
        bookings.append(booking)
        with open(BOOKINGS_FILE, "w") as f:
            json.dump(bookings, f, indent=4)
        logs.append(f"[BOOKING AGENT] Booking written to bookings.json")
    except Exception as e:
        logs.append(f"[BOOKING AGENT] File error: {str(e)}")

    confirmation = (
        f"Booking {booking_id} confirmed! {service_type} with {provider['name']} "
        f"at {time_slot}. Contact: {provider.get('phone', 'N/A')}. "
        f"Rate: PKR {provider.get('price_per_hour', 0)}/hr"
    )

    return {
        "booking": booking,
        "confirmation_message": confirmation,
        "logs": logs
    }


def schedule_followup(booking: dict, reminder_minutes: int = 60) -> dict:
    logs = []
    logs.append(f"[FOLLOWUP AGENT] Scheduling reminder for booking {booking['booking_id']}")

    try:
        slot_time = datetime.strptime(booking["slot"], "%I:%M %p")
        reminder_time = (slot_time - timedelta(minutes=reminder_minutes)).strftime("%I:%M %p")
        logs.append(f"[FOLLOWUP AGENT] Reminder set for {reminder_time} ({reminder_minutes} mins before {booking['slot']})")

        if os.path.exists(BOOKINGS_FILE):
            with open(BOOKINGS_FILE, "r") as f:
                bookings = json.load(f)
            for b in bookings:
                if b["booking_id"] == booking["booking_id"]:
                    b["reminder"] = reminder_time
                    b["reminder_minutes"] = reminder_minutes
                    break
            with open(BOOKINGS_FILE, "w") as f:
                json.dump(bookings, f, indent=4)
            logs.append(f"[FOLLOWUP AGENT] Reminder saved to bookings.json")

        return {
            "reminder_time": reminder_time,
            "message": f"Reminder scheduled at {reminder_time}, {reminder_minutes} minutes before your appointment.",
            "logs": logs
        }

    except Exception as e:
        logs.append(f"[FOLLOWUP AGENT] Error: {str(e)}")
        return {
            "reminder_time": None,
            "message": "Reminder could not be scheduled",
            "logs": logs
        }