import base64
import json
import os
import sys
import time
import urllib.request

PORT = 4444
BASE_URL = "http://localhost:5173"
API_URL = "http://localhost:8000/api"
SCREENSHOT_DIR = "/home/mark/.gemini/antigravity/brain/00069874-5a3b-47fe-88e9-e5ebce397acc/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


class WebDriverClient:
    def __init__(self, port=PORT):
        self.port = port
        self.session_id = None

    def post(self, path, data=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        body = json.dumps(data or {}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def delete(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(url, method="DELETE")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def start_session(self, width=1280, height=800):
        capabilities = {
            "capabilities": {
                "alwaysMatch": {
                    "moz:firefoxOptions": {
                        "args": ["--headless", "--no-remote"]
                    }
                }
            }
        }
        res = self.post("/session", capabilities)
        self.session_id = res["value"]["sessionId"]
        print(f"Session started: {self.session_id}")
        self.set_window_size(width, height)
        return self.session_id

    def set_window_size(self, width, height):
        self.post(f"/session/{self.session_id}/window/rect", {"width": width, "height": height})
        time.sleep(0.5)

    def navigate(self, url):
        self.post(f"/session/{self.session_id}/url", {"url": url})
        time.sleep(1.5)

    def execute_script(self, script, args=[]):
        res = self.post(f"/session/{self.session_id}/execute/sync", {"script": script, "args": args})
        return res.get("value")

    def take_screenshot(self, filename):
        res = self.get(f"/session/{self.session_id}/screenshot")
        final_path = os.path.join(SCREENSHOT_DIR, filename)
        with open(final_path, "wb") as f:
            f.write(base64.b64decode(res["value"]))
        print(f"Screenshot saved: {final_path}")
        return final_path

    def close(self):
        if self.session_id:
            try:
                self.delete(f"/session/{self.session_id}")
            except Exception as e:
                print(f"Error closing session: {e}")
            self.session_id = None


def run_tests():
    wd = WebDriverClient()
    wd.start_session(1280, 800)

    try:
        print("\n--- 1. Navigating to Media Toolkit ---")
        wd.navigate(f"{BASE_URL}/#toolkit")
        time.sleep(2)

        # Check that the task table displays the task
        task_count = wd.execute_script("""
            const rows = document.querySelectorAll('table tbody tr');
            return rows.length;
        """)
        print(f"Tasks in history table: {task_count}")
        assert task_count > 0, "Expected at least 1 task in the history table"

        print("\n--- 2. Clicking Delete on task in table ---")
        wd.execute_script("""
            const deleteButtons = document.querySelectorAll('table tbody tr button[title="Delete Task"]');
            if (deleteButtons.length > 0) {
                deleteButtons[0].click();
            }
        """)
        time.sleep(0.5)

        # Verify confirmation modal opened
        modal_opened = wd.execute_script("""
            const modal = document.querySelector('div[role="dialog"][aria-labelledby="delete-toolkit-modal-title"]');
            return !!modal;
        """)
        print(f"Delete confirmation modal visible: {modal_opened}")
        assert modal_opened, "Delete confirmation modal failed to open!"

        # Verify modal contents
        modal_title = wd.execute_script("""
            const title = document.getElementById('delete-toolkit-modal-title');
            return title ? title.textContent : '';
        """)
        print(f"Modal title: '{modal_title}'")
        assert "Delete Toolkit Task" in modal_title, f"Unexpected title: {modal_title}"

        # Capture desktop modal screenshot
        wd.take_screenshot("toolkit_delete_confirm_modal_desktop.png")

        print("\n--- 3. Testing Mobile Responsive Modal View (375px) ---")
        wd.set_window_size(375, 812)
        time.sleep(0.5)

        modal_overflow = wd.execute_script("""
            return document.documentElement.scrollWidth > window.innerWidth;
        """)
        print(f"Mobile 375px modal overflow: {modal_overflow}")
        assert not modal_overflow, "Modal causes horizontal overflow on 375px mobile!"
        wd.take_screenshot("toolkit_delete_confirm_modal_mobile.png")

        # Test Cancel button
        print("\n--- 4. Testing Cancel Button ---")
        wd.execute_script("""
            const cancelBtn = Array.from(document.querySelectorAll('div[role="dialog"] button')).find(b => b.textContent && b.textContent.includes('Cancel'));
            if (cancelBtn) cancelBtn.click();
        """)
        time.sleep(0.5)

        modal_closed = wd.execute_script("""
            const modal = document.querySelector('div[role="dialog"][aria-labelledby="delete-toolkit-modal-title"]');
            return !modal;
        """)
        print(f"Modal closed after Cancel: {modal_closed}")
        assert modal_closed, "Modal should close on Cancel!"

        # Verify task is NOT deleted
        task_count_after_cancel = wd.execute_script("""
            return document.querySelectorAll('table tbody tr').length;
        """)
        print(f"Task count after Cancel: {task_count_after_cancel}")
        assert task_count_after_cancel == task_count, "Task was deleted even though user clicked Cancel!"

        print("\n--- 5. Testing Permanent Delete in Modal ---")
        # Re-open modal
        wd.execute_script("""
            const deleteButtons = document.querySelectorAll('table tbody tr button[title="Delete Task"]');
            if (deleteButtons.length > 0) {
                deleteButtons[0].click();
            }
        """)
        time.sleep(0.5)

        # Click Confirm Delete
        wd.execute_script("""
            const confirmBtn = Array.from(document.querySelectorAll('div[role="dialog"] button')).find(b => b.textContent && b.textContent.includes('Delete Task'));
            if (confirmBtn) confirmBtn.click();
        """)
        time.sleep(1.5)

        # Verify modal closed and task removed from list
        task_count_after_delete = wd.execute_script("""
            return document.querySelectorAll('table tbody tr').length;
        """)
        print(f"Task count before delete: {task_count}, after confirm delete: {task_count_after_delete}")
        assert task_count_after_delete == task_count - 1, f"Expected {task_count - 1} tasks, got {task_count_after_delete}"

        print("\n=======================================================")
        print("  TOOLKIT DELETE CONFIRMATION MODAL TESTS PASSED 100%!")
        print("=======================================================")

    finally:
        wd.close()


if __name__ == "__main__":
    run_tests()
