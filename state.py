"""
State management — JSON persistence
"""
import json
import os

from config import STATE_FILE

DEFAULT_STATE = {
    "balance": 0.0,
    "position": None,
    "trades": [],
    "is_active": True,
    "last_scan_date": None,
    "start_balance": None,
    "peak_balance": 0.0,
    "mexc_api_key": None,
    "mexc_secret_key": None,
}

def load():
    try:
        with open(STATE_FILE) as f:
            st = json.load(f)
            for k in DEFAULT_STATE:
                if k not in st:
                    st[k] = DEFAULT_STATE[k]
            return st
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_STATE)

def save(state):
    os.makedirs(os.path.dirname(STATE_FILE) or '.', exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def reset():
    st = dict(DEFAULT_STATE)
    save(st)
    return st
