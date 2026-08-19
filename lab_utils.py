import requests
import logging
import time
from datetime import datetime, timedelta

# Logging is configured by main.py, which reads the log path from config.
# This module just writes to the root logger.

# How long to wait for a lab to stop reporting busy after a snapshot restore.
BUSY_POLL_SECONDS = 3
BUSY_MAX_ATTEMPTS = 60


def reset_lab(session, lab_id, base_url):
    def log(message):
        logging.info(message)
        print(message)  # Optionally print the message to console

    headers = {'Content-Type': 'application/json'}

    # Ensure no trailing slash in base_url
    if base_url.endswith('/'):
        base_url = base_url[:-1]

    try:
        log(f"Starting reset for lab {lab_id}")

        # Reset Lab Guide
        response = session.put(f"{base_url}/lab/{lab_id}/guide/reset", headers=headers)
        log(f"Reset Lab Guide response: {response.status_code}")
        response.raise_for_status()

        # Restore Snapshot
        response = session.put(f"{base_url}/lab/{lab_id}/snapshot/restore", headers=headers)
        log(f"Restore Snapshot response: {response.status_code}")
        response.raise_for_status()

        # Wait for the lab to stop reporting busy, but do not wait forever.
        for attempt in range(BUSY_MAX_ATTEMPTS):
            log(f"Checking if lab {lab_id} is busy (attempt {attempt + 1}/{BUSY_MAX_ATTEMPTS})")
            time.sleep(BUSY_POLL_SECONDS)
            response = session.get(f"{base_url}/lab/{lab_id}", headers=headers)
            log(f"Check lab status response: {response.status_code}")
            lab_status = response.json()

            if not lab_status.get('busy', True):  # Default to True to continue loop if 'busy' key is missing
                break
        else:
            timeout = BUSY_MAX_ATTEMPTS * BUSY_POLL_SECONDS
            log(f"Lab {lab_id} still busy after {timeout}s, abandoning reset")
            return

        # Start Lab
        response = session.put(f"{base_url}/lab/{lab_id}/start", headers=headers)
        log(f"Start Lab response: {response.status_code}")
        response.raise_for_status()

        # Reset User
        response = session.post(f"{base_url}/lab/{lab_id}/student", json={"student_id": ""}, headers=headers)
        log(f"Reset User response: {response.status_code}")
        response.raise_for_status()

        log(f"Lab {lab_id} reset successfully.")

    except requests.exceptions.RequestException as e:
        log(f"An error occurred while resetting lab {lab_id}: {e}")
        if e.response is not None:
            # Body is deliberately not logged; it carries per-lab credentials.
            log(f"Error response status: {e.response.status_code}")


def get_labs_in_classroom(session, classroom_id, base_url):
    headers = {'Content-Type': 'application/json'}

    # Ensure no trailing slash in base_url
    if base_url.endswith('/'):
        base_url = base_url[:-1]

    try:
        logging.info(f"Fetching labs for classroom {classroom_id}")
        response = session.get(f"{base_url}/classroom/{classroom_id}/labs", headers=headers)
        logging.info(f"Response status code: {response.status_code}")
        response.raise_for_status()
        labs = response.json()  # Assuming the response is a JSON list of labs
        logging.info(f"Received labs for classroom {classroom_id}: {labs}")
        # Extract lab id and student_last_active
        return [{'lab_id': lab['id'], 'student_last_active': lab.get('student_last_active', "0000-12-31T18:09:24-05:50")} for lab in labs]
    except requests.exceptions.RequestException as e:
        # Body is deliberately not logged; it carries per-lab credentials.
        logging.error(f"Error fetching labs for classroom {classroom_id}: {e}")
        return []


def is_inactive(last_active_time, minutes):
    try:
        logging.info(f"Checking if lab has been idle more than {minutes} minutes: last active {last_active_time}")
        last_active = datetime.strptime(last_active_time, "%Y-%m-%dT%H:%M:%S.%f%z")
        inactive = datetime.now(last_active.tzinfo) - last_active > timedelta(minutes=minutes)
        logging.info(f"Idle beyond {minutes} minutes: {inactive}")
        return inactive
    except ValueError as e:
        logging.error(f"Error parsing last active time: {last_active_time} - {e}")
        return False
