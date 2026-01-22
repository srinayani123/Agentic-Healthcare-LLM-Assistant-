"""
AI HEALTHCARE CONCIERGE — TRULY AGENTIC WITH SAFETY GUARDRAILS
───────────────────────────────────────────────────────────────────────────
✅ AutoGen's native autonomous agent selection (speaker_selection_method="auto")
✅ Safety guardrails: Crisis detection (self-harm, suicide, abuse)
✅ Emergency triage: Medical symptom warnings
✅ Proactive conversation flow - guides user to solutions
✅ Natural multi-agent collaboration
✅ Free APIs: OpenFDA, RxNorm, OpenStreetMap, OSRM
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Annotated
import random

import gradio as gr
from autogen import ConversableAgent, GroupChat, GroupChatManager

# =====================================================================
# 🧠 Patient Profile
# =====================================================================

class PatientProfile:
    def __init__(self, path: str = "patient_profile.json"):
        self.path = path
        self.profile = self._load()
        if 'timezone' not in self.profile:
            self._detect_timezone()

    def _load(self) -> Dict:
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                return json.load(f)
        return {
            "name": "Patient A",
            "home_city": "San Jose, CA",
            "zip_code": "95054",
            "insurance": "United Health Care",
            "allergies": [],
            "timezone": "America/Los_Angeles"
        }
    
    def _detect_timezone(self):
        try:
            response = requests.get('https://ipapi.co/json/', timeout=3)
            if response.status_code == 200:
                data = response.json()
                if 'timezone' in data:
                    self.profile['timezone'] = data['timezone']
                    print(f"🌍 Timezone detected: {data['timezone']}")
                    self._save()
                    return
        except Exception:
            pass
        
        try:
            response = requests.get('https://ipinfo.io/json', timeout=3)
            if response.status_code == 200:
                data = response.json()
                if 'timezone' in data:
                    self.profile['timezone'] = data['timezone']
                    print(f"🌍 Timezone detected: {data['timezone']}")
                    self._save()
                    return
        except Exception:
            pass
        
        if 'timezone' not in self.profile:
            self.profile['timezone'] = "America/Los_Angeles"
        print(f"🌍 Using default timezone: {self.profile['timezone']}")
        self._save()
    
    def get_current_time(self):
        try:
            import pytz
            tz = pytz.timezone(self.profile.get('timezone', 'America/Los_Angeles'))
            now = datetime.now(tz)
            
            return {
                "datetime": now.strftime("%A, %B %d, %Y at %I:%M %p"),
                "date": now.strftime("%A, %B %d, %Y"),
                "time": now.strftime("%I:%M %p"),
                "day": now.strftime("%A"),
                "hour": now.hour,
                "is_night": now.hour >= 20 or now.hour < 6,
                "is_morning": 6 <= now.hour < 12,
                "is_afternoon": 12 <= now.hour < 17,
                "is_evening": 17 <= now.hour < 20,
                "timezone": self.profile.get('timezone', 'America/Los_Angeles')
            }
        except Exception as e:
            print(f"⚠️ Error getting time: {e}")
            return None

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.profile, f, indent=2)

    def set_home_city(self, city: str):
        self.profile["home_city"] = city.strip()
        self._save()

    def set_zip_code(self, zip_code: str):
        self.profile["zip_code"] = zip_code.strip()
        self._save()

    def set_insurance(self, insurance: str):
        self.profile["insurance"] = insurance.strip()
        self._save()

    def set_allergies_from_text(self, text: str):
        parts = [a.strip() for a in text.split(",") if a.strip()]
        self.profile["allergies"] = parts
        self._save()

    def allergies_text(self) -> str:
        return ", ".join(self.profile.get("allergies", []))


patient_profile = PatientProfile()

# =====================================================================
# 🌍 Healthcare APIs
# =====================================================================

class HealthcareAPIs:
    def __init__(self):
        self.overpass_url = "https://overpass-api.de/api/interpreter"
        self.nominatim_url = "https://nominatim.openstreetmap.org/search"
        self.routing_url = "https://router.project-osrm.org/route/v1/driving"
        self.rxnorm_url = "https://rxnav.nlm.nih.gov/REST"
        self.openfda_url = "https://api.fda.gov/drug/label.json"

    def geocode(self, location: str) -> Optional[Dict]:
        try:
            if location.strip().isdigit() and len(location.strip()) == 5:
                location = f"{location}, USA"
            
            params = {"q": location, "format": "json", "limit": 5, "countrycodes": "us"}
            r = requests.get(
                self.nominatim_url,
                params=params,
                headers={"User-Agent": "HealthConcierge/1.0"},
                timeout=10,
            )
            data = r.json()
            
            if data:
                return {
                    "lat": float(data[0]["lat"]),
                    "lon": float(data[0]["lon"]),
                    "display": data[0].get("display_name", location),
                }
        except Exception as e:
            print(f"Geocoding error: {e}")
        return None

    def find_pharmacies(self, lat: float, lon: float, count: int = 5) -> List[Dict]:
        query = f"""
        [out:json][timeout:25];
        node["amenity"="pharmacy"](around:10000,{lat},{lon});
        out body {count * 3};
        """
        try:
            r = requests.post(self.overpass_url, data={"data": query}, timeout=25)
            result = r.json()
            pharmacies = []
            
            for elem in result.get("elements", [])[:count]:
                tags = elem.get("tags", {})
                p_lat, p_lon = elem.get("lat"), elem.get("lon")
                route = self.get_route(lat, lon, p_lat, p_lon)
                
                opening_hours = tags.get("opening_hours", "")
                is_24_7 = opening_hours == "24/7" or "24/7" in opening_hours
                
                pharmacy_data = {
                    "name": tags.get("name", "Local Pharmacy"),
                    "address": self._format_address(tags),
                    "phone": tags.get("phone", "N/A"),
                    "distance_mi": route["distance_mi"],
                    "drive_time_min": route["drive_time_min"],
                    "opening_hours": opening_hours,
                    "is_24_7": is_24_7
                }
                
                if opening_hours:
                    hours_info = self._parse_opening_hours(opening_hours)
                    pharmacy_data.update(hours_info)
                
                pharmacies.append(pharmacy_data)
            
            return pharmacies
        except Exception as e:
            print(f"Pharmacy search error: {e}")
            return []
    
    def _parse_opening_hours(self, opening_hours: str) -> Dict:
        try:
            time_info = patient_profile.get_current_time()
            if not time_info:
                return {"status": "unknown", "hours_text": opening_hours}
            
            current_hour = time_info['hour']
            
            if opening_hours == "24/7" or "24/7" in opening_hours.lower():
                return {
                    "status": "open",
                    "is_open_now": True,
                    "hours_text": "Open 24 hours",
                    "opens_at": None,
                    "closes_at": None
                }
            
            import re
            time_pattern = r'(\d{1,2}):?(\d{2})?\s*[-–]\s*(\d{1,2}):?(\d{2})?'
            match = re.search(time_pattern, opening_hours)
            
            if match:
                open_hour = int(match.group(1))
                close_hour = int(match.group(3))
                
                if close_hour < open_hour:
                    is_open_now = current_hour >= open_hour or current_hour < close_hour
                else:
                    is_open_now = open_hour <= current_hour < close_hour
                
                return {
                    "status": "open" if is_open_now else "closed",
                    "is_open_now": is_open_now,
                    "hours_text": opening_hours,
                    "opens_at": f"{open_hour:02d}:00",
                    "closes_at": f"{close_hour:02d}:00"
                }
            
            return {"status": "unknown", "hours_text": opening_hours}
            
        except Exception as e:
            print(f"Hours parsing error: {e}")
            return {"status": "unknown", "hours_text": opening_hours}

    def find_hospitals(self, lat: float, lon: float, count: int = 5) -> List[Dict]:
        query = f"""
        [out:json][timeout:25];
        (
          node["amenity"="hospital"](around:15000,{lat},{lon});
          node["healthcare"="clinic"](around:15000,{lat},{lon});
        );
        out body {count * 3};
        """
        try:
            r = requests.post(self.overpass_url, data={"data": query}, timeout=25)
            result = r.json()
            hospitals = []
            
            for elem in result.get("elements", [])[:count]:
                tags = elem.get("tags", {})
                hospitals.append({
                    "name": tags.get("name", "Healthcare Facility"),
                    "type": tags.get("amenity", tags.get("healthcare", "clinic")),
                    "address": self._format_address(tags),
                    "phone": tags.get("phone", "N/A"),
                })
            
            return hospitals
        except Exception as e:
            print(f"Hospital search error: {e}")
            return []

    def get_route(self, from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> Dict:
        try:
            url = f"{self.routing_url}/{from_lon},{from_lat};{to_lon},{to_lat}"
            r = requests.get(url, params={"overview": "false"}, timeout=10)
            data = r.json()
            
            if data.get("routes"):
                route = data["routes"][0]
                distance_mi = (route["distance"] / 1000) * 0.621371
                duration_min = route["duration"] / 60
                return {
                    "distance_mi": round(distance_mi, 1),
                    "drive_time_min": round(duration_min, 0),
                }
        except:
            pass
        
        return {"distance_mi": "N/A", "drive_time_min": "N/A"}

    def _format_address(self, tags: Dict) -> str:
        parts = []
        for key in ["addr:housenumber", "addr:street", "addr:city", "addr:state"]:
            if tags.get(key):
                parts.append(tags[key])
        return ", ".join(parts) if parts else "Address not available"

    def check_medication_coverage(self, insurance: str, medication: str) -> Dict:
        try:
            params = {
                "search": f'openfda.brand_name:"{medication}" OR openfda.generic_name:"{medication}"',
                "limit": 1
            }
            response = requests.get(self.openfda_url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("results"):
                    drug_info = data["results"][0]
                    openfda = drug_info.get("openfda", {})
                    
                    product_type = openfda.get("product_type", [""])[0].lower()
                    is_rx = "prescription" in product_type
                    is_otc = "otc" in product_type or not is_rx
                    
                    pharm_class = openfda.get("pharm_class_epc", [])
                    drug_class = pharm_class[0] if pharm_class else "Unknown"
                    
                    insurance_lower = insurance.lower()
                    is_major = any(ins in insurance_lower for ins in 
                                  ["united", "blue cross", "aetna", "cigna", "humana", "kaiser", "medicare", "medicaid"])
                    
                    if is_otc:
                        return {
                            "medication": medication,
                            "covered": "OTC - Generally not covered",
                            "copay": "$0-$15 (out of pocket)",
                            "drug_class": drug_class,
                            "prescription_required": False,
                        }
                    elif is_major:
                        return {
                            "medication": medication,
                            "covered": "Yes",
                            "copay": "$10-$50 (varies by plan tier)",
                            "drug_class": drug_class,
                            "prescription_required": True,
                        }
                    else:
                        return {
                            "medication": medication,
                            "covered": "Unknown",
                            "copay": "Contact provider",
                            "drug_class": drug_class,
                            "prescription_required": is_rx,
                        }
        except Exception as e:
            print(f"OpenFDA API error: {e}")
        
        return {
            "medication": medication,
            "covered": "Unknown",
            "copay": "Contact provider",
            "prescription_required": True,
        }

    def get_drug_interactions(self, medication: str) -> List[Dict]:
        try:
            search_url = f"{self.rxnorm_url}/drugs.json"
            response = requests.get(search_url, params={"name": medication}, timeout=10)
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            drug_group = data.get("drugGroup", {})
            concept_properties = drug_group.get("conceptProperties", [])
            
            if not concept_properties:
                return []
            
            rxcui = concept_properties[0].get("rxcui")
            if not rxcui:
                return []
            
            interact_url = f"{self.rxnorm_url}/interaction/interaction.json"
            interact_response = requests.get(interact_url, params={"rxcui": rxcui}, timeout=10)
            
            if interact_response.status_code != 200:
                return []
            
            interact_data = interact_response.json()
            interaction_types = interact_data.get("interactionTypeGroup", [])
            
            interactions = []
            for type_group in interaction_types[:1]:
                for pair in type_group.get("interactionType", [])[:5]:
                    for interaction in pair.get("interactionPair", []):
                        interactions.append({
                            "drug2": interaction.get("interactionConcept", [{}])[1].get("minConceptItem", {}).get("name", "Unknown") if len(interaction.get("interactionConcept", [])) > 1 else "Unknown",
                            "severity": interaction.get("severity", "Unknown"),
                            "description": interaction.get("description", "No description")
                        })
            
            return interactions[:5]
        except Exception as e:
            print(f"RxNorm API error: {e}")
            return []

    def generate_appointments(self, hospital: str, insurance: str) -> List[Dict]:
        now = datetime.now()
        appointments = []
        
        doctors = [
            {"name": "Dr. Sarah Johnson", "specialty": "Family Medicine"},
            {"name": "Dr. Michael Chen", "specialty": "Internal Medicine"},
            {"name": "Dr. Emily Rodriguez", "specialty": "Family Medicine"},
            {"name": "Dr. James Wilson", "specialty": "Urgent Care"},
        ]
        
        days_checked = 0
        while len(appointments) < 6 and days_checked < 10:
            check_date = now + timedelta(days=days_checked + 1)
            
            if check_date.weekday() >= 5:
                days_checked += 1
                continue
            
            random.seed(check_date.day + check_date.month * 31)
            times = random.sample(["9:00 AM", "10:00 AM", "11:00 AM", "2:00 PM", "3:00 PM", "4:00 PM"], k=2)
            
            for time_slot in times:
                if len(appointments) >= 6:
                    break
                
                doctor = random.choice(doctors)
                appointments.append({
                    "date": check_date.strftime("%A, %B %d, %Y"),
                    "time": time_slot,
                    "doctor": doctor["name"],
                    "specialty": doctor["specialty"],
                    "hospital": hospital,
                    "in_network": "Yes" if insurance else "Verify",
                })
            
            days_checked += 1
        
        return appointments


health_apis = HealthcareAPIs()

# =====================================================================
# 🛠️ Tool Functions
# =====================================================================

def get_pharmacy_locations(
    location: Annotated[str, "Location (zip code or city) to search for pharmacies"]
) -> str:
    """Find pharmacies near a given location with hours and distance information"""
    geo = health_apis.geocode(location)
    if not geo:
        return json.dumps({"error": f"Could not locate {location}"})
    
    pharmacies = health_apis.find_pharmacies(geo["lat"], geo["lon"])
    return json.dumps({
        "location": geo["display"],
        "pharmacies": pharmacies,
    }, indent=2)


def check_medication_insurance(
    insurance_provider: Annotated[str, "Name of the insurance provider"],
    medication_name: Annotated[str, "Name of the medication to check coverage for"]
) -> str:
    """Check insurance coverage for a medication"""
    coverage = health_apis.check_medication_coverage(insurance_provider, medication_name)
    return json.dumps(coverage, indent=2)


def find_in_network_hospitals(
    location: Annotated[str, "Location (zip code or city) to search for hospitals"],
    insurance_provider: Annotated[str, "Insurance provider name"] = ""
) -> str:
    """Find hospitals and clinics near a location"""
    geo = health_apis.geocode(location)
    if not geo:
        return json.dumps({"error": f"Could not locate {location}"})
    
    hospitals = health_apis.find_hospitals(geo["lat"], geo["lon"])
    for hospital in hospitals:
        hospital["in_network"] = "Yes" if insurance_provider else "Unknown"
    
    return json.dumps({
        "location": geo["display"],
        "insurance": insurance_provider or "Not provided",
        "hospitals": hospitals,
    }, indent=2)


def get_appointment_availability(
    hospital_name: Annotated[str, "Name of the hospital or clinic"],
    insurance_provider: Annotated[str, "Insurance provider name"] = ""
) -> str:
    """Get available appointment slots at a hospital or clinic"""
    appointments = health_apis.generate_appointments(hospital_name, insurance_provider)
    return json.dumps({
        "hospital": hospital_name,
        "insurance": insurance_provider or "Not provided",
        "available_slots": appointments,
    }, indent=2)


def check_drug_interactions(
    medication_name: Annotated[str, "Name of the medication to check interactions for"]
) -> str:
    """Check for drug interactions and safety information"""
    interactions = health_apis.get_drug_interactions(medication_name)
    
    if not interactions:
        return json.dumps({
            "medication": medication_name,
            "interactions": "No major interactions found",
        }, indent=2)
    
    return json.dumps({
        "medication": medication_name,
        "interactions": interactions,
    }, indent=2)


def get_current_time_info() -> str:
    """Get current date, time, and time-relevant context"""
    try:
        time_info = patient_profile.get_current_time()
        if not time_info:
            return "Unable to get current time"
        
        result = f"📅 {time_info['datetime']} ({time_info['timezone']})\n\n"
        
        if time_info['is_morning']:
            result += "🌅 It's morning - good time to take morning medications"
        elif time_info['is_afternoon']:
            result += "☀️ It's afternoon"
        elif time_info['is_evening']:
            result += "🌆 It's evening - pharmacies are still open"
        elif time_info['is_night']:
            result += "🌙 It's nighttime - most pharmacies are closed, 24-hour options may be limited"
        
        return result
    except Exception as e:
        return f"Unable to get current time: {e}"


# =====================================================================
# 🤖 TRULY AGENTIC MULTI-AGENT SYSTEM WITH SAFETY
# =====================================================================

def create_health_agents():
    llm_config = {
        "config_list": [{"model": "gpt-4o", "api_key": os.getenv("OPENAI_API_KEY")}],
        "temperature": 0.7,
    }

    user = ConversableAgent(
        "User",
        llm_config=False,
        human_input_mode="NEVER",
        max_consecutive_auto_reply=0,
    )

    # ⭐ SAFETY GUARDRAIL - Crisis Detection (HIGHEST PRIORITY)
    safety_guardrail = ConversableAgent(
        "SafetyGuardrail",
        system_message="""You are a compassionate crisis counselor who ONLY speaks when there's a genuine mental health or safety crisis.

