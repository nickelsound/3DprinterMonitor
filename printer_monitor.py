#!/usr/bin/env python3

"""
3D Printer Monitor

Description:
    This script periodically checks the status of a 3D printer, stores snapshots,
    analyzes them using the OpenAI API, and sends status updates (state, display_name)
    to IFTTT, but only if either state or display_name has changed. By default,
    it loads secrets and configuration from a .env file, so you can safely manage
    your credentials without committing them to version control.

Note:
    For a real production environment, ensure that you do not leak API keys
    (for example, do not commit them to a public repository).
    You can store them in environment variables loaded by python-dotenv,
    or use a similar approach (a secret manager, Docker secrets, etc.).
"""

import os
import logging
import time
import requests
import base64
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# ---------------------------------------------------------------------------
# 1. PRINTER SETUP (status and job endpoints, API key)
# ---------------------------------------------------------------------------
PRINTER_STATUS_API_URL = os.getenv("PRINTER_STATUS_API_URL", "http://printer/api/v1/status")
PRINTER_JOB_API_URL = os.getenv("PRINTER_JOB_API_URL", "http://printer/api/v1/job")
PRINTER_API_KEY = os.getenv("PRINTER_API_KEY", "")

# ---------------------------------------------------------------------------
# 2. SNAPSHOT CAPTURING (where snapshots are saved temporarily, and the URL source)
# ---------------------------------------------------------------------------
PRINTER_SNAPSHOT_URL = os.getenv("PRINTER_SNAPSHOT_URL", "http://camera/images/snapshot0.jpg")

# Comma-separated local paths in .env
LOCAL_SNAPSHOT_TEMP_PATHS_STR = os.getenv(
    "LOCAL_SNAPSHOT_TEMP_PATHS",
    "/tmp/snapshot1.jpg,/tmp/snapshot2.jpg,/tmp/snapshot3.jpg"
)
LOCAL_SNAPSHOT_TEMP_PATHS = LOCAL_SNAPSHOT_TEMP_PATHS_STR.split(",")

# ---------------------------------------------------------------------------
# 3. SNAPSHOT UPLOADING (destination endpoint, needed tokens)
# ---------------------------------------------------------------------------
SNAPSHOT_UPLOAD_API_URL = os.getenv("SNAPSHOT_UPLOAD_API_URL", "https://connect.prusa3d.com/c/snapshot")
SNAPSHOT_UPLOAD_TOKEN = os.getenv("SNAPSHOT_UPLOAD_TOKEN", "")
SNAPSHOT_UPLOAD_FINGERPRINT = os.getenv("SNAPSHOT_UPLOAD_FINGERPRINT", "")

# ---------------------------------------------------------------------------
# 4. IFTTT WEBHOOKS
# ---------------------------------------------------------------------------
IFTTT_AUTH_KEY = os.getenv("IFTTT_AUTH_KEY", "")
IFTTT_STOP_PRINTING_EVENT = os.getenv("IFTTT_STOP_PRINTING_EVENT", "should_stop_printing")
IFTTT_STATUS_CHANGED_EVENT = os.getenv("IFTTT_STATUS_CHANGED_EVENT", "status_changed")

IFTTT_STOP_PRINTING_URL = f"https://maker.ifttt.com/trigger/{IFTTT_STOP_PRINTING_EVENT}/with/key/{IFTTT_AUTH_KEY}"
IFTTT_STATUS_URL = f"https://maker.ifttt.com/trigger/{IFTTT_STATUS_CHANGED_EVENT}/json/with/key/{IFTTT_AUTH_KEY}"

