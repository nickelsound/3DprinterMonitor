# MK4S 3D Printer Monitor

This project provides a Python-based solution for continuously monitoring a MK4/MK4S 3D printer's status and automatically activating enclosure ventilation for PLA and PETG. It sends printer state changes and job metadata to IFTTT, ensures snapshots are uploaded to a remote API, and leverages OpenAI for snapshot image analysis, detecting potential print failures.

Below is a detailed explanation of what the script does and how to configure it.
The hardware setup is described [here](https://www.printables.com/model/1014150-complete-solution-for-mk4s-mmu3-with-enclosure-and).

---

## Features

1. **Periodic Printer Status Checks**  
   • Monitors the 3D printer's current state, such as PRINTING, IDLE, etc.  
   • Uses the printer’s status API endpoint to retrieve real-time state.

2. **IFTTT Triggering**  
   • Whenever the printer’s state changes, or the active print job (display_name) changes, the script sends a notification to an IFTTT event.  
   • The script can trigger a separate IFTTT event if a print failure is detected (a second “YES” response), prompting the user (or potentially an automation) to stop the printer.

3. **Snapshot Capturing & Uploading**  
   • Periodically downloads snapshots from the printer via a provided URL.  
   • Stores these snapshots locally and uploads them to a specified remote endpoint (e.g., Prusa Connect).

4. **OpenAI Image Analysis**  
   • After every 20 snapshots (configurable), the script gathers the last three snapshots and sends them to OpenAI’s API.  
   • Using textual instructions, GPT model tries to detect 3D print failures such as "spaghetti" or detachment from the print bed.  
   • Returns “YES” or “NO” based on the confidence that something is wrong.

5. **Environment-Based Configuration**  
   • All sensitive keys and tokens (printer API, OpenAI key, IFTTT keys, etc.) are loaded from a .env file.  
   • This facilitates secure handling of secrets and easy environment-specific setups.

6. **Logging & Error Handling**  
   • Logs all actions and responses, including errors, with clear messaging.  
   • Retries on exceptions, preventing crashes from transient network or API issues.

---

## Prerequisites

• Python 3.12+  
• A configured 3D printer API (e.g. Prusa, or any printer that provides a JSON-based status & job endpoint).  
• python-dotenv (used for managing environment variables).  
• requests (used for HTTP calls).

---

## Installation
### Docker
1. user Dockerfile

### Custom
1. Clone or download this repository.  
2. Create (or copy) a .env file in the same directory as the main Python script (see the example below).  
3. In your terminal:  
   » pip install -r requirements.txt  

The script will then be ready to run.

---

## Example .env

Below is an example .env that includes all required environment variables. Adjust them for your setup:

```bash
PRINTER_STATUS_API_URL="http://printer/api/v1/status"
PRINTER_JOB_API_URL="http://printer/api/v1/job"
PRINTER_API_KEY=""

PRINTER_SNAPSHOT_URL="http://camera/images/snapshot0.jpg"
LOCAL_SNAPSHOT_TEMP_PATHS="/tmp/snapshot1.jpg,/tmp/snapshot2.jpg,/tmp/snapshot3.jpg"

SNAPSHOT_UPLOAD_API_URL="https://connect.prusa3d.com/c/snapshot"
SNAPSHOT_UPLOAD_TOKEN=""
SNAPSHOT_UPLOAD_FINGERPRINT=""

IFTTT_AUTH_KEY=""
IFTTT_STOP_PRINTING_EVENT="should_stop_printing"
IFTTT_STATUS_CHANGED_EVENT="3dprinter_status_changed"

OPENAI_COMPLETIONS_API_URL="https://api.openai.com/v1/chat/completions"
OPENAI_API_KEY=""
```

Notes:  
• The environment variable names are referenced in the code.  
• You can rename them if you wish, but you must update the code accordingly.  
• Do not commit your .env to a public repository (use .gitignore).

---

## Usage

1. Make sure your .env file is in place and your environment variables are set properly.  
2. Run the Python script:  
   » python monitor.py  

3. The script will log information about the printer status, snapshots, and any API call responses.  
4. If your IFTTT events are configured properly, you should receive notifications whenever the print job or state changes.

---

## How It Works

1. **Printer Status Check:**  
   • Every 10 seconds (configurable in INTERVAL_SEC), the script calls the printer’s status endpoint to check if the state is PRINTING or something else.

2. **Job API (If PRINTING):**  
   • If the printer is printing, it retrieves job details (like the display_name).  
   • Compares them with the last known job to see if anything changed. When different, it triggers an IFTTT webhook (the "status changed" event).

3. **Snapshot Logic:**  
   • The script downloads snapshots from PRINTER_SNAPSHOT_URL, saves them locally, and uploads them to SNAPSHOT_UPLOAD_API_URL.  
   • This cycle repeats each interval.

4. **OpenAI Analysis:**  
   • Every 20 cycles (200 seconds in default config), the script reads the last three snapshots, encodes them in Base64, and sends them to OpenAI.  
   • If OpenAI’s response indicates a likely print failure (“YES”), the script toggles a flag. If the flag is set twice in a row, it calls the “stop printing” IFTTT event.

5. **IFTTT Webhooks:**  
   • "3dprinter_status_changed" event → sends "state" and optionally "display_name".  
   • "should_stop_printing" event → triggered when a second “YES” response is confirmed by OpenAI (scribe: effectively a print failure).

---

## Customization

• **Interval:** Modify INTERVAL_SEC to manage how often status and snapshots are polled.  
• **Snapshot Frequency:** The script triggers snapshot capturing on every iteration. The detailed OpenAI analysis is performed every 20th snapshot. Adjust “if counter == 20” to match your preference.  
• **OpenAI Model:** The script uses "gpt-4o" as the model name. Change this if needed according to your available models or preferences.  
• **Logging:** The default logging level is INFO. You can adjust to DEBUG for more verbose output or to WARNING/ERROR for quieter logs.

---

## Troubleshooting

• **No IFTTT Triggers:**  
  1. Confirm that your environment variables for IFTTT_AUTH_KEY, IFTTT_STOP_PRINTING_EVENT, and IFTTT_STATUS_CHANGED_EVENT are correct.  
  2. Make sure the URL is formatted properly ("/with/key/..." – not "?with/key=" or "=with/key").  
  3. Check your IFTTT applets to ensure they’re listening on the correct event names.

• **Incomplete Snapshots:**  
  1. Make sure the printer’s snapshot URL is correct.  
  2. Verify local permissions to write snapshots to /tmp or your specified directory.

• **OpenAI Errors:**  
  1. Check that you have a valid OPENAI_API_KEY with the right model access.  
  2. Inspect logs to see if you’re hitting rate limits or have incorrect credentials.

• **Env Variables Not Found:**  
  1. Make sure python-dotenv is installed and .env is in the same directory as your script.  
  2. Validate the .env syntax (no trailing spaces or quotes mismatch).

---

## Contributing

Feel free to open issues or submit pull requests! Report any bugs, ideas for improvements, or suggestions on how to better handle print-failure detection.

---

## License

This project is provided under an open-source license (MIT, GPL, or whichever you choose). You can freely modify and distribute this code. Be mindful of your own environment variables and tokens — never commit private data to a public repository.

---
