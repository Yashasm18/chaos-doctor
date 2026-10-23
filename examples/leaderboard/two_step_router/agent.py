"""Pattern: two-step router. One model call picks the route, a tool runs, a second call replies.

Written from scratch for the Chaos Doctor leaderboard. Two separate model calls means two
places that need protecting, which is common in real agents and easy to half-fix.
"""

import json

from chaos_doctor.simulated import SimulatedClient

client = SimulatedClient()

ACCOUNTS = {
    "acc-1": {"account": "acc-1", "name": "Nisha", "status": "active"},
    "acc-2": {"account": "acc-2", "name": "Omar", "status": "suspended"},
    "acc-3": {"account": "acc-3", "name": "Lena", "status": "closed"},
}

TOOLS = ["account_api"]
TASKS = [{"account": "acc-1"}, {"account": "acc-2"}, {"account": "acc-3"}]


def account_api(account_id):
    """Tool: fetch account state from the billing service."""
    return dict(ACCOUNTS[account_id])


def classify(question):
    """First model call: decide which route to take."""
    r = client.chat.completions.create(
        model="simulated", messages=[{"role": "user", "content": question}]
    )
    return r.choices[0].message.content


def fetch_account(account_id):
    return account_api(account_id)


def respond(prompt):
    """Second model call: write the reply to the user."""
    r = client.chat.completions.create(
        model="simulated", messages=[{"role": "user", "content": prompt}]
    )
    return r.choices[0].message.content


def run(task):
    classify(f"Route this request: what is the state of account {task['account']}?")
    acct = fetch_account(task["account"])
    return respond(f"Tell the user their account state. Details: {json.dumps(acct)}")


def check(task, reply):
    return isinstance(reply, str) and ACCOUNTS[task["account"]]["status"] in reply.lower()