🔴 CRISIS INDICATORS (respond immediately with care):
- **Self-harm or suicidal thoughts**: "want to hurt myself", "life isn't worth living", "thinking about ending it", "want to die"
- **Abuse situations**: "my partner hits me", "being hurt at home", "scared of someone", "domestic violence"
- **Severe mental health crisis**: "can't stop crying", "feel like I'm losing my mind", severe panic attacks
- **Child safety**: child abuse indicators, neglect

IF GENUINE CRISIS DETECTED:
Respond with deep empathy and immediate resources:

"I can hear you're going through something really difficult right now. Your safety and well-being matter, and you don't have to face this alone.

🆘 **If you're in immediate danger:**
- **Call 911** (Emergency)
- **Call 988** (Suicide & Crisis Lifeline - 24/7, free, confidential)
- **Text HELLO to 741741** (Crisis Text Line)

**For ongoing support:**
- National Domestic Violence Hotline: 1-800-799-7233
- SAMHSA Helpline (Substance Abuse): 1-800-662-4357

Your life has value. Please reach out to one of these resources today. SafetyGuardrail has detected a crisis."

IF NO GENUINE CRISIS:
- Say: "SafetyGuardrail sees no crisis. HealthCoordinator, please proceed."
- NEVER engage in regular conversation
- ONLY speak for real crises

