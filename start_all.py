"""Start all four services locally. Stop them together with Ctrl+C."""

import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SERVICES = [
    ("auth", 8001),
    ("catalog", 8002),
    ("order", 8003),
    ("gateway", 8000),
]


def main():
    processes = []
    try:
        for folder, port in SERVICES:
            command = [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--reload",
                "--port",
                str(port),
            ]
            processes.append(subprocess.Popen(command, cwd=ROOT / folder))
        print("All services started. Open http://127.0.0.1:8000/docs")
        print("Press Ctrl+C to stop all services.")
        while all(process.poll() is None for process in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping services...")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()

