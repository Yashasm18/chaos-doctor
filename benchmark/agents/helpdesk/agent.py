"""IT helpdesk agent: answers "what's happening with my ticket?" (benchmark agent)."""

import json

from chaos_doctor.simulated import SimulatedClient

model_client = SimulatedClient()

TICKETS = {
    "T-101": {
        "ticket_id": "T-101",
        "requester": "Asha",
        "status": "escalated",
        "summary": "VPN down",
    },
    "T-102": {
        "ticket_id": "T-102",
        "requester": "Ravi",
        "status": "resolved",
        "summary": "New laptop",
    },
    "T-103": {
        "ticket_id": "T-103",
        "requester": "Meera",
        "status": "waiting",
        "summary": "Reset MFA",
    },
}

client = model_client
TOOLS = ["fetch_ticket"]
TASKS = [{"ticket": "T-101"}, {"ticket": "T-102"}, {"ticket": "T-103"}]


def fetch_ticket(ticket_id):
    """Tool: read one ticket from the helpdesk system."""
    return dict(TICKETS[ticket_id])


def load_ticket(ticket_id):
    """Get the ticket the user is asking about."""
    return fetch_ticket(ticket_id)


def complete(prompt):
    """Ask the language model for a reply."""
    out = model_client.chat.completions.create(
        model="simulated", messages=[{"role": "user", "content": prompt}]
    )
    return out.choices[0].message.content


def run(task):
    ticket = load_ticket(task["ticket"])
    return complete(f"Explain the ticket to the requester. Details: {json.dumps(ticket)}")


def check(task, answer):
    return isinstance(answer, str) and TICKETS[task["ticket"]]["status"] in answer.lower()