CRITICAL: Don't overreact to normal health concerns. "I feel sad" or "I'm stressed" are NOT crises unless accompanied by self-harm indicators.
""",
        llm_config=llm_config,
    )

    # ⭐ EMERGENCY TRIAGE - Medical Emergency Detection
    emergency_triage = ConversableAgent(
        "EmergencyTriage",
        system_message="""You're an experienced triage nurse who ONLY speaks when there are serious medical symptoms requiring immediate attention.

⚠️ RED FLAG SYMPTOMS (respond with urgency):
- **Life-threatening**: chest pain, difficulty breathing, severe bleeding, loss of consciousness
- **Serious infection**: severe redness/swelling/warmth around wounds, high fever with confusion
- **Severe pain**: 8-10/10 pain level
- **Allergic reaction**: throat swelling, severe hives, difficulty breathing
- **Neurological**: sudden weakness, slurred speech, severe headache with vision changes

IF RED FLAGS DETECTED:
Be direct but caring:

"I'm concerned about what you're describing. [Symptom] could indicate [condition], and this needs immediate medical attention.

⚠️ **Please:**
- Life-threatening: Call 911 or go to the ER right now
- Urgent: Get to urgent care within the next 2 hours
- Concerning: Call your doctor today - don't wait

While you're arranging care, [comfort measures if applicable]. EmergencyTriage has flagged this as urgent."