# ---------------------------------------------------------------------------
# 5. OPENAI SETTINGS
# ---------------------------------------------------------------------------
OPENAI_COMPLETIONS_API_URL = os.getenv("OPENAI_COMPLETIONS_API_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# 6. MONITORING SETTINGS (interval, counters, etc.)
# ---------------------------------------------------------------------------
INTERVAL_SEC = 10

# Internal state
counter = 0
image_index = 0
previous_response = ""
confirmed_yes = False
last_sent_state: Optional[str] = None
last_sent_display_name: Optional[str] = None

# ---------------------------------------------------------------------------
# LOGGING SETTINGS
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_printer_status() -> Optional[str]:
    """
    Calls the printer's status endpoint and returns its state if available.
    :return: The printer state (e.g. "PRINTING", "IDLE", etc.) or None if not found.
    """
    headers = {"x-api-key": PRINTER_API_KEY}
    response = requests.get(PRINTER_STATUS_API_URL, headers=headers)
    response.raise_for_status()
    state = response.json().get("printer", {}).get("state")
    return state

def get_printer_job() -> Dict[str, Any]:
    """
    Calls the printer's job endpoint and returns the job information as a dict.
    :return: Dict containing the job information (e.g. state, file info).
    """
    headers = {"x-api-key": PRINTER_API_KEY}
    response = requests.get(PRINTER_JOB_API_URL, headers=headers)
    response.raise_for_status()
    return response.json()

def post_ifttt_status(state: str, display_name: Optional[str] = None) -> None:
    """
    Sends the printer state to IFTTT. If a display_name is provided, it is included.
    :param state: The printer state (e.g. "PRINTING").
    :param display_name: The print job's display name, if applicable.
    """
    payload = {"state": state}
    if display_name:
        payload["display_name"] = display_name
    
    requests.post(IFTTT_STATUS_URL, json=payload)
    logging.info(f"[IFTTT] Sent state '{state}', display_name '{display_name}'.")

def capture_snapshot(destination_path: str) -> None:
    """
    Downloads a snapshot from the printer and stores it locally.
    :param destination_path: The file path for the downloaded snapshot.
    """
    response = requests.get(PRINTER_SNAPSHOT_URL)
    response.raise_for_status()
    with open(destination_path, 'wb') as file:
        file.write(response.content)
    logging.info(f"Snapshot saved to: {destination_path}")

def upload_snapshot(file_path: str) -> None:
    """
    Uploads a local snapshot to the remote API (e.g. Prusa Connect).
    :param file_path: Path of the snapshot to be uploaded.
    """
    with open(file_path, 'rb') as file:
        image_bytes = file.read()
    headers = {
        "Token": SNAPSHOT_UPLOAD_TOKEN,
        "Fingerprint": SNAPSHOT_UPLOAD_FINGERPRINT
    }
    response = requests.put(SNAPSHOT_UPLOAD_API_URL, headers=headers, data=image_bytes)
    logging.info(f"[Snapshot] Upload response: {response.text}")

def analyze_snapshots_with_openai(
    base64_images: List[str],
    previous_resp: str,
    confirmed: bool
) -> (str, bool):
    """
    Sends snapshots for analysis to the OpenAI API, checks if printing should stop.
    :param base64_images: List of three base64-encoded snapshots.
    :param previous_resp: The last response ("YES", "NO", or "").
    :param confirmed: Whether the second "YES" response has already triggered the stop.
    :return: A tuple (new_response, confirmedYes).
    """
    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "system",
                "content": "You are a 3D printing expert."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Analyze the following images and determine if there are any issues with the 3D print, specifically looking for signs of a print "
                            "failure such as spaghetti (extruded filament mess) or if the printed object has detached from the print bed. If the object has detached, "
                            "it will not move consistently with the motion of the print bed across three consecutive photos. If all images confirm an issue, say YES, "
                            "otherwise return NO. After the answer, provide a detailed analysis of each image. "
                            "Image 1 Analysis: Spaghetti: Describe any visible spaghetti or extruded filament mess around the print area. Detached Object: Check if "
                            "the printed object shows any signs of detachment from the print bed. Describe its alignment and position. Movement Consistency: "
                            "Determine if the object moves consistently with the motion of the print bed. "
                            "Image 2 Analysis: Spaghetti: Describe any changes in the presence of spaghetti or filament mess. Detached Object: Compare the object's "
                            "position and alignment with Image 1. Note any signs of further detachment. Movement Consistency: Assess if the object's movement remains "
                            "consistent with the print bed. "
                            "Image 3 Analysis: Spaghetti: Note any continued presence or absence of spaghetti or filament mess. Detached Object: Compare the object's "
                            "position and alignment with Images 1 and 2. Confirm if there are further signs of detachment. Movement Consistency: Evaluate if the "
                            "object's movement is consistent with the print bed. If the analysis of the three images indicates that the printed object has detached "
                            "from the print bed, causing movement inconsistency, confirm a print failure and the need to stop the print."
                        )
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_images[0]}"}
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_images[1]}"}
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_images[2]}"}
                    }
                ]
            }
        ],
        "max_tokens": 4000
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    
    response = requests.post(OPENAI_COMPLETIONS_API_URL, headers=headers, json=payload)
    logging.info(f"[OpenAI] Raw response: {response.text}")
    
    response_json = response.json()
    if 'choices' not in response_json:
        logging.error("OpenAI response does not contain 'choices'.")
        return previous_resp, confirmed
    
    content = response_json['choices'][0]['message']['content']
    logging.info(f"[OpenAI] Content: {content}")
    
    if "YES" in content:
        if previous_resp == "YES":
            # Second "YES": call IFTTT stop printing
            requests.get(IFTTT_STOP_PRINTING_URL)
            logging.info("[IFTTT] Stop printing webhook triggered.")
            confirmed = True
        else:
            # First "YES": set the flag
            previous_resp = "YES"
            confirmed = False
    elif "NO" in content:
        previous_resp = "NO"
        confirmed = False
    else:
        previous_resp = ""
        confirmed = False
    
    return previous_resp, confirmed

