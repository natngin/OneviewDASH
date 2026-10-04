"""
Configuration for Action Recommendation (CAPA) Engine.
All SLA parameters and Roster data are proposals/dummy.
"""

# SLA in hours (Proposal / USULAN)
SLA_HOURS = {
    "CRITICAL": 4.0,       # 4 hours
    "WARNING": 72.0,       # 72 hours (3 days)
    "WATCHLIST": 336.0,    # 14 days (336 hours)
}

SLA_LABELS = {
    "CRITICAL": "4 Hours (Proposed SLA)",
    "WARNING": "72 Hours (Proposed SLA)",
    "WATCHLIST": "14 Days (Proposed SLA)",
}

LABEL_SLA = "Proposed SLA"
LABEL_ROSTER = "Dummy Roster"

# Verification: N days of consecutive NORMAL status required to VERIFY a DONE plan
VERIFICATION_NORMAL_DAYS = 7.0

# Work Order Simulation Prefix & Status
WO_PREFIX = "WO-SIM-"
WO_STATUS = "SIMULASI"

VALID_TRANSITIONS = {
    "DRAFT": ["APPROVED", "CANCELLED", "SUPERSEDED"],
    "APPROVED": ["DISPATCHED", "CANCELLED", "SUPERSEDED"],
    "DISPATCHED": ["DONE", "CANCELLED", "SUPERSEDED"],
    "DONE": ["VERIFIED", "SUPERSEDED", "CANCELLED"],
    "VERIFIED": ["SUPERSEDED"],
    "CANCELLED": [],
    "SUPERSEDED": [],
}
