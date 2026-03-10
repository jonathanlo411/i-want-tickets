import atexit
import json
import math
import os
import sys
import psutil
import re
import time
import signal
import subprocess
import threading
from subprocess import Popen
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

IS_WINDOWS = sys.platform == "win32"

try:
    import screeninfo
except ImportError:
    screeninfo = None

# Global state
all_drivers = []
chrome_pids = []
docker_process = None
chrome_service = None
_cleanup_called = False

DOCKER_COMPOSE = """
version: "3"

services:
"""


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def _kill_docker_process():
    """Kill the docker-compose UP process without touching the containers."""
    global docker_process
    if not docker_process or docker_process.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            # On Windows, terminate() sends CTRL_C_EVENT which the console
            # forwards to ALL attached processes — exactly the problem we're
            # trying to avoid.  taskkill /F /T kills the process tree directly.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(docker_process.pid)],
                capture_output=True,
            )
        else:
            docker_process.terminate()
        docker_process.wait(timeout=5)
    except Exception:
        try:
            docker_process.kill()
        except Exception:
            pass


def cleanup():
    global _cleanup_called
    if _cleanup_called:
        return
    _cleanup_called = True

    print("\n\nShutting down gracefully...")

    print(f"Closing {len(all_drivers)} browser instance(s)...")
    for driver in all_drivers:
        try:
            driver.quit()
        except Exception:
            pass

    # Stop docker containers.
    _kill_docker_process()
    print("Stopping docker containers...")
    try:
        subprocess.run(["docker-compose", "down"], timeout=60)
        print("  Docker containers stopped.")
    except Exception as e:
        print(f"  docker-compose down failed: {e}")

    print("Cleanup complete.")


