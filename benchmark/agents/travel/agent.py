"""Travel agent: tells a passenger whether their flight is on time (benchmark agent)."""

import json

from chaos_doctor.simulated import SimulatedClient

client = SimulatedClient()

FLIGHTS = {
    "6E-204": {"flight": "6E-204", "passenger": "Kiran", "status": "delayed", "gate": "12"},
    "AI-501": {"flight": "AI-501", "passenger": "Divya", "status": "boarding", "gate": "3"},
    "UK-818": {"flight": "UK-818", "passenger": "Arjun", "status": "cancelled", "gate": "-"},
}

TOOLS = ["flight_status_api"]
TASKS = [{"flight": "6E-204"}, {"flight": "AI-501"}, {"flight": "UK-818"}]


def flight_status_api(code):
    """Tool: live flight status from the airline API."""
    return dict(FLIGHTS[code])


def generate_reply(text):
    """LLM call that writes the message to the passenger."""
    r = client.chat.completions.create(
        model="simulated", messages=[{"role": "user", "content": text}]
    )
    return r.choices[0].message.content


def lookup_flight(code):
    """Find the passenger's flight."""
    return flight_status_api(code)


def run(task):
    info = lookup_flight(task["flight"])
    return generate_reply(f"Tell the passenger about their flight. Details: {json.dumps(info)}")


def check(task, answer):
    return isinstance(answer, str) and FLIGHTS[task["flight"]]["status"] in answer.lower()