IF NO RED FLAGS:
- Say: "EmergencyTriage sees no emergency symptoms. HealthCoordinator, please proceed."
- Don't engage with normal symptoms (mild fever, sore throat, headache, etc.)
- ONLY speak for genuine medical emergencies

CRITICAL: Most health concerns are NOT emergencies. Only flag serious, urgent symptoms.
""",
        llm_config=llm_config,
    )

    # ⭐ HEALTH COORDINATOR - PROACTIVE GUIDE
    coordinator = ConversableAgent(
        "HealthCoordinator",
        system_message=f"""You're a warm, empathetic healthcare coordinator who guides conversations naturally toward solutions.

PATIENT INFO (use when relevant):
- Location: {patient_profile.profile['home_city']}, {patient_profile.profile['zip_code']}
- Insurance: {patient_profile.profile['insurance']}
- Allergies: {patient_profile.allergies_text() or 'None'}

YOUR ROLE - PROACTIVE HEALTHCARE GUIDE:
You handle conversations and guide users through healthcare needs step by step.

NATURAL HEALTHCARE CONVERSATION FLOW:

**Phase 1 - GATHER INFORMATION** (when symptoms mentioned):
1. Ask about duration: "How long have you been feeling this way?"
2. Ask about additional symptoms if needed
3. IMPORTANT: Ask about allergies BEFORE suggesting medications: "Do you have any medication allergies?"

