import os
import json
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
FOLDER_PATH = os.path.dirname(os.path.abspath(__file__))
APPROVED_USERS_FILE = os.path.join(FOLDER_PATH, "approved_users.json")
APPROVED_USERS = set()


def load_approved_users():
    if os.path.exists(APPROVED_USERS_FILE):
        with open(APPROVED_USERS_FILE, "r") as f:
            try:
                APPROVED_USERS.update(json.load(f))
            except (json.JSONDecodeError, ValueError):
                pass


def save_approved_users():
    with open(APPROVED_USERS_FILE, "w") as f:
        json.dump(list(APPROVED_USERS), f)


load_approved_users()
