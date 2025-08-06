import os
import sys
import json
import time
import textwrap
import requests
import webbrowser

from PySide6.QtWidgets import (
    QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QTabWidget, QRadioButton,
    QButtonGroup, QMessageBox
)
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtCore import Qt

# --- Program version ---
PROGRAM_VERSION = "1.0.3"
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/Zam6969/FanslyGoalManager/refs/heads/main/version.txt"
GITHUB_REPO_URL = "https://github.com/Zam6969/FanslyGoalManager"

CONFIG_PATH = os.path.join(os.path.expanduser("~"), "fansly_config.json")

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
            msg = (f"A new version is available!\n\n"
                   f"Your version: {PROGRAM_VERSION}\n"
                   f"Latest version: {latest}\n\n"
                   f"Would you like to open the GitHub repo to download it?")
            
            dlg = QMessageBox()
            dlg.setWindowTitle("Update Available")
            dlg.setText(msg)
            dlg.setIcon(QMessageBox.Information)

            open_btn = dlg.addButton("Open Repo", QMessageBox.AcceptRole)
            ok_btn = dlg.addButton("OK", QMessageBox.RejectRole)

            dlg.exec()

            if dlg.clickedButton() == open_btn:
                webbrowser.open(GITHUB_REPO_URL)
    except Exception as e:
        print(f"[WARN] Version check failed: {e}")

class ConfigDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Setup Config")
        self.setModal(True)
        self.resize(400, 200)
        layout = QVBoxLayout(self)

        font = QFont("Segoe UI Emoji", 12)
        layout.addWidget(QLabel("Auth Token:"))
        self.auth_in = QLineEdit(); self.auth_in.setFont(font)
        layout.addWidget(self.auth_in)

        layout.addWidget(QLabel("ChatRoom ID:"))
        self.chatid_in = QLineEdit(); self.chatid_in.setFont(font)
        layout.addWidget(self.chatid_in)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        btn_layout.addStretch(1)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def get_values(self):
        return self.auth_in.text().strip(), self.chatid_in.text().strip()

class GoalManager(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fansly Goal Manager")
        self.resize(1000, 600)

        auth, chat_id, loaded_presets = load_config()
        if not auth or not chat_id:
            dlg = ConfigDialog()
            if dlg.exec() != QDialog.Accepted:
                sys.exit(0)
            auth, chat_id = dlg.get_values()
            if not auth or not chat_id:
                QMessageBox.critical(None, "Missing Input", "Auth Token and ChatRoom ID are required.")
                sys.exit(0)
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
            ("Fetch Goals", self.fetch_goals),
            ("Delete Selected Goal", self.delete_selected_goal),
            ("Delete All Goals", self.delete_all_goals),
            ("Update Goal", self.update_goal),
            ("Reset Goal Amount select", self.reset_goal)
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
        if idx < 0 or idx >= len(self.goals):
            return
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
            QMessageBox.warning(self, "No preset", f"Slot {slot} empty")
            return
        self.amount_in.setText(str(pl["goalAmount"] // 1000))
        self.label_in.setText(pl["label"])
        self.desc_in.setPlainText(pl["description"])

    def send_presets(self, group):
        for pl in self.PRESETS.get(group, {}).values():
            requests.post(self.CREATE_URL, json=pl, headers=self.HEADERS)
        self.fetch_goals()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53,53,53))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(35,35,35))
    palette.setColor(QPalette.AlternateBase, QColor(53,53,53))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(53,53,53))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42,130,218))
    palette.setColor(QPalette.Highlight, QColor(42,130,218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)

    check_for_update()  # ✅ Show popup if newer version exists

    w = GoalManager()
    w.show()
    sys.exit(app.exec())