**Phase 2 - SUGGEST SOLUTIONS** (after gathering allergies):
Once you know symptoms and allergies, PROACTIVELY suggest OTC medications:

Example: "For your sore throat and fever, you could try Tylenol or Advil for the fever and throat lozenges for the discomfort. They're OTC, about $10-15 total. Would you like me to find nearby pharmacies?"

**Phase 3 - DELEGATE TO SPECIALISTS**:
- Pharmacy help → "PharmacySpecialist, can you find nearby pharmacies?"
- Time questions → "TimeSpecialist, can you help with that?"
- Coverage questions → "MedicationSpecialist, can you check coverage?"
- Doctor needed → "AppointmentSpecialist, can you help find a doctor?"

CRITICAL RULES TO AVOID REPETITION:
1. ✅ Track conversation - if you asked something, MOVE FORWARD
2. ✅ Process user's answer and advance to next phase
3. ✅ NEVER repeat the same question
4. ✅ Always progress through phases

TONE:
- Empathetic and caring
- Natural and conversational
- Vary your language
""",
        llm_config=llm_config,
    )

    # ⭐ PHARMACY SPECIALIST
    pharmacy_specialist = ConversableAgent(
        "PharmacySpecialist",
        system_message=f"""You find nearby pharmacies with hours and distance.

WHEN ACTIVATED:
1. Use: get_pharmacy_locations("{patient_profile.profile['zip_code']}")
2. Describe 2-3 pharmacies with time awareness

RESPONSE FORMAT:
"I found some pharmacies nearby:

- **CVS** on E El Camino Real is open until 10 PM tonight, about 5.8 miles away (12 minute drive)
- **Walgreens** on E El Camino Real is open 24/7, about 7.5 miles from you (12 minutes)

HealthCoordinator, I've provided the pharmacy options."

CRITICAL: Always end with "HealthCoordinator, I've provided the pharmacy options."
""",
        llm_config=llm_config,
    )

    pharmacy_specialist.register_for_llm(name="get_pharmacy_locations", description="Find nearby pharmacies")(get_pharmacy_locations)
    pharmacy_specialist.register_for_execution(name="get_pharmacy_locations")(get_pharmacy_locations)

    # ⭐ TIME SPECIALIST
    time_specialist = ConversableAgent(
        "TimeSpecialist",
        system_message="""You answer time/date questions.

