import os
import time
import json
import requests

# Production
BASE_URL = "https://mars.keysight.com"

# UAT (uncomment if needed)
# BASE_URL = "https://uat-mars-sgp.keysight.com"

TIMEOUT = 30

# ----------------------------------------------------------------------
# 0) True  = show and save EVERY field MARS returns.
#    False = show and save only the fields listed in FIELDS below.
# ----------------------------------------------------------------------
ALL_FIELDS = True

FIELDS = [
    "Equipment_ID",
    "Model_No",
    "Serial_No",
    "Model_Description",
    "Equipment_Status",
    "Calibration_Status",
    "Cal_Due_Date_Local_DateOnly",
    "Placement_ID",
    "Placement_Description",
]

# ----------------------------------------------------------------------
# 2) Where to save the files (same folder as this script).
# ----------------------------------------------------------------------
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


class MarsClient:
    def __init__(self, user, password, base_url=BASE_URL):
        self.user = user
        self.password = password
        self.base_url = base_url.rstrip("/")

        self.access_token = None
        self.refresh_token = None
        self.expires_in = 3600
        self.issued_at = 0

    def login(self):
        print("Logging in...")

        response = requests.post(
            f"{self.base_url}/webapi/auth/token",
            headers={
                "USER": self.user,
                "PASSWORD": self.password
            },
            timeout=TIMEOUT
        )

        response.raise_for_status()

        data = response.json()["ret"]

        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.expires_in = data.get("expires_in", 3600)
        self.issued_at = time.time()

        print("Login successful")

    def refresh(self):
        print("Refreshing token...")

        response = requests.post(
            f"{self.base_url}/webapi/auth/refresh",
            headers={
                "USER": self.user,
                "REFRESH-TOKEN": self.refresh_token
            },
            timeout=TIMEOUT
        )

        if response.status_code == 401:
            print("Refresh token expired. Re-authenticating...")
            self.login()
            return

        response.raise_for_status()

        data = response.json()["ret"]

        self.access_token = data["access_token"]
        self.expires_in = data.get("expires_in", 3600)
        self.issued_at = time.time()

        print("Token refreshed")

    def ensure_token(self):
        if self.access_token is None:
            self.login()

        elif time.time() - self.issued_at >= 0.8 * self.expires_in:
            self.refresh()

    def get(self, endpoint, **params):
        self.ensure_token()

        response = requests.get(
            f"{self.base_url}/webapi/{endpoint}",
            headers={
                "Authorization": f"Bearer {self.access_token}"
            },
            params=params,
            timeout=TIMEOUT
        )

        if response.status_code == 401:
            print("Access token expired. Retrying...")

            self.refresh()

            response = requests.get(
                f"{self.base_url}/webapi/{endpoint}",
                headers={
                    "Authorization": f"Bearer {self.access_token}"
                },
                params=params,
                timeout=TIMEOUT
            )

        response.raise_for_status()

        return response.json()

    def get_equipment(self, equipment_id):
        return self.get(
            "ExtractEquipmentList",
            equipment_id=equipment_id
        )


def pick_fields(record, fields):
    """Return the record with only the chosen fields.

    If ALL_FIELDS is True (or fields is empty/None), return the whole record.
    record.get(name) gives None (instead of crashing) if a field is missing.
    """
    if ALL_FIELDS or not fields:
        return record
    return {name: record.get(name) for name in fields}


def save_json(records, filename):
    """Save a list of dicts as a pretty-printed .json file."""
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)
    return path


def save_txt(records, filename):
    """Save a list of dicts as a human-readable .txt file."""
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            for name, value in record.items():
                f.write(f"{name}: {value}\n")
            f.write("\n" + "-" * 60 + "\n\n")
    return path


if __name__ == "__main__":

    client = MarsClient(
        os.environ["MARS_USER"],
        os.environ["MARS_PASSWORD"]
    )

    equipment_ids = [
        "PN010064",
        "PN010075",
    ]

    all_records = []   # every picked record is collected here, then saved

    for equipment_id in equipment_ids:

        print(f"\n{'=' * 60}")
        print(f"Equipment ID: {equipment_id}")
        print(f"{'=' * 60}")

        try:
            result = client.get_equipment(equipment_id)

            # result["ret"] is a LIST of records (one per matching equipment)
            for record in result["ret"]:
                picked = pick_fields(record, FIELDS)
                all_records.append(picked)

                for name, value in picked.items():
                    print(f"{name:32} {value}")

        except Exception as e:
            print(f"Error: {e}")

    if all_records:
        json_path = save_json(all_records, "equipment_result.json")
        txt_path = save_txt(all_records, "equipment_result.txt")
        print(f"\nSaved: {json_path}")
        print(f"Saved: {txt_path}")