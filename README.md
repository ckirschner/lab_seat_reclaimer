# Lab Seat Reclaimer

Automatically reclaims idle seats in a hosted lab environment.

## The problem

A shared lab platform hands out a fixed number of seats per classroom. People
open a lab, work for ten minutes, close the tab, and never release it. The seat
stays checked out. From the platform's perspective everything is fine; from the
next person's perspective the classroom is full and there is nothing to use.

Manually reclaiming those seats does not scale. It also means someone has to be
watching, which is exactly the kind of work that should not require a person.

This tool watches for it instead. It polls each classroom on an interval, finds
seats assigned to a user who has gone idle past a threshold, and puts them back
into the pool.

## What it does

For each classroom in the watch list, on every poll:

1. Fetch the labs in the classroom.
2. Skip any lab with no assigned user — nothing to reclaim.
3. Compare `student_last_active` against the idle threshold. The platform
   returns a zero-value timestamp for seats that were claimed but never touched;
   those are treated as idle.
4. For each idle lab, run the reset sequence: reset the guide, restore the
   snapshot, wait for the platform to report the lab is no longer busy, start
   the lab, then clear the assigned user.

The reset order matters. Clearing the user before the snapshot restore
completes leaves the next person on a dirty machine.

## Configuration

Copy `lab_config.example.json` to the config path for your OS and edit it:

| OS      | Config path                  |
|---------|------------------------------|
| Windows | `C:\temp\lab_config.json`    |
| macOS   | `/tmp/lab_config.json`       |

That one path is hardcoded, because it is where the tool looks to find
everything else. Every other path is a config value.

```json
{
  "base_url": "https://lab.example.com/api",
  "idle_minutes": 15,
  "poll_seconds": 60,
  "log_path": "/tmp/logs.txt",
  "classrooms_path": "/tmp/classrooms.txt"
}
```

| Key               | What it does                                          |
|-------------------|-------------------------------------------------------|
| `base_url`        | API root; also the value prefilled in the URL field   |
| `idle_minutes`    | How long a seat sits idle before it is reclaimed      |
| `poll_seconds`    | Wait between passes over the classroom list           |
| `log_path`        | Where the log file is written                         |
| `classrooms_path` | File listing classroom IDs to watch, one per line     |

Any key you omit falls back to a built-in default, and the path defaults differ
per OS. A missing config file is not an error.

Credentials are entered in the UI at runtime and are not written to disk.

## Running it

```
pip install -r requirements.txt
python main.py
```

Enter your username and password, confirm the URL, and press Start. The log
pane shows what it is doing. Stop is checked once per second during the poll
interval, so it exits promptly rather than after the full wait.

To reset a single lab by hand, put its ID in the Lab ID field and press
Reset Lab.

## A note on logging

Lab records returned by this kind of platform carry per-lab credentials —
interface passwords, tokens, and jumpbox passwords. This tool deliberately logs
status codes and lab IDs only. It does not log response bodies, because doing so
writes those credentials to a plaintext file on every poll.

If you fork this and add response logging for debugging, redact the credential
fields first.

## Requirements

Python 3.8+, `requests`, and Tk (bundled with most Python installs; on Linux you
may need to install `python3-tk` separately).

## Limitations

- Windows and macOS only, because the config and log paths are hardcoded per OS.
- Single-threaded reset. A classroom with many idle labs works through them one
  at a time.
- The idle check assumes the platform reports `student_last_active` as an
  ISO-8601 timestamp with microseconds and an offset.
- A lab that never stops reporting busy is abandoned after three minutes rather
  than blocking the reset thread indefinitely.