def main() -> None:
    """
    Main function for the 3D printer monitor. Periodically checks the printer state,
    handles snapshot capturing & uploading, runs OpenAI analysis, and posts updates to IFTTT.
    """
    global counter, image_index, previous_response, confirmed_yes
    global last_sent_state, last_sent_display_name
    
    logging.info("Starting 3D printer monitor (ENV-based production version).")
    
    while True:
        try:
            logging.info("Checking printer status...")
            printer_status = get_printer_status()
            if not printer_status:
                logging.warning("Failed to retrieve printer status.")
            else:
                logging.info(f"Printer status: {printer_status}")

            # Check if the printer is printing
            if printer_status == "PRINTING":
                job_json = get_printer_job()
                job_state = job_json.get("state", "")
                display_name = job_json.get("file", {}).get("display_name", "")

                # Check if state or display_name changed
                state_or_name_changed = (
                    job_state != last_sent_state or
                    display_name != last_sent_display_name
                )

                if state_or_name_changed:
                    post_ifttt_status(job_state, display_name)
                    last_sent_state = job_state
                    last_sent_display_name = display_name
                else:
                    logging.info("Job state and display_name have not changed; skipping IFTTT.")

                # Snapshot and analysis logic
                current_image_path = LOCAL_SNAPSHOT_TEMP_PATHS[image_index]
                capture_snapshot(current_image_path)
                upload_snapshot(current_image_path)

                counter += 1
                image_index = (image_index + 1) % len(LOCAL_SNAPSHOT_TEMP_PATHS)

                # Every 20th snapshot triggers the AI analysis
                if counter == 20:
                    counter = 0
                    logging.info("Processing every 20th photo for further analysis...")

                    base64_images = []
                    for path in LOCAL_SNAPSHOT_TEMP_PATHS:
                        with open(path, 'rb') as file:
                            base64_image = base64.b64encode(file.read()).decode('utf-8')
                            base64_images.append(base64_image)

                    previous_response, confirmed_yes = analyze_snapshots_with_openai(
                        base64_images,
                        previous_response,
                        confirmed_yes
                    )

            else:
                # Printer is not printing → call IFTTT only if the state changed
                if printer_status != last_sent_state:
                    post_ifttt_status(printer_status, None)
                    last_sent_state = printer_status
                    last_sent_display_name = None
                else:
                    logging.info("Printer status unchanged and not PRINTING; no IFTTT call.")

            logging.info(f"Waiting {INTERVAL_SEC} seconds before the next check...")
            time.sleep(INTERVAL_SEC)

        except Exception as e:
            logging.error(f"Error occurred: {e}", exc_info=True)
            logging.info(f"Waiting {INTERVAL_SEC} seconds before the next check...")
            time.sleep(INTERVAL_SEC)

if __name__ == "__main__":
    main()