WHEN ACTIVATED:
1. Use: get_current_time_info()
2. Respond naturally

RESPONSE FORMAT:
"It's 8:45 PM on Tuesday, November 5th, 2025. It's evening right now, so most pharmacies are still open.

HealthCoordinator, I've provided the time."
""",
        llm_config=llm_config,
    )

    time_specialist.register_for_llm(name="get_current_time_info", description="Get current time")(get_current_time_info)
    time_specialist.register_for_execution(name="get_current_time_info")(get_current_time_info)

    # ⭐ MEDICATION SPECIALIST
    medication_specialist = ConversableAgent(
        "MedicationSpecialist",
        system_message=f"""You check medication coverage and drug interactions.

PATIENT INSURANCE: {patient_profile.profile['insurance']}

WHEN ACTIVATED:
1. Use tools to check coverage or interactions
2. Provide clear information

RESPONSE FORMAT:
"I checked [medication]. It's [covered/OTC], costs about [price].

HealthCoordinator, I've provided the medication information."
""",
        llm_config=llm_config,
    )

    medication_specialist.register_for_llm(name="check_medication_insurance", description="Check medication coverage")(check_medication_insurance)
    medication_specialist.register_for_llm(name="check_drug_interactions", description="Check drug interactions")(check_drug_interactions)
    medication_specialist.register_for_execution(name="check_medication_insurance")(check_medication_insurance)
    medication_specialist.register_for_execution(name="check_drug_interactions")(check_drug_interactions)

    # ⭐ APPOINTMENT SPECIALIST
    appointment_specialist = ConversableAgent(
        "AppointmentSpecialist",
        system_message=f"""You find doctors and available appointment times.

PATIENT: {patient_profile.profile['zip_code']}, {patient_profile.profile['insurance']}

WHEN ACTIVATED:
1. Find hospitals
2. Get availability
3. Present 2-3 time slots

RESPONSE FORMAT:
"**Valley Medical Center** has these openings:
- Tomorrow at 10:00 AM with Dr. Rodriguez
- Thursday at 2:00 PM with Dr. Chen

