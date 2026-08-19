import tkinter as tk
from tkinter import scrolledtext
import requests
from threading import Thread, Event
import logging
import platform
import json
from requests.auth import HTTPBasicAuth
from lab_utils import reset_lab, get_labs_in_classroom, is_inactive

# Detect the operating system. The config file path is the one thing that
# cannot live in the config file, so it stays here.
os_name = platform.system()
if os_name == "Windows":
    config_file_path = "c:\\temp\\lab_config.json"
    _default_paths = {
        "log_path": "c:\\temp\\logs.txt",
        "classrooms_path": "c:\\temp\\classrooms.txt",
    }
elif os_name == "Darwin":  # macOS
    config_file_path = "/tmp/lab_config.json"
    _default_paths = {
        "log_path": "/tmp/logs.txt",
        "classrooms_path": "/tmp/classrooms.txt",
    }
else:
    raise Exception("Unsupported Operating System")

# Set default config values
DEFAULT_CONFIG = {
    "base_url": "https://lab.example.com/api",
    "idle_minutes": 15,
    "poll_seconds": 60,
    **_default_paths,
}


# Load config. Logging is not configured yet at this point, because the log
# path comes from the config, so anything worth saying is buffered and emitted
# once the logger exists.
def load_config(path):
    messages = []
    try:
        with open(path) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}, messages
    except FileNotFoundError:
        messages.append(("info", f"No config at {path}, using defaults"))
        return dict(DEFAULT_CONFIG), messages
    except (json.JSONDecodeError, OSError) as e:
        messages.append(("error", f"Could not read config at {path}: {e}"))
        return dict(DEFAULT_CONFIG), messages


CONFIG, _startup_messages = load_config(config_file_path)

# Configure logging
logging.basicConfig(filename=CONFIG["log_path"], level=logging.INFO,
                    format='%(asctime)s - %(message)s')
