import base64
import json
import os
import time
import urllib.request
from pathlib import Path

SCREENSHOTS_DIR = Path("/home/mark/.gemini/antigravity/brain/00069874-5a3b-47fe-88e9-e5ebce397acc/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


class GeckoClient:
    def __init__(self, base_url="http://127.0.0.1:4444"):
        self.base_url = base_url
        self.session_id = None

    def post(self, endpoint, data):
        url = f"{self.base_url}{endpoint}"
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get(self, endpoint):
        url = f"{self.base_url}{endpoint}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def delete(self, endpoint):
        url = f"{self.base_url}{endpoint}"
        req = urllib.request.Request(url, method="DELETE")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def start(self, width=1440, height=900):
        caps = {
            "capabilities": {
                "alwaysMatch": {
                    "moz:firefoxOptions": {
                        "args": [
                            "--headless",
                            "--no-remote",
                            f"--width={width}",
                            f"--height={height}",
                        ]
                    }
                }
            }
        }
        res = self.post("/session", caps)
        self.session_id = res["value"]["sessionId"]
        print(f"WebDriver Session started: {self.session_id}")

    def navigate(self, url, wait_seconds=3):
        print(f"Navigating to {url}...")
        self.post(f"/session/{self.session_id}/url", {"url": url})
        time.sleep(wait_seconds)

    def execute_script(self, script, args=None):
        return self.post(
            f"/session/{self.session_id}/execute/sync",
            {"script": script, "args": args or []},
        )

    def screenshot(self, filename):
        res = self.get(f"/session/{self.session_id}/screenshot")
        png_data = base64.b64decode(res["value"])
        out_path = SCREENSHOTS_DIR / filename
        with open(out_path, "wb") as f:
            f.write(png_data)
        print(f"Saved screenshot: {out_path} ({len(png_data)} bytes)")
        return out_path

    def stop(self):
        if self.session_id:
            try:
                self.delete(f"/session/{self.session_id}")
                print(f"Session {self.session_id} closed.")
            except Exception as e:
                print(f"Error closing session: {e}")
            self.session_id = None


def main():
    client = GeckoClient()
    try:
        client.start(width=1440, height=960)

        # 1. Dashboard
        client.navigate("http://localhost:5173/#dashboard", wait_seconds=3)
        client.screenshot("v2_3_01_dashboard.png")

        # 2. Projects List showing bamboo-v2-3
        client.navigate("http://localhost:5173/#projects", wait_seconds=3)
        client.screenshot("v2_3_02_projects_list.png")

        # 3. Project Studio - Transcript Tab (bamboo-v2-3)
        client.navigate("http://localhost:5173/#project/bamboo-v2-3", wait_seconds=3)
        client.execute_script("""
            const btns = Array.from(document.querySelectorAll('button'));
            const tabBtn = btns.find(b => b.textContent && b.textContent.includes('Transcript'));
            if (tabBtn) tabBtn.click();
        """)
        time.sleep(2)
        client.screenshot("v2_3_03_transcript_tab.png")

        # 4. Project Studio - Translation Tab
        client.execute_script("""
            const btns = Array.from(document.querySelectorAll('button'));
            const tabBtn = btns.find(b => b.textContent && b.textContent.includes('Translation'));
            if (tabBtn) tabBtn.click();
        """)
        time.sleep(2)
        client.screenshot("v2_3_04_translation_tab.png")

        # 5. Project Studio - Voice Tab
        client.execute_script("""
            const btns = Array.from(document.querySelectorAll('button'));
            const tabBtn = btns.find(b => b.textContent && b.textContent.includes('Voice'));
            if (tabBtn) tabBtn.click();
        """)
        time.sleep(2)
        client.screenshot("v2_3_05_voice_tab.png")

        # 6. Project Studio - Export Tab
        client.execute_script("""
            const btns = Array.from(document.querySelectorAll('button'));
            const tabBtn = btns.find(b => b.textContent && b.textContent.includes('Export'));
            if (tabBtn) tabBtn.click();
        """)
        time.sleep(2)
        client.screenshot("v2_3_06_export_tab_ready.png")

        print("\nAll 6 v2.3 screenshots successfully captured!")

    finally:
        client.stop()


if __name__ == "__main__":
    main()
