"""Start four local services, with no model calls. Ctrl-C stops all children."""

import os
import subprocess
import sys
import time

from auditor.paths import ROOT


def main():
    children = []
    try:
        for i, role in enumerate(["intake", "policy", "audit"]):
            port = 8211 + i
            env = dict(os.environ, AGENT_ROLE=role, AGENT_URL=f"http://127.0.0.1:{port}/")
            children.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "auditor.services.app:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                    ],
                    cwd=ROOT,
                    env=env,
                )
            )
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "auditor.api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5190",
                ],
                cwd=ROOT,
            )
        )
        print("Reviewer: http://localhost:5190 (offline fixture replay)", flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in children:
            if p.poll() is None:
                p.terminate()
        for p in children:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()


if __name__ == "__main__":
    main()
