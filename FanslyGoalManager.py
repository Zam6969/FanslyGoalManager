import os
import sys
import json
import time
import textwrap
import requests
import webbrowser
from io import BytesIO
from PySide6.QtGui import QPainter, QPainterPath


from PySide6.QtWidgets import (
    QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QTabWidget, QRadioButton,
    QButtonGroup, QMessageBox
)
from PySide6.QtGui import QFont, QPalette, QColor, QPixmap
from PySide6.QtCore import Qt

# Selenium imports for automatic login
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- Program version ---
PROGRAM_VERSION = "1.0.4"
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/Zam6969/FanslyGoalManager/refs/heads/main/version.txt"
GITHUB_REPO_URL = "https://github.com/Zam6969/FanslyGoalManager"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), "fansly_config.json")

# === Functions for automatic login and credential fetching ===

def fetch_raw_session(driver, storage_key="session_active_session"):
    """
    Return the raw JSON string from localStorage for the given key, or None if missing.
    """
    return driver.execute_script(f"return window.localStorage.getItem('{storage_key}');")


def extract_token(raw_json):
    """
    Given a JSON string, parse and extract a token under common keys.
    Returns (token, error_message).
    """
    if raw_json is None:
        return None, "no raw data (key not set yet)"
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError) as e:
        return None, f"invalid JSON in storage: {e}"
    if not isinstance(data, dict):
        return None, f"unexpected storage format (not an object): {data!r}"
    for key in ("token", "accessToken", "sessionToken"):
        if key in data and data[key]:
            return data[key], None
    return None, f"no token field in session object, keys={list(data.keys())}"


def login_and_fetch_credentials():
    """
    Launches a Chrome browser for the user to log in, polls localStorage for the
    Fansly session token, then calls the account/me endpoint to get the chatRoomId.
    """
    # Start Chrome
    options = webdriver.ChromeOptions()
    # Uncomment to persist login between runs:
    # options.add_argument("--user-data-dir=./selenium-profile")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    # Navigate to Fansly
    driver.get("https://fansly.com/")
    print("🚀 Browser opened. Please log in to https://fansly.com/ …")

    # Poll for session token
    token = None
    while token is None:
        raw = fetch_raw_session(driver)
        token, err = extract_token(raw)
        if token:
            print("✅ Retrieved session token.")
            break
        else:
            print("⚠️", err)
        time.sleep(1)

    driver.quit()

    # Fetch chatRoomId via API
    headers = {"Authorization": token, "Content-Type": "application/json"}
    resp = requests.get(
        "https://apiv3.fansly.com/api/v1/account/me?ngsw-bypass=true",
        headers=headers
    )
    resp.raise_for_status()
    data = resp.json().get("response", {})
    account = data.get("account", {})
    streaming = account.get("streaming", {})
    channel = streaming.get("channel", {})
    chat_room_id = channel.get("chatRoomId")
    if not chat_room_id:
        raise RuntimeError("Unable to fetch chatRoomId from account response.")
    print(f"✅ Retrieved chatRoomId → {chat_room_id}")
    return token, str(chat_room_id)


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            d = json.load(f)
        return d.get("AUTH_TOKEN"), d.get("CHATROOM_ID"), d.get("PRESETS", {})
    return None, None, {}

def save_config(auth, chat_id, presets):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump({
            "AUTH_TOKEN": auth,
            "CHATROOM_ID": chat_id,
            "PRESETS": presets
        }, f, indent=2)

def check_for_update():
    try:
        r = requests.get(UPDATE_CHECK_URL, timeout=5)
        r.raise_for_status()
        latest = r.text.strip()
        if latest != PROGRAM_VERSION:
            msg = QMessageBox()
            msg.setWindowTitle("Update Available")
            msg.setText(
                f"A new version is available!\n\n"
                f"Your version: {PROGRAM_VERSION}\n"
                f"Latest version: {latest}\n\n"
                f"Would you like to open the GitHub repo to download it?"
            )
            msg.setIcon(QMessageBox.Information)
            open_btn = msg.addButton("Open Repo", QMessageBox.AcceptRole)
            msg.addButton("Not Really (continue)", QMessageBox.RejectRole)
            msg.exec()
            if msg.clickedButton() == open_btn:
                webbrowser.open(GITHUB_REPO_URL)
    except Exception as e:
        print(f"[WARN] Version check failed: {e}")