for _level, _message in _startup_messages:
    getattr(logging, _level)(_message)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Lab Seat Reclaimer")

        self.config = CONFIG

        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.lab_id = tk.StringVar()
        self.url = tk.StringVar(value=self.config["base_url"])

        tk.Label(root, text="Username:").grid(row=0, column=0, sticky='w')
        tk.Entry(root, textvariable=self.username).grid(row=0, column=1, padx=10, pady=5)

        tk.Label(root, text="Password:").grid(row=1, column=0, sticky='w')
        tk.Entry(root, textvariable=self.password, show='*').grid(row=1, column=1, padx=10, pady=5)

        tk.Label(root, text="URL:").grid(row=2, column=0, sticky='w')
        tk.Entry(root, textvariable=self.url).grid(row=2, column=1, padx=10, pady=5)

        tk.Label(root, text="Lab ID (manual reset):").grid(row=3, column=0, sticky='w')
        tk.Entry(root, textvariable=self.lab_id).grid(row=3, column=1, padx=10, pady=5)

        self.log_area = scrolledtext.ScrolledText(root, width=50, height=15)
        self.log_area.grid(row=4, column=0, columnspan=2, padx=10, pady=5)

        self.start_button = tk.Button(root, text="Start", command=self.start)
        self.start_button.grid(row=5, column=0, padx=10, pady=5)

        self.stop_button = tk.Button(root, text="Stop", command=self.stop)
        self.stop_button.grid(row=5, column=1, padx=10, pady=5)

        self.reset_button = tk.Button(root, text="Reset Lab", command=self.reset_lab)
        self.reset_button.grid(row=6, column=0, columnspan=2, padx=10, pady=5)

        self.stop_event = Event()
        self.thread = None

    def start(self):
        self.stop_event.clear()
        self.thread = Thread(target=self.main_loop)
        self.thread.start()
        self.add_log("Start button pressed. Main loop started.")

    def stop(self):
        self.add_log("Stop button pressed. Setting stop event.")
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)  # Add timeout to join to avoid indefinite hang
        self.add_log("Stop button pressed. Main loop stopped.")

    def reset_lab(self):
        lab_id = self.lab_id.get().strip()
        if not lab_id:
            self.add_log("No lab ID entered, nothing to reset.")
            return
        base_url = self.url.get()
        auth = (self.username.get(), self.password.get())
        session = self.create_session(auth, base_url)
        if session is None:
            self.add_log("Session creation failed. Manual reset aborted.")
            return
        self.add_log(f"Resetting lab {lab_id}")
        reset_thread = Thread(target=reset_lab, args=(session, lab_id, base_url))
        reset_thread.start()

    def authenticate(self, session, base_url, auth):
        auth_url = f"{base_url}/session"
        try:
            response = requests.post(auth_url, headers={"accept": "application/json"}, auth=HTTPBasicAuth(auth[0], auth[1]))
            if response.status_code == 200:
                session.cookies = response.cookies
                self.add_log("Authentication successful.")
                return True
            else:
                self.add_log(f"Authentication failed with status code: {response.status_code}")
                return False
        except requests.RequestException as e:
            self.add_log(f"Authentication error: {e}")
            return False

    def create_session(self, auth, base_url):
        session = requests.Session()
        session.auth = HTTPBasicAuth(auth[0], auth[1])
        session.headers.update({"accept": "application/json"})
        if not self.authenticate(session, base_url, auth):
            self.add_log("Exiting main loop due to failed authentication.")
            return None
        return session

    def main_loop(self):
        self.add_log("Entering main loop.")
        classrooms_file_path = self.config["classrooms_path"]
        while not self.stop_event.is_set():
            base_url = self.url.get()
            auth = (self.username.get(), self.password.get())
            session = self.create_session(auth, base_url)
            if session is None:
                self.add_log("Session creation failed. Exiting main loop.")
                return

            try:
                self.add_log(f"Reading classrooms from {classrooms_file_path}")
                with open(classrooms_file_path, "r") as file:
                    classrooms = [line.strip() for line in file.readlines()]

                self.add_log(f"Found classrooms: {classrooms}")
                for classroom_id in classrooms:
                    if self.stop_event.is_set():
                        self.add_log("Stop event detected. Exiting main loop.")
                        return  # Exit the main loop immediately
                    self.add_log(f"Processing classroom {classroom_id}")
                    labs = get_labs_in_classroom(session, classroom_id, base_url)
                    self.add_log(f"Found labs for classroom {classroom_id}: {labs}")
                    for lab in labs:
                        if self.stop_event.is_set():
                            self.add_log("Stop event detected. Exiting lab loop.")
                            return  # Exit the lab loop immediately
                        lab_id = lab['lab_id']
                        # Check if student_id is empty
                        lab_details_response = session.get(f"{base_url}/lab/{lab_id}")
                        lab_details = lab_details_response.json()
                        student_id = lab_details.get('student_id', '')

                        if not student_id:
                            self.add_log(f"Skipping lab {lab_id} in classroom {classroom_id} because student_id is empty")
                            continue

                        last_active_time = lab['student_last_active']
                        idle_minutes = self.config["idle_minutes"]
                        if last_active_time == "0000-12-31T18:09:24-05:50" or is_inactive(last_active_time, idle_minutes):
                            self.add_log(f"Resetting lab {lab_id} in classroom {classroom_id} (last active {last_active_time})")
                            reset_lab(session, lab_id, base_url)
                        else:
                            self.add_log(f"Skipping lab {lab_id} in classroom {classroom_id} (last active {last_active_time})")

            except Exception as e:
                self.add_log(f"Error in main loop: {e}")

            poll_seconds = self.config["poll_seconds"]
            self.add_log(f"Main loop iteration completed, waiting {poll_seconds}s before next iteration")
            # Check stop_event every second for the whole poll interval
            for i in range(poll_seconds):
                if self.stop_event.wait(1):
                    self.add_log(f"Stop event detected during wait loop at second {i}. Exiting wait loop.")
                    return  # Exit the wait loop immediately

        self.add_log("Exiting main loop.")

    def add_log(self, message):
        logging.info(message)
        self.log_area.insert(tk.END, message + '\n')
        self.log_area.yview(tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
