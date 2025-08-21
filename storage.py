# storage.py
import os
import json

BASE_PATH = "assets/preloads"

def _council_path(council_key: str) -> str:
    """
    Build the folder path for a given council key.
    """
    return os.path.join(BASE_PATH, council_key)


def _policies_file(council_key: str) -> str:
    """
    Return path to the demo_policies.json file for the council.
    """
    return os.path.join(_council_path(council_key), "demo_policies.json")


def save_policy(council_key: str, policy: dict):
    """
    Append a new policy dict to the council’s demo_policies.json.
    Creates the file if it doesn’t exist.
    """
    os.makedirs(_council_path(council_key), exist_ok=True)
    file_path = _policies_file(council_key)

    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            try:
                data = json.load(f)
            except:
                data = []
    else:
        data = []

    data.append(policy)

    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


def load_policies(council_key: str):
    """
    Load all stored policies for the council.
    Returns empty list if none exist.
    """
    file_path = _policies_file(council_key)
    if not os.path.exists(file_path):
        return []

    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except:
        return []


def clear_policies(council_key: str):
    """
    Delete demo_policies.json for a fresh start.
    """
    file_path = _policies_file(council_key)
    if os.path.exists(file_path):
        os.remove(file_path)
        return True
    return False