def _signal_handler(signum, frame):
    cleanup()
    os._exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global DOCKER_COMPOSE, docker_process

    # Register cleanup on both signal and normal exit so Ctrl+C in any shell
    # (PowerShell, Git Bash, cmd) is covered.
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    atexit.register(cleanup)  # fallback for KeyboardInterrupt that bypasses signal handler

    config = load_config()

    if config["browser_count"] == 0:
        available_ram_gb = psutil.virtual_memory().available / (1024 ** 3)
        config["browser_count"] = math.floor(available_ram_gb / 2)

    for i in range(config["browser_count"]):
        domain_name = extract_domain_name(config["browser_uri"])
        name = f"{domain_name}-{i + 1}"
        port = 3000 + i
        DOCKER_COMPOSE += create_web_tempalte(name, port, config["browser_uri"])

    with open("docker-compose.yaml", "w") as f:
        f.write(DOCKER_COMPOSE)

    # Launch docker-compose in a new process GROUP so the Windows console
    # does not broadcast Ctrl+C to it.  On Windows this is done via
    # CREATE_NEW_PROCESS_GROUP; on Unix, start_new_session=True is equivalent.
    if IS_WINDOWS:
        docker_process = Popen(
            ["docker-compose", "up"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        docker_process = Popen(
            ["docker-compose", "up"],
            start_new_session=True,
        )

    print("Waiting for containers to start...")
    time.sleep(3)

    open_browsers(config, config["browser_count"])

    print("\nPress Ctrl+C to stop and clean up...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass  # atexit.register(cleanup) will fire on exit


# ---------------------------------------------------------------------------
# Config / helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "browser_uri": "https://github.com/jonathanlo411/",
            "browser_count": 0,
            "browser_mode": "windows",
            "screen_orientation": "grid",
        }


def extract_domain_name(uri: str) -> str:
    match = re.search(
        r'https?://(?:[a-zA-Z0-9-]+\.)*([a-zA-Z0-9-]+)\.[a-zA-Z0-9]+(?:/|$)', uri
    )
    return match.group(1) if match else "browser"


def get_screen_info():
    if screeninfo is None:
        print("screeninfo not installed. Install with: pip install screeninfo")
        return None
    try:
        screens = screeninfo.get_monitors()
        if not screens:
            return None
        primary = next((s for s in screens if s.is_primary), screens[0])
        print(f"Detected {len(screens)} screen(s) | Primary: {primary.width}x{primary.height}")
        return {
            "primary": {"width": primary.width, "height": primary.height,
                        "x": primary.x, "y": primary.y},
            "all_screens": [
                {"width": s.width, "height": s.height, "x": s.x, "y": s.y}
                for s in screens
            ],
            "total_screens": len(screens),
        }
    except Exception as e:
        print(f"Error getting screen info: {e}")
        return None


def calculate_window_positions(config, screen_info, browser_count):
    orientation = config.get("screen_orientation", "auto")
    primary_height = screen_info["primary"]["height"]
    screens = screen_info["all_screens"]
    positions = []

    if orientation == "auto":
        orientation = "double" if primary_height <= 1080 else "grid"

    if orientation == "grid":
        for si, screen in enumerate(screens):
            positions += [
                {"x": screen["x"],                        "y": screen["y"],
                 "width": screen["width"] // 2,           "height": screen["height"] // 2, "screen": si},
                {"x": screen["x"] + screen["width"] // 2, "y": screen["y"],
                 "width": screen["width"] // 2,           "height": screen["height"] // 2, "screen": si},
                {"x": screen["x"],                        "y": screen["y"] + screen["height"] // 2,
                 "width": screen["width"] // 2,           "height": screen["height"] // 2, "screen": si},
                {"x": screen["x"] + screen["width"] // 2, "y": screen["y"] + screen["height"] // 2,
                 "width": screen["width"] // 2,           "height": screen["height"] // 2, "screen": si},
            ]
    elif orientation == "double":
        for si, screen in enumerate(screens):
            positions += [
                {"x": screen["x"],                        "y": screen["y"],
                 "width": screen["width"] // 2,           "height": screen["height"], "screen": si},
                {"x": screen["x"] + screen["width"] // 2, "y": screen["y"],
                 "width": screen["width"] // 2,           "height": screen["height"], "screen": si},
            ]
    elif orientation == "triple":
        for si, screen in enumerate(screens):
            positions += [
                {"x": screen["x"],                             "y": screen["y"],
                 "width": screen["width"] // 3,                "height": screen["height"], "screen": si},
                {"x": screen["x"] + screen["width"] // 3,     "y": screen["y"],
                 "width": screen["width"] // 3,                "height": screen["height"], "screen": si},
                {"x": screen["x"] + screen["width"] * 2 // 3, "y": screen["y"],
                 "width": screen["width"] // 3,                "height": screen["height"], "screen": si},
            ]
    return positions


# ---------------------------------------------------------------------------
# Browser helpers
# ---------------------------------------------------------------------------

def open_browsers(config, browser_count: int) -> None:
    global chrome_service
    print("Setting up ChromeDriver...")
    try:
        service = Service(ChromeDriverManager().install())
        chrome_service = service
    except Exception as e:
        print(f"Error installing ChromeDriver: {e}")
        return

    screen_info = get_screen_info() or {
        "primary": {"width": 1920, "height": 1080, "x": 0, "y": 0},
        "all_screens": [{"width": 1920, "height": 1080, "x": 0, "y": 0}],
        "total_screens": 1,
    }

    if config.get("browser_mode") == "tabs":
        print("Opening single browser with tabs...")
        open_browser_with_tabs(service, browser_count)
    else:
        print("Opening multiple browser windows...")
        open_browser_windows(service, browser_count, config, screen_info)


def open_browser_with_tabs(service, browser_count):
    global all_drivers
    try:
        driver = webdriver.Chrome(service=service)
        driver.maximize_window()
        all_drivers.append(driver)
        try:
            cd = psutil.Process(driver.service.process.pid)
            chrome_pids.extend([c.pid for c in cd.children(recursive=True)])
        except Exception:
            pass
        urls = [f"http://localhost:{3000 + i}" for i in range(browser_count)]
        for attempt in range(5):
            try:
                driver.get(urls[0])
                print(f"Opened tab 1: {urls[0]}")
                break
            except Exception:
                if attempt == 4:
                    print("Failed to open first tab.")
                    return
                time.sleep(2)
        for i, url in enumerate(urls[1:], start=2):
            try:
                driver.execute_script(f"window.open('{url}', '_blank');")
                print(f"Opened tab {i}: {url}")
                time.sleep(0.5)
            except Exception as e:
                print(f"Error opening tab {i}: {e}")
    except Exception as e:
        print(f"Error opening browser with tabs: {e}")


def open_browser_windows(service, browser_count, config, screen_info):
    global all_drivers
    positions = calculate_window_positions(config, screen_info, browser_count)

    for i in range(browser_count):
        url = f"http://localhost:{3000 + i}"
        print(f"Opening window {i + 1}: {url}...")
        pos = positions[i % len(positions)] if positions else {
            "x": 100 + i * 50, "y": 100 + i * 50, "width": 400, "height": 400
        }
        for attempt in range(5):
            try:
                driver = webdriver.Chrome(service=service)
                driver.get(url)
                driver.set_window_position(pos["x"], pos["y"])
                driver.set_window_size(pos["width"], pos["height"])
                all_drivers.append(driver)
                try:
                    cd = psutil.Process(driver.service.process.pid)
                    chrome_pids.extend([c.pid for c in cd.children(recursive=True)])
                except Exception:
                    pass
                print(
                    f"  Window {i + 1} at ({pos['x']}, {pos['y']}) "
                    f"size {pos['width']}x{pos['height']}"
                )
                time.sleep(0.1)
                break
            except Exception as e:
                if attempt < 4:
                    print(f"  Attempt {attempt + 1} failed, retrying...")
                    time.sleep(2)
                else:
                    print(f"  Failed to open window {i + 1}: {e}")


def create_web_tempalte(name: str, port: int, uri: str):
    slug = name.replace(" ", "-").lower()
    return f"""  {slug}:
    image: lscr.io/linuxserver/chromium:latest
    container_name: {name}
    shm_size: "2gb"
    ports:
      - "{port}:3000"
    environment:
      - PUID=1000
      - PGID=1000
      - CHROME_CLI={uri}
    volumes:
      - ./data/{slug}:/config

"""


if __name__ == "__main__":
    main()