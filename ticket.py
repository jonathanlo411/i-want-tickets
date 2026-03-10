import json
import math
import os
import sys
import psutil
import re
import time
import signal
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

IS_WINDOWS = sys.platform == "win32"

try:
    import screeninfo
except ImportError:
    screeninfo = None

docker_process = None

DOCKER_COMPOSE = """
version: "3"

services:
"""


def cleanup(signum=None, frame=None):
    print("\n\nStopping docker containers...")
    if docker_process and docker_process.poll() is None:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(docker_process.pid)], capture_output=True)
        else:
            docker_process.terminate()
    subprocess.run(["docker-compose", "down"], timeout=60)
    print("Done.")
    os._exit(0)


def main():
    global DOCKER_COMPOSE, docker_process

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

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

    if IS_WINDOWS:
        docker_process = subprocess.Popen(["docker-compose", "up"], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        docker_process = subprocess.Popen(["docker-compose", "up"], start_new_session=True)

    print("Waiting for containers to start...")
    time.sleep(3)

    open_browsers(config, config["browser_count"])

    print("\nPress Ctrl+C to stop containers and clean up...")
    while True:
        time.sleep(1)


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
    match = re.search(r'https?://(?:[a-zA-Z0-9-]+\.)*([a-zA-Z0-9-]+)\.[a-zA-Z0-9]+(?:/|$)', uri)
    return match.group(1) if match else "browser"


def get_screen_info():
    if screeninfo is None:
        return None
    try:
        screens = screeninfo.get_monitors()
        if not screens:
            return None
        primary = next((s for s in screens if s.is_primary), screens[0])
        print(f"Detected {len(screens)} screen(s) | Primary: {primary.width}x{primary.height}")
        return {
            "primary": {"width": primary.width, "height": primary.height, "x": primary.x, "y": primary.y},
            "all_screens": [{"width": s.width, "height": s.height, "x": s.x, "y": s.y} for s in screens],
            "total_screens": len(screens),
        }
    except Exception as e:
        print(f"Error getting screen info: {e}")
        return None


def calculate_window_positions(config, screen_info):
    orientation = config.get("screen_orientation", "auto")
    screens = screen_info["all_screens"]
    positions = []

    if orientation == "auto":
        orientation = "double" if screen_info["primary"]["height"] <= 1080 else "grid"

    if orientation == "grid":
        for si, s in enumerate(screens):
            positions += [
                {"x": s["x"],                   "y": s["y"],                    "width": s["width"] // 2, "height": s["height"] // 2},
                {"x": s["x"] + s["width"] // 2,  "y": s["y"],                    "width": s["width"] // 2, "height": s["height"] // 2},
                {"x": s["x"],                   "y": s["y"] + s["height"] // 2,  "width": s["width"] // 2, "height": s["height"] // 2},
                {"x": s["x"] + s["width"] // 2,  "y": s["y"] + s["height"] // 2, "width": s["width"] // 2, "height": s["height"] // 2},
            ]
    elif orientation == "double":
        for si, s in enumerate(screens):
            positions += [
                {"x": s["x"],                   "y": s["y"], "width": s["width"] // 2, "height": s["height"]},
                {"x": s["x"] + s["width"] // 2,  "y": s["y"], "width": s["width"] // 2, "height": s["height"]},
            ]
    elif orientation == "triple":
        for si, s in enumerate(screens):
            positions += [
                {"x": s["x"],                       "y": s["y"], "width": s["width"] // 3,      "height": s["height"]},
                {"x": s["x"] + s["width"] // 3,     "y": s["y"], "width": s["width"] // 3,      "height": s["height"]},
                {"x": s["x"] + s["width"] * 2 // 3, "y": s["y"], "width": s["width"] // 3,      "height": s["height"]},
            ]
    return positions


def open_browsers(config, browser_count: int) -> None:
    print("Setting up ChromeDriver...")
    try:
        service = Service(ChromeDriverManager().install())
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
        driver = webdriver.Chrome(service=service)
        driver.maximize_window()
        urls = [f"http://localhost:{3000 + i}" for i in range(browser_count)]
        driver.get(urls[0])
        for url in urls[1:]:
            driver.execute_script(f"window.open('{url}', '_blank');")
    else:
        print("Opening multiple browser windows...")
        positions = calculate_window_positions(config, screen_info)
        for i in range(browser_count):
            url = f"http://localhost:{3000 + i}"
            pos = positions[i % len(positions)] if positions else {"x": 100 + i*50, "y": 100 + i*50, "width": 400, "height": 400}
            print(f"Opening window {i + 1}: {url}...")
            for attempt in range(5):
                try:
                    driver = webdriver.Chrome(service=service)
                    driver.get(url)
                    driver.set_window_position(pos["x"], pos["y"])
                    driver.set_window_size(pos["width"], pos["height"])
                    print(f"  Window {i + 1} at ({pos['x']}, {pos['y']}) size {pos['width']}x{pos['height']}")
                    time.sleep(0.1)
                    break
                except Exception as e:
                    if attempt < 4:
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