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

    def start_session(self, width=1440, height=1000):
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
    wd.start_session(1440, 900)

    try:
        print("\n--- 1. Testing Desktop Expanded Sidebar (1440px) ---")
        wd.navigate(f"{BASE_URL}/#dashboard")
        time.sleep(1.5)

        # Ensure sidebar is expanded by clearing localStorage or clicking expand if collapsed
        wd.execute_script("localStorage.setItem('khmerdub_sidebar_collapsed', 'false'); window.location.reload();")
        time.sleep(2)

        # Check sidebar width > 200px
        sidebar_w = wd.execute_script("""
            const aside = document.querySelector('aside[aria-label="Desktop Navigation"]');
            return aside ? aside.getBoundingClientRect().width : 0;
        """)
        print(f"Desktop expanded sidebar width: {sidebar_w}px")
        assert sidebar_w >= 200, f"Expected expanded sidebar >= 200px, got {sidebar_w}"
        wd.take_screenshot("responsive_01_desktop_expanded_sidebar.png")

        print("\n--- 2. Testing Desktop Collapsed Sidebar Toggle & Persistence ---")
        # Click collapse button
        wd.execute_script("""
            const btn = document.querySelector('button[aria-label="Collapse sidebar"]');
            if (btn) btn.click();
        """)
        time.sleep(0.5)

        collapsed_w = wd.execute_script("""
            const aside = document.querySelector('aside[aria-label="Desktop Navigation"]');
            return aside ? aside.getBoundingClientRect().width : 0;
        """)
        print(f"Desktop collapsed sidebar width: {collapsed_w}px")
        assert 50 <= collapsed_w <= 90, f"Expected collapsed sidebar width ~64px, got {collapsed_w}"

        # Verify localStorage persistence
        saved_pref = wd.execute_script("return localStorage.getItem('khmerdub_sidebar_collapsed')")
        print(f"localStorage preference: {saved_pref}")
        assert saved_pref == "true", f"Expected localStorage 'true', got {saved_pref}"

        wd.take_screenshot("responsive_02_desktop_collapsed_sidebar.png")

        print("\n--- 3. Testing Tablet Layout (768px & 1024px) ---")
        wd.set_window_size(768, 1024)
        time.sleep(1)

        # Check horizontal overflow on tablet
        tablet_overflow = wd.execute_script("""
            return document.documentElement.scrollWidth > window.innerWidth;
        """)
        print(f"Tablet 768px horizontal overflow: {tablet_overflow}")
        assert not tablet_overflow, "Tablet 768px layout has horizontal overflow!"
        wd.take_screenshot("responsive_03_tablet_layout.png")

        print("\n--- 4. Testing Mobile Layout with Sidebar Closed (375px) ---")
        wd.set_window_size(375, 812)
        time.sleep(1)

        # Verify desktop sidebar is hidden
        desktop_hidden = wd.execute_script("""
            const aside = document.querySelector('aside[aria-label="Desktop Navigation"]');
            return !aside || window.getComputedStyle(aside).display === 'none';
        """)
        print(f"Desktop sidebar hidden on mobile: {desktop_hidden}")
        assert desktop_hidden, "Desktop sidebar should be hidden on 375px mobile!"

        # Verify hamburger menu exists and is visible
        hamburger_visible = wd.execute_script("""
            const btn = document.querySelector('button[aria-label="Open navigation menu"]');
            return btn && window.getComputedStyle(btn).display !== 'none';
        """)
        print(f"Mobile hamburger menu visible: {hamburger_visible}")
        assert hamburger_visible, "Hamburger button must be visible on mobile!"

        # Check mobile title does not wrap into 3 lines (offset height should be <= 32px)
        title_height = wd.execute_script("""
            const title = document.querySelector('header h1');
            return title ? title.offsetHeight : 0;
        """)
        print(f"Mobile header title height: {title_height}px")
        assert title_height <= 32, f"Title wrapped unexpectedly! Height: {title_height}px"

        wd.take_screenshot("responsive_04_mobile_closed_sidebar.png")

        print("\n--- 5. Testing Mobile Header & Connection Status Details ---")
        # Click mobile connection status pill to open details modal
        wd.execute_script("""
            const pill = document.querySelector('button[aria-label="Backend status"]');
            if (pill) pill.click();
        """)
        time.sleep(0.5)

        modal_open = wd.execute_script("""
            const modal = document.querySelector('div[role="dialog"][aria-labelledby="backend-details-title"]');
            return !!modal;
        """)
        print(f"Mobile connection details modal opened: {modal_open}")
        assert modal_open, "Mobile connection details modal should open on tap!"

        wd.take_screenshot("responsive_09_mobile_header_details_modal.png")

        # Close modal
        wd.execute_script("""
            const closeBtn = document.querySelector('button[aria-label="Close details"]');
            if (closeBtn) closeBtn.click();
        """)
        time.sleep(0.3)

        print("\n--- 6. Testing Mobile Drawer Opening, Interaction & Accessibility ---")
        # Click hamburger menu
        wd.execute_script("""
            const btn = document.querySelector('button[aria-label="Open navigation menu"]');
            if (btn) btn.click();
        """)
        time.sleep(0.5)

        drawer_open = wd.execute_script("""
            const drawer = document.querySelector('aside[aria-label="Mobile Navigation Menu"]');
            return !!drawer;
        """)
        print(f"Mobile drawer opened: {drawer_open}")
        assert drawer_open, "Mobile drawer failed to open!"

        # Check body scroll lock
        body_overflow = wd.execute_script("return document.body.style.overflow;")
        print(f"Body overflow when drawer open: '{body_overflow}'")
        assert body_overflow == "hidden", f"Expected body overflow 'hidden', got '{body_overflow}'"

        wd.take_screenshot("responsive_05_mobile_opened_sidebar.png")

        # Test closing with Escape key
        print("Testing Escape key to close mobile drawer...")
        wd.execute_script("""
            window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        """)
        time.sleep(0.5)

        drawer_closed = wd.execute_script("""
            const drawer = document.querySelector('aside[aria-label="Mobile Navigation Menu"]');
            return !drawer;
        """)
        print(f"Drawer closed on Escape: {drawer_closed}")
        assert drawer_closed, "Drawer should close when Escape key is pressed!"

        # Reopen and test clicking navigation item (e.g. Media Toolkit)
        print("Testing drawer navigation to Media Toolkit...")
        wd.execute_script("""
            const btn = document.querySelector('button[aria-label="Open navigation menu"]');
            if (btn) btn.click();
        """)
        time.sleep(0.5)

        wd.execute_script("""
            const navButtons = Array.from(document.querySelectorAll('aside[aria-label="Mobile Navigation Menu"] button'));
            const toolkitBtn = navButtons.find(b => b.textContent && b.textContent.includes('Media Toolkit'));
            if (toolkitBtn) toolkitBtn.click();
        """)
        time.sleep(1.5)

        current_hash = wd.execute_script("return window.location.hash;")
        print(f"Navigated to hash: {current_hash}")
        assert "toolkit" in current_hash, f"Expected #toolkit, got {current_hash}"

        # Verify drawer auto-closed upon selection
        drawer_closed_after_nav = wd.execute_script("""
            const drawer = document.querySelector('aside[aria-label="Mobile Navigation Menu"]');
            return !drawer;
        """)
        assert drawer_closed_after_nav, "Drawer must close after a navigation item is tapped!"

        print("\n--- 7. Testing Mobile Media Toolkit (375px) ---")
        time.sleep(1)
        toolkit_overflow = wd.execute_script("""
            return document.documentElement.scrollWidth > window.innerWidth;
        """)
        print(f"Media Toolkit 375px horizontal overflow: {toolkit_overflow}")
        assert not toolkit_overflow, "Media Toolkit has horizontal overflow on 375px!"
        wd.take_screenshot("responsive_06_mobile_media_toolkit.png")

        print("\n--- 8. Testing Mobile Voice Studio (375px) ---")
        wd.navigate(f"{BASE_URL}/#voices")
        time.sleep(1.5)
        voices_overflow = wd.execute_script("""
            return document.documentElement.scrollWidth > window.innerWidth;
        """)
        print(f"Voice Studio 375px horizontal overflow: {voices_overflow}")
        assert not voices_overflow, "Voice Studio has horizontal overflow on 375px!"
        wd.take_screenshot("responsive_07_mobile_voice_studio.png")

        print("\n--- 9. Testing Mobile Dubbing Studio / Projects (375px) ---")
        # First create a temporary project via API to test Dubbing Studio
        create_req = urllib.request.Request(
            f"{API_URL}/projects",
            data=json.dumps({"title": "Mobile Dubbing Responsive Test"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(create_req) as resp:
            proj_data = json.loads(resp.read().decode("utf-8"))
        test_pid = proj_data["id"]
        print(f"Created temporary project for testing: {test_pid}")

        wd.navigate(f"{BASE_URL}/#project/{test_pid}")
        time.sleep(2)

        dubbing_overflow = wd.execute_script("""
            return document.documentElement.scrollWidth > window.innerWidth;
        """)
        print(f"Dubbing Studio 375px horizontal overflow: {dubbing_overflow}")
        assert not dubbing_overflow, "Dubbing Studio has horizontal overflow on 375px!"
        wd.take_screenshot("responsive_08_mobile_dubbing_studio.png")

        # Clean up test project
        del_req = urllib.request.Request(f"{API_URL}/projects/{test_pid}", method="DELETE")
        try:
            with urllib.request.urlopen(del_req) as resp:
                pass
            print("Cleaned up test project.")
        except Exception as e:
            print(f"Error cleaning test project: {e}")

        print("\n--- 10. Testing Navigation After Browser Resizing (Responsive Transitions) ---")
        # Start at 375px, open drawer, resize to 1280px, verify drawer closes cleanly
        wd.navigate(f"{BASE_URL}/#dashboard")
        time.sleep(1)
        wd.execute_script("""
            const btn = document.querySelector('button[aria-label="Open navigation menu"]');
            if (btn) btn.click();
        """)
        time.sleep(0.5)

        # Now resize to desktop 1280px
        wd.set_window_size(1280, 800)
        time.sleep(1)

        drawer_closed_on_resize = wd.execute_script("""
            const drawer = document.querySelector('aside[aria-label="Mobile Navigation Menu"]');
            return !drawer;
        """)
        print(f"Drawer automatically closed upon resizing to 1280px: {drawer_closed_on_resize}")
        assert drawer_closed_on_resize, "Mobile drawer should auto-close when resizing to desktop!"

        wd.take_screenshot("responsive_10_navigation_after_resizing.png")

        print("\n--- 11. Testing All Required Viewport Widths for Horizontal Overflow ---")
        viewports = [320, 375, 390, 430, 640, 768, 1024, 1280, 1440]
        pages = ["dashboard", "projects", "toolkit", "voices", "settings"]

        for w in viewports:
            wd.set_window_size(w, 800)
            time.sleep(0.5)
            for page in pages:
                wd.navigate(f"{BASE_URL}/#{page}")
                time.sleep(0.5)
                overflow = wd.execute_script("""
                    return document.documentElement.scrollWidth > window.innerWidth;
                """)
                assert not overflow, f"Page #{page} has horizontal overflow at {w}px!"
            print(f"✓ Viewport {w}px: All 5 main pages have 0 horizontal overflow.")

        # Capture specific 320px ultra-narrow mobile screenshot
        wd.set_window_size(320, 600)
        wd.navigate(f"{BASE_URL}/#dashboard")
        time.sleep(1)
        wd.take_screenshot("responsive_11_narrow_mobile_320px.png")
        print("✓ Captured 320px ultra-narrow mobile screenshot.")

        print("\n=======================================================")
        print("  ALL RESPONSIVE UI AUTOMATED TESTS PASSED SUCCESSFULLY!")
        print("=======================================================")

    finally:
        wd.close()


if __name__ == "__main__":
    run_tests()