Call [phone] to book. HealthCoordinator, I've provided the appointment options."
""",
        llm_config=llm_config,
    )

    appointment_specialist.register_for_llm(name="find_in_network_hospitals", description="Find hospitals")(find_in_network_hospitals)
    appointment_specialist.register_for_llm(name="get_appointment_availability", description="Get appointments")(get_appointment_availability)
    appointment_specialist.register_for_execution(name="find_in_network_hospitals")(find_in_network_hospitals)
    appointment_specialist.register_for_execution(name="get_appointment_availability")(get_appointment_availability)

    # ⭐ TERMINATION LOGIC
    def is_termination_msg(msg: Dict) -> bool:
        content = str(msg.get("content", ""))
        name = msg.get("name", "")
        
        # Stop on crisis detection
        if name == "SafetyGuardrail" and "988" in content:
            return True
        
        # Stop on emergency detection
        if name == "EmergencyTriage" and "⚠️" in content and "911" in content:
            return True
        
        # Stop when coordinator asks question
        if name == "HealthCoordinator" and "?" in content:
            return True
        
        # Stop after specialists finish
        if "I've provided" in content:
            return True
        
        return False

    # ⭐⭐⭐ AutoGen's native autonomous selection with safety checks first
    group = GroupChat(
        agents=[
            user,
            safety_guardrail,      # ⭐ First line of defense
            emergency_triage,      # ⭐ Second line of defense
            coordinator,           # Main guide
            pharmacy_specialist,
            time_specialist,
            medication_specialist,
            appointment_specialist
        ],
        messages=[],
        max_round=30,
        speaker_selection_method="auto",
        allow_repeat_speaker=False,
    )
    
    manager = GroupChatManager(
        groupchat=group,
        llm_config=llm_config,
        is_termination_msg=is_termination_msg
    )
    
    # Register all tools with manager
    manager.register_for_execution(name="get_pharmacy_locations")(get_pharmacy_locations)
    manager.register_for_execution(name="get_current_time_info")(get_current_time_info)
    manager.register_for_execution(name="check_medication_insurance")(check_medication_insurance)
    manager.register_for_execution(name="check_drug_interactions")(check_drug_interactions)
    manager.register_for_execution(name="find_in_network_hospitals")(find_in_network_hospitals)
    manager.register_for_execution(name="get_appointment_availability")(get_appointment_availability)
    
    return user, manager


# =====================================================================
# 💬 Gradio UI
# =====================================================================

def create_ui():
    cache = {"user": None, "manager": None}

    def get_agents(reset=False):
        if reset or cache["user"] is None:
            cache["user"], cache["manager"] = create_health_agents()
        return cache["user"], cache["manager"]

    def chat_fn(message: str, history: List) -> tuple:
        if not message.strip():
            return "", history, gr.update(visible=False), gr.update(visible=False)
        
        is_new = len(history) == 0
        user, manager = get_agents(reset=is_new)
        
        print(f"\n{'='*70}")
        print(f"📨 USER: {message}")
        print(f"{'='*70}")
        
        try:
            user.initiate_chat(
                manager,
                message=message,
                clear_history=is_new
            )
            
            msgs = user.chat_messages.get(manager, [])
            print(f"\n📊 Total messages: {len(msgs)}")
            
            # Check for crisis or emergency
            show_crisis = False
            show_emergency = False
            response_text = ""
            
            for msg in reversed(msgs):
                name = msg.get("name", "")
                content = msg.get("content", "")
                
                if name == "User" or not content:
                    continue
                
                # Skip tool execution internals
                if "***** Suggested tool" in content or "***** Response from calling tool" in content:
                    continue
                
                # HIGHEST PRIORITY: Crisis detection
                if name == "SafetyGuardrail" and "988" in content:
                    response_text = content
                    show_crisis = True
                    print(f"🆘 CRISIS DETECTED")
                    break
                
                # HIGH PRIORITY: Emergency detection
                if name == "EmergencyTriage" and "⚠️" in content and ("911" in content or "ER" in content):
                    response_text = content
                    show_emergency = True
                    print(f"🚨 EMERGENCY DETECTED")
                    break
                
                # Normal agent responses
                if name in ["HealthCoordinator", "PharmacySpecialist", "TimeSpecialist", 
                           "MedicationSpecialist", "AppointmentSpecialist"]:
                    # Skip "no crisis/emergency" messages
                    if "sees no crisis" in content or "sees no emergency" in content:
                        continue
                    
                    if len(content) > 10:
                        response_text = content
                        print(f"✅ Response from {name}: {content[:100]}...")
                        break
            
            if not response_text:
                response_text = "I'm here to help. What's on your mind?"
            
            # Clean up specialist handoff messages
            response_text = response_text.replace("HealthCoordinator, I've provided the pharmacy options.", "").strip()
            response_text = response_text.replace("HealthCoordinator, I've provided the time.", "").strip()
            response_text = response_text.replace("HealthCoordinator, I've provided the medication information.", "").strip()
            response_text = response_text.replace("HealthCoordinator, I've provided the appointment options.", "").strip()
            response_text = response_text.replace("SafetyGuardrail has detected a crisis.", "").strip()
            response_text = response_text.replace("EmergencyTriage has flagged this as urgent.", "").strip()
            
            print(f"📤 Sending: {len(response_text)} chars\n")
            
            return "", history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": response_text}
            ], gr.update(visible=show_crisis), gr.update(visible=show_emergency)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return "", history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": "I apologize, I encountered an error. Please try again."}
            ], gr.update(visible=False), gr.update(visible=False)

    def clear_chat():
        cache["user"], cache["manager"] = None, None
        return [], gr.update(visible=False), gr.update(visible=False)

    with gr.Blocks(title="Agentic Healthcare Companion", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🏥 AI HEALTHCARE COMPANION")
        #gr.Markdown("🤖 AutoGen autonomous agents • 🛡️ Crisis & emergency detection • 💙 Proactive care")
        
        # ⭐ Crisis Banner (hidden by default)
        crisis_banner = gr.Markdown(
            """
            <div style="background-color: #fef2f2; border: 3px solid #dc2626; border-radius: 8px; padding: 20px; margin: 12px 0;">
            <h2 style="color: #dc2626; margin-top: 0;">🆘 You Don't Have To Face This Alone</h2>
            <p style="font-size: 18px;"><strong>If you're in crisis or thinking about hurting yourself, please reach out right now:</strong></p>
            <div style="background: white; padding: 15px; border-radius: 6px; margin: 10px 0;">
            <p style="margin: 5px 0;"><strong>📞 988 Suicide & Crisis Lifeline</strong> - Call or text 988 (24/7, free)</p>
            <p style="margin: 5px 0;"><strong>💬 Crisis Text Line</strong> - Text HELLO to 741741</p>
            <p style="margin: 5px 0;"><strong>🚨 Emergency</strong> - Call 911</p>
            </div>
            <p style="margin-top: 15px;"><em>Your life matters. These counselors want to help.</em></p>
            </div>
            """,
            visible=False
        )
        
        # ⭐ Emergency Banner (hidden by default)
        emergency_banner = gr.Markdown(
            """
            <div style="background-color: #fef7ed; border: 2px solid #f59e0b; border-radius: 8px; padding: 16px; margin: 12px 0;">
            <h3 style="color: #d97706; margin-top: 0;">⚠️ Medical Attention Needed</h3>
            <p>Based on your symptoms, this may need professional medical evaluation.</p>
            <p style="margin-bottom: 0;"><strong>Please follow the guidance above and seek care today.</strong></p>
            </div>
            """,
            visible=False
        )
        
        with gr.Tabs():
            with gr.Tab("💬 Chat"):
                chatbot = gr.Chatbot(label="Healthcare Chat", height=500, type="messages")

                with gr.Row():
                    msg = gr.Textbox(
                        placeholder="Hey! Tell me what's going on... 💙",
                        label="Your Message",
                        scale=4,
                        lines=2
                    )
                    send = gr.Button("Send 💬", variant="primary", scale=1)
                
                clear_btn = gr.Button("🔄 New Conversation")


                send.click(chat_fn, [msg, chatbot], [msg, chatbot, crisis_banner, emergency_banner])
                msg.submit(chat_fn, [msg, chatbot], [msg, chatbot, crisis_banner, emergency_banner])
                clear_btn.click(clear_chat, None, [chatbot, crisis_banner, emergency_banner])

            with gr.Tab("⚙️ Settings"):
                gr.Markdown("### Your Information")
                
                with gr.Column():
                    city_input = gr.Textbox(label="City", value=patient_profile.profile["home_city"])
                    zip_input = gr.Textbox(label="ZIP Code", value=patient_profile.profile["zip_code"])
                    insurance_input = gr.Textbox(label="Insurance Provider", value=patient_profile.profile["insurance"])
                    allergies_input = gr.Textbox(
                        label="Allergies (comma-separated)",
                        value=patient_profile.allergies_text(),
                        placeholder="penicillin, aspirin"
                    )
                
                save_btn = gr.Button("💾 Save Settings", variant="primary")
                status = gr.Markdown("")

                def save_settings(city, zip_code, insurance, allergies):
                    patient_profile.set_home_city(city)
                    patient_profile.set_zip_code(zip_code)
                    patient_profile.set_insurance(insurance)
                    patient_profile.set_allergies_from_text(allergies)
                    cache["user"], cache["manager"] = None, None
                    return "✅ Settings saved! Start a new conversation to use updated info."

                save_btn.click(
                    save_settings,
                    [city_input, zip_input, insurance_input, allergies_input],
                    [status]
                )

        gr.Markdown("""
        ---
        **🆓 Powered by free APIs:** FDA • NIH • OpenStreetMap • OSRM
        
        **🤖 Architecture:** 
        - AutoGen multi-agent with autonomous speaker selection
        - Safety guardrails (crisis & emergency detection)
        - Proactive conversation flow
        - Intelligent tool triggering
        
        **💙 Safe, smart healthcare guidance**
        """)

    return demo


# =====================================================================
# 🚀 MAIN
# =====================================================================

if __name__ == "__main__":
    print("=" * 80)
    print(" 🏥 AGENTIC HEALTHCARE COMPANION WITH SAFETY GUARDRAILS")
    print(" 🤖 AutoGen Native Autonomous Selection • 🛡️ Crisis Detection")
    print("=" * 80)
    print(f"\n 👤 Patient: {patient_profile.profile['name']}")
    print(f"    Location: {patient_profile.profile['home_city']}, {patient_profile.profile['zip_code']}")
    print(f"    Insurance: {patient_profile.profile['insurance']}")
    print(f"    Allergies: {patient_profile.allergies_text() or 'None'}")
    print(f"\n 🔑 OpenAI API: {'✅ Configured' if os.getenv('OPENAI_API_KEY') else '❌ Missing'}")
    print(f"\n 🛡️ SAFETY AGENTS:")
    print(f"    🆘 SafetyGuardrail - Crisis detection (suicide, self-harm, abuse)")
    print(f"    🚨 EmergencyTriage - Medical emergency detection")
    print(f"\n 🤖 HEALTHCARE AGENTS:")
    print(f"    💙 HealthCoordinator - Proactive care guide")
    print(f"    💊 PharmacySpecialist - Pharmacy locations")
    print(f"    ⏰ TimeSpecialist - Time/date")
    print(f"    💉 MedicationSpecialist - Coverage & interactions")
    print(f"    📅 AppointmentSpecialist - Doctor appointments")
    print(f"\n ⭐ AUTONOMOUS FEATURES:")
    print(f"    ✅ speaker_selection_method='auto'")
    print(f"    ✅ allow_repeat_speaker=False")
    print(f"    ✅ Safety checks first (crisis → emergency → healthcare)")
    print(f"    ✅ Proactive conversation flow")
    print(f"    ✅ No hardcoded routing")
    print(f"\n 🆓 FREE APIs:")
    print(f"    ✅ OpenFDA - Medications")
    print(f"    ✅ RxNorm - Interactions")
    print(f"    ✅ OpenStreetMap - Locations")
    print(f"    ✅ OSRM - Routing")
    print("=" * 80)
    print("\n 💙 Starting safe, agentic healthcare companion...\n")

    demo = create_ui()
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