class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login with Fansly")
        self.setModal(True)
        self.resize(300, 100)
        btn = QPushButton("Login with Fansly")
        btn.setFont(QFont("Segoe UI Emoji", 12))
        btn.clicked.connect(self._do_login)
        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(btn, alignment=Qt.AlignCenter)
        layout.addStretch()
        self.token = None
        self.chat_id = None

    def _do_login(self):
        try:
            t, c = login_and_fetch_credentials()
        except Exception as e:
            QMessageBox.critical(self, "Login Error", str(e))
            return
        self.token   = t
        self.chat_id = c
        self.accept()


class GoalManager(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fansly Goal Manager")
        self.resize(1000, 600)
        auth, chat_id, loaded_presets = load_config()
        if not auth or not chat_id:
            dlg = LoginDialog()
            if dlg.exec() != QDialog.Accepted:
                sys.exit(0)

            auth, chat_id = dlg.token, dlg.chat_id
            save_config(auth, chat_id, loaded_presets)    

        self.AUTH_TOKEN = auth
        self.CHAT_ID = chat_id
        self.PRESETS = loaded_presets or {}
        self.HEADERS = {
            "Authorization": self.AUTH_TOKEN,
            "Content-Type": "application/json"
        }
        self.BASE_URL = "https://apiv3.fansly.com/api/v1/chatroom/goals"
        self.CREATE_URL = self.BASE_URL + "?ngsw-bypass=true"
        self.UPDATE_URL = "https://apiv3.fansly.com/api/v1/chatroom/goal/update?ngsw-bypass=true"
        self.goals = []
        self.font = QFont("Segoe UI Emoji", 12)
        self.radio_buttons = []
        self.labels = []

        outer = QVBoxLayout(self)
        top_bar = QHBoxLayout()

        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(64, 64)
        self.avatar_label.setScaledContents(True)
        top_bar.addWidget(self.avatar_label)

        self.welcome_label = QLabel("Checking login status...")
        self.welcome_label.setAlignment(Qt.AlignLeft)
        self.welcome_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        top_bar.addWidget(self.welcome_label)

        top_bar.addStretch()
        outer.addLayout(top_bar)

        main_layout = QHBoxLayout()
        main_layout.addLayout(self.build_left_panel(), 1)
        main_layout.addLayout(self.build_middle_panel(), 1)
        main_layout.addLayout(self.build_right_panel(), 2)
        outer.addLayout(main_layout)

        footer = QHBoxLayout()
        credit = QLabel("made with love by cutezam")
        credit.setFont(QFont("Segoe UI Emoji", 8))
        credit.setStyleSheet("color: gray;")
        footer.addWidget(credit, alignment=Qt.AlignLeft)
        footer.addStretch(1)
        outer.addLayout(footer)

        self.fetch_goals()
        self.load_account_status()

    def make_circular_pixmap(self, pixmap):
        size = min(pixmap.width(), pixmap.height())
        img = pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        rounded = QPixmap(size, size)
        rounded.fill(Qt.transparent)

        painter = QPainter(rounded)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, img)
        painter.end()

        return rounded

    def load_account_status(self):
        try:
            r = requests.get("https://apiv3.fansly.com/api/v1/account/me?ngsw-bypass=true", headers=self.HEADERS)
            r.raise_for_status()
            data = r.json()
            if data.get("success") and "response" in data:
                account = data["response"]["account"]
                username = account.get("username", "Unknown")
                self.welcome_label.setText(f"Welcome {username} – You are currently logged in")
                self.welcome_label.setStyleSheet("color: lightgreen; font-size: 14px;")

                avatar = account.get("avatar", {})
                avatar_url = None
                for variant in avatar.get("variants", []):
                    if variant.get("type") != 3 and "locations" in variant:
                        avatar_url = variant["locations"][0]["location"]
                        break
                if not avatar_url and "locations" in avatar:
                    avatar_url = avatar["locations"][0]["location"]
                if avatar_url:
                    img_data = requests.get(avatar_url).content
                    pixmap = QPixmap()
                    pixmap.loadFromData(img_data)
                    self.avatar_label.setPixmap(self.make_circular_pixmap(pixmap))
            else:
                self.welcome_label.setText("You are not logged in")
                self.welcome_label.setStyleSheet("color: red; font-size: 14px;")
        except Exception:
            self.welcome_label.setText("You are not logged in")
            self.welcome_label.setStyleSheet("color: red; font-size: 14px;")




    def build_left_panel(self):
        left = QVBoxLayout()
        left.addWidget(QLabel("Goal Amount"))
        self.amount_in = QLineEdit(); self.amount_in.setFont(self.font)
        left.addWidget(self.amount_in)
        left.addWidget(QLabel("Label"))
        self.label_in = QLineEdit(); self.label_in.setFont(self.font)
        left.addWidget(self.label_in)
        left.addWidget(QLabel("Description"))
        self.desc_in = QTextEdit(); self.desc_in.setFont(self.font)
        left.addWidget(self.desc_in)

        for text, slot in [
            ("Send Goal", self.send_goal),
            ("Fetch Goals (if not fetched already)", self.fetch_goals),
            ("Update Selected Goal", self.update_goal),
            ("Reset Selected Goal", self.reset_goal),
            ("Delete Selected Goal", self.delete_selected_goal),
            ("Delete All Goals", self.delete_all_goals)
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            b.setFont(self.font)
            left.addWidget(b)

        left.addStretch(1)
        return left

    def build_middle_panel(self):
        mid = QVBoxLayout()
        hdr = QLabel("Presets", alignment=Qt.AlignCenter)
        hdr.setFont(self.font)
        mid.addWidget(hdr)
        self.tabs = QTabWidget()
        self.tabs.setFont(self.font)
        for g in (1, 2, 3):
            page = QWidget()
            grid = QGridLayout(page)
            for i, slot in enumerate((1, 2, 3)):
                sv = QPushButton(f"Save {slot}")
                ed = QPushButton(f"Edit {slot}")
                sv.clicked.connect(lambda _, g=g, s=slot: self.save_preset(g, s))
                ed.clicked.connect(lambda _, g=g, s=slot: self.edit_preset(g, s))
                sv.setFont(self.font); ed.setFont(self.font)
                grid.addWidget(sv, 0, i)
                grid.addWidget(ed, 1, i)
            send = QPushButton("Send Presets")
            send.clicked.connect(lambda _, g=g: self.send_presets(g))
            send.setFont(self.font)
            grid.addWidget(send, 2, 0, 1, 3)
            self.tabs.addTab(page, f"Group {g}")
        mid.addWidget(self.tabs)
        mid.addStretch(1)
        return mid

    def build_right_panel(self):
        right = QGridLayout()
        hdr = QLabel("Current Goals", alignment=Qt.AlignCenter)
        hdr.setFont(self.font)
        right.addWidget(hdr, 0, 0, 1, 2)
        self.radio_group = QButtonGroup(self)
        for i in range(3):
            rb = QRadioButton()
            rb.setFont(self.font)
            rb.toggled.connect(self.load_selected)
            lbl = QLabel()
            lbl.setFont(self.font)
            lbl.setWordWrap(True)
            self.radio_group.addButton(rb, i)
            self.radio_buttons.append(rb)
            self.labels.append(lbl)
            right.addWidget(rb, 1 + i, 0, alignment=Qt.AlignTop)
            right.addWidget(lbl, 1 + i, 1)
        right.setColumnStretch(1, 1)
        return right

    def fetch_goals(self):
        try:
            params = {"chatRoomIds": self.CHAT_ID, "ngsw-bypass": "true"}
            r = requests.get(self.BASE_URL, params=params, headers=self.HEADERS)
            r.raise_for_status()
            data = r.json().get("response", [])[:3]
        except Exception as e:
            QMessageBox.critical(self, "Fetch Error", str(e))
            data = []
        self.goals = data
        for i in range(3):
            if i < len(data):
                g = data[i]
                text = "\n".join(textwrap.wrap(g.get("label", ""), width=30))
                desc = "\n".join(textwrap.wrap(g.get("description", ""), width=40))
                amt = f"$ {g.get('currentAmount', 0) // 1000} / $ {g['goalAmount'] // 1000}"
                self.labels[i].setText(f"{text}\n{desc}\n{amt}")
                self.radio_buttons[i].setEnabled(True)
            else:
                self.labels[i].clear()
                self.radio_buttons[i].setChecked(False)
                self.radio_buttons[i].setEnabled(False)

    def load_selected(self):
        idx = self.radio_group.checkedId()
        if idx < 0 or idx >= len(self.goals): return
        g = self.goals[idx]
        self.amount_in.setText(str(g["goalAmount"] // 1000))
        self.label_in.setText(g.get("label", ""))
        self.desc_in.setPlainText(g.get("description", ""))

    def send_goal(self):
        try:
            amt = int(self.amount_in.text())
        except:
            QMessageBox.warning(self, "Input Error", "Enter whole dollars")
            return
        pl = {
            "chatRoomId": self.CHAT_ID,
            "type": 0,
            "goalAmount": amt * 1000,
            "label": self.label_in.text().strip(),
            "description": self.desc_in.toPlainText().strip()
        }
        r = requests.post(self.CREATE_URL, json=pl, headers=self.HEADERS)
        if r.status_code // 100 == 2:
            self.fetch_goals()
        else:
            QMessageBox.critical(self, "Error", f"{r.status_code}")

    def delete_selected_goal(self):
        idx = self.radio_group.checkedId()
        if idx < 0:
            QMessageBox.warning(self, "No selection", "Select a goal first")
            return
        g = self.goals[idx]
        pl = {
            "id": g["id"], "chatRoomId": self.CHAT_ID, "accountId": g["accountId"],
            "currentAmount": g.get("currentAmount", 0), "deletedAt": int(time.time() * 1000),
            "description": g.get("description", ""), "goalAmount": g["goalAmount"],
            "label": g["label"], "status": 1, "type": g.get("type", 0), "version": g.get("version", 0)
        }
        r = requests.post(self.UPDATE_URL, json=pl, headers=self.HEADERS)
        if r.status_code // 100 == 2:
            self.fetch_goals()
        else:
            QMessageBox.critical(self, "Error", f"Delete failed: {r.status_code}")

    def update_goal(self):
        idx = self.radio_group.checkedId()
        if idx < 0:
            QMessageBox.warning(self, "No selection", "Select a goal first")
            return
        g = self.goals[idx]
        try:
            amt = int(self.amount_in.text())
        except:
            QMessageBox.warning(self, "Input Error", "Enter whole dollars")
            return
        pl = {
            "id": g["id"], "chatRoomId": self.CHAT_ID, "accountId": g["accountId"],
            "currentAmount": g.get("currentAmount", 0), "deletedAt": g.get("deletedAt", 0),
            "description": self.desc_in.toPlainText().strip(),
            "goalAmount": amt * 1000, "label": self.label_in.text().strip(),
            "status": g.get("status", 0), "type": g.get("type", 0), "version": g.get("version", 0)
        }
        r = requests.post(self.UPDATE_URL, json=pl, headers=self.HEADERS)
        if r.status_code // 100 == 2:
            self.fetch_goals()
        else:
            QMessageBox.critical(self, "Error", f"{r.status_code}")

    def delete_all_goals(self):
        try:
            params = {"chatRoomIds": self.CHAT_ID, "ngsw-bypass": "true"}
            r = requests.get(self.BASE_URL, params=params, headers=self.HEADERS)
            r.raise_for_status()
            items = r.json().get("response", [])
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return
        for g in items:
            pl = {
                "id": g["id"], "chatRoomId": self.CHAT_ID, "accountId": g["accountId"],
                "currentAmount": g.get("currentAmount", 0), "deletedAt": int(time.time() * 1000),
                "description": g.get("description", ""), "goalAmount": g["goalAmount"],
                "label": g["label"], "status": 1, "type": g.get("type", 0), "version": g.get("version", 0)
            }
            requests.post(self.UPDATE_URL, json=pl, headers=self.HEADERS)
        self.fetch_goals()

    def reset_goal(self):
        idx = self.radio_group.checkedId()
        if idx < 0:
            QMessageBox.warning(self, "No selection", "Select a goal first")
            return
        g = self.goals[idx]
        pl_del = {
            "id": g["id"], "chatRoomId": self.CHAT_ID, "accountId": g["accountId"],
            "currentAmount": g.get("currentAmount", 0), "deletedAt": int(time.time() * 1000),
            "description": g.get("description", ""), "goalAmount": g["goalAmount"],
            "label": g["label"], "status": 1, "type": g.get("type", 0), "version": g.get("version", 0)
        }
        r1 = requests.post(self.UPDATE_URL, json=pl_del, headers=self.HEADERS)
        if r1.status_code // 100 != 2:
            QMessageBox.critical(self, "Error", f"Reset delete failed: {r1.status_code}")
            return
        pl_new = {
            "chatRoomId": self.CHAT_ID, "type": 0, "goalAmount": g["goalAmount"],
            "label": g["label"], "description": g["description"]
        }
        r2 = requests.post(self.CREATE_URL, json=pl_new, headers=self.HEADERS)
        if r2.status_code // 100 == 2:
            self.fetch_goals()
        else:
            QMessageBox.critical(self, "Error", f"Reset create failed: {r2.status_code}")

    def save_preset(self, group, slot):
        try:
            amt = int(self.amount_in.text())
        except:
            QMessageBox.warning(self, "Input Error", "Enter whole dollars")
            return
        self.PRESETS.setdefault(group, {})[slot] = {
            "chatRoomId": self.CHAT_ID, "type": 0,
            "goalAmount": amt * 1000,
            "label": self.label_in.text().strip(),
            "description": self.desc_in.toPlainText().strip()
        }
        save_config(self.AUTH_TOKEN, self.CHAT_ID, self.PRESETS)
        QMessageBox.information(self, "Saved", f"Group {group} Slot {slot}")

    def edit_preset(self, group, slot):
        pl = self.PRESETS.get(group, {}).get(slot)
        if not pl:
            QMessageBox.warning(self, "Missing", f"No preset in Group {group} Slot {slot}")
            return
        self.amount_in.setText(str(pl["goalAmount"] // 1000))
        self.label_in.setText(pl.get("label", ""))
        self.desc_in.setPlainText(pl.get("description", ""))

    def send_presets(self, group):
        presets = self.PRESETS.get(group, {})
        if not presets:
            QMessageBox.warning(self, "Missing", f"No presets found for Group {group}")
            return
        for slot, pl in presets.items():
            r = requests.post(self.CREATE_URL, json=pl, headers=self.HEADERS)
            if r.status_code // 100 != 2:
                QMessageBox.warning(self, "Error", f"Slot {slot} failed: {r.status_code}")
        self.fetch_goals()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    dark = QPalette()
    dark.setColor(QPalette.Window, QColor(30, 30, 30))
    dark.setColor(QPalette.WindowText, Qt.white)
    dark.setColor(QPalette.Base, QColor(20, 20, 20))
    dark.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
    dark.setColor(QPalette.ToolTipBase, Qt.white)
    dark.setColor(QPalette.ToolTipText, Qt.white)
    dark.setColor(QPalette.Text, Qt.white)
    dark.setColor(QPalette.Button, QColor(50, 50, 50))
    dark.setColor(QPalette.ButtonText, Qt.white)
    dark.setColor(QPalette.BrightText, Qt.red)
    dark.setColor(QPalette.Link, QColor(42, 130, 218))
    dark.setColor(QPalette.Highlight, QColor(42, 130, 218))
    dark.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(dark)
    check_for_update()
    w = GoalManager()
    w.show()
    sys.exit(app.exec())

