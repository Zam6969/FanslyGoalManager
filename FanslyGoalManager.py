import os, sys, json, time, requests, textwrap
import customtkinter as ctk
from tkinter import messagebox

# ————— Config handling —————
CONFIG_PATH = os.path.join(os.path.expanduser("~"), "fansly_config.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            d = json.load(f)
        return d.get("AUTH_TOKEN"), d.get("CHATROOM_ID"), d.get("PRESETS", {})
    return None, None, {}

def save_config(auth, chat_id, presets):
    with open(CONFIG_PATH, "w") as f:
        json.dump({
            "AUTH_TOKEN": auth,
            "CHATROOM_ID": chat_id,
            "PRESETS": presets
        }, f, indent=2)

def prompt_config():
    dlg = ctk.CTk()
    dlg.title("Setup Config")
    dlg.resizable(False, False)
    w, h = 400, 220
    sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
    dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
    dlg.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(dlg, text="Auth Token:", anchor="w")\
       .grid(row=0, column=0, padx=20, pady=(20,4), sticky="ew")
    e1 = ctk.CTkEntry(dlg)
    e1.grid(row=1, column=0, padx=20, pady=(0,10), sticky="ew")

    ctk.CTkLabel(dlg, text="ChatRoom ID:", anchor="w")\
       .grid(row=2, column=0, padx=20, pady=(0,4), sticky="ew")
    e2 = ctk.CTkEntry(dlg)
    e2.grid(row=3, column=0, padx=20, pady=(0,10), sticky="ew")

    def on_close():
        dlg.destroy()
        sys.exit()
    dlg.protocol("WM_DELETE_WINDOW", on_close)

    def save_and_go():
        tok, cid = e1.get().strip(), e2.get().strip()
        if not tok or not cid:
            return messagebox.showwarning("Missing", "All fields required", parent=dlg)
        save_config(tok, cid, {})
        dlg.destroy()

    ctk.CTkButton(dlg, text="Save", command=save_and_go)\
       .grid(row=4, column=0, pady=10)
    dlg.mainloop()

# ————— Initialize —————
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

AUTH_TOKEN, CHATROOM_ID, loaded_presets = load_config()
if not AUTH_TOKEN or not CHATROOM_ID:
    prompt_config()
    AUTH_TOKEN, CHATROOM_ID, loaded_presets = load_config()

HEADERS      = {"Content-Type": "application/json", "Authorization": AUTH_TOKEN}
BASE_URL     = "https://apiv3.fansly.com/api/v1/chatroom/goals"
FETCH_PARAMS = {"chatRoomIds": CHATROOM_ID, "ngsw-bypass": "true"}
CREATE_URL   = BASE_URL + "?ngsw-bypass=true"
UPDATE_URL   = "https://apiv3.fansly.com/api/v1/chatroom/goal/update?ngsw-bypass=true"

# ————— State —————
entry_amount = entry_label = entry_desc = update_btn = None
goals_dict = {}
presets = {g:{s:None for s in (1,2,3)} for g in (1,2,3)}
for g_str, slots in loaded_presets.items():
    try:
        g = int(g_str)
        for s_str, payload in slots.items():
            presets[g][int(s_str)] = payload
    except:
        pass

# ————— Build window & StringVar —————
app = ctk.CTk()
app.title("Fansly Goal Manager")
app.geometry("1000x600")
sw, sh = app.winfo_screenwidth(), app.winfo_screenheight()
app.geometry(f"1000x600+{(sw-1000)//2}+{(sh-600)//2}")
app.grid_columnconfigure((0,1,2), weight=1)
app.grid_rowconfigure(0, weight=1)

selected_goal_var = ctk.StringVar(app)

# ————— API Actions —————
def fetch_and_display_goals():
    global goals_list_frame
    resp = requests.get(BASE_URL, params=FETCH_PARAMS, headers=HEADERS)
    if resp.status_code != 200:
        return messagebox.showerror("Error", f"Fetch failed: {resp.status_code}")
    goals_list_frame.destroy()
    build_goals_list(right_frame)

def build_goals_list(parent):
    global goals_list_frame, goals_dict
    goals_list_frame = ctk.CTkFrame(parent, fg_color="#1f1f1f")
    goals_list_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
    parent.grid_rowconfigure(1, weight=1)
    parent.grid_columnconfigure(0, weight=1)

    goals_dict.clear()
    resp = requests.get(BASE_URL, params=FETCH_PARAMS, headers=HEADERS)
    for idx, g in enumerate(resp.json().get("response", [])[:3]):
        goals_dict[g["id"]] = g

        # container for each goal
        container = ctk.CTkFrame(goals_list_frame, fg_color="transparent")
        container.grid(row=idx, column=0, sticky="ew", padx=8, pady=4)
        container.grid_columnconfigure(1, weight=1)

        # radio button with no text
        rb = ctk.CTkRadioButton(
            container,
            text="",                      # ← hide the built-in label
            variable=selected_goal_var,
            value=g["id"],
            command=on_select_goal
        )
        rb.grid(row=0, column=0, sticky="nw")

        # wrap label & description
        label_text = g.get("label", "")
        desc_text  = g.get("description", "")
        wrapped_label = "\n".join(textwrap.wrap(label_text, width=30))
        wrapped_desc  = "\n".join(textwrap.wrap(desc_text,  width=40))
        amount_line   = f"${g.get('currentAmount',0)//1000} / ${g['goalAmount']//1000}"
        full_text = wrapped_label
        if wrapped_desc:
            full_text += "\n" + wrapped_desc
        full_text += "\n" + amount_line

        # multi-line label
        lbl = ctk.CTkLabel(
            container,
            text=full_text,
            anchor="w",
            justify="left",
            wraplength=300
        )
        lbl.grid(row=0, column=1, sticky="w", padx=(10,0))

def on_select_goal():
    g = goals_dict[selected_goal_var.get()]
    entry_amount.delete(0, "end"); entry_amount.insert(0, str(g["goalAmount"]//1000))
    entry_label.delete(0, "end"); entry_label.insert(0, g["label"])
    entry_desc.delete(0, "end"); entry_desc.insert(0, g["description"])
    update_btn.configure(state="normal")

def send_goal():
    try:
        ua = int(entry_amount.get())
    except:
        return messagebox.showerror("Input Error", "Enter whole dollars")
    pl = {
        "chatRoomId": CHATROOM_ID,
        "type": 0,
        "goalAmount": ua*1000,
        "label": entry_label.get().strip(),
        "description": entry_desc.get().strip()
    }
    r = requests.post(CREATE_URL, json=pl, headers=HEADERS)
    if r.status_code//100 == 2:
        fetch_and_display_goals()
    else:
        messagebox.showerror("Error", f"{r.status_code}")

def update_goal():
    gid = selected_goal_var.get()
    g = goals_dict[gid]
    try:
        ua = int(entry_amount.get())
    except:
        return messagebox.showerror("Input Error", "Enter whole dollars")
    pl = {
        "id": g["id"], "chatRoomId": CHATROOM_ID,
        "accountId": g["accountId"],
        "currentAmount": g.get("currentAmount",0),
        "deletedAt": g.get("deletedAt",0),
        "description": entry_desc.get().strip(),
        "goalAmount": ua*1000,
        "label": entry_label.get().strip(),
        "status": g.get("status",0),
        "type": g.get("type",0),
        "version": g.get("version",0)
    }
    r = requests.post(UPDATE_URL, json=pl, headers=HEADERS)
    if r.status_code//100 == 2:
        fetch_and_display_goals()
    else:
        messagebox.showerror("Error", f"{r.status_code}")
    update_btn.configure(state="disabled")

def delete_all_goals():
    resp = requests.get(BASE_URL, params=FETCH_PARAMS, headers=HEADERS)
    if resp.status_code != 200:
        return messagebox.showerror("Error", f"{resp.status_code}")
    for g in resp.json().get("response", []):
        pl = {
            "id": g["id"], "chatRoomId": CHATROOM_ID,
            "accountId": g["accountId"],
            "currentAmount": g.get("currentAmount",0),
            "deletedAt": int(time.time()*1000),
            "description": g.get("description",""),
            "goalAmount": g["goalAmount"],
            "label": g["label"],
            "status": 1, "type": g.get("type",0),
            "version": g.get("version",0)
        }
        requests.post(UPDATE_URL, json=pl, headers=HEADERS)
    fetch_and_display_goals()

# ————— New reset_goal action —————
def reset_goal():
    gid = selected_goal_var.get()
    if not gid:
        return messagebox.showwarning("No Selection", "Select a goal first")
    g = goals_dict[gid]
    # store original
    label = g.get("label", "")
    desc  = g.get("description", "")
    amt   = g.get("goalAmount", 0)

    # delete it
    pl_del = {
        "id": g["id"], "chatRoomId": CHATROOM_ID,
        "accountId": g["accountId"],
        "currentAmount": g.get("currentAmount",0),
        "deletedAt": int(time.time()*1000),
        "description": desc,
        "goalAmount": amt,
        "label": label,
        "status": 1, "type": g.get("type",0),
        "version": g.get("version",0)
    }
    r1 = requests.post(UPDATE_URL, json=pl_del, headers=HEADERS)
    if r1.status_code//100 != 2:
        return messagebox.showerror("Error", f"Reset delete failed: {r1.status_code}")

    # recreate fresh
    pl_new = {
        "chatRoomId": CHATROOM_ID,
        "type": 0,
        "goalAmount": amt,
        "label": label,
        "description": desc
    }
    r2 = requests.post(CREATE_URL, json=pl_new, headers=HEADERS)
    if r2.status_code//100 == 2:
        fetch_and_display_goals()
    else:
        messagebox.showerror("Error", f"Reset create failed: {r2.status_code}")

def save_preset(group, slot):
    try:
        ua = int(entry_amount.get())
    except:
        return messagebox.showerror("Input Error", "Enter whole dollars")
    presets[group][slot] = {
        "chatRoomId": CHATROOM_ID, "type": 0,
        "goalAmount": ua*1000,
        "label": entry_label.get().strip(),
        "description": entry_desc.get().strip()
    }
    messagebox.showinfo("Saved", f"Group {group} Slot {slot}")

def edit_preset(group, slot):
    pl = presets[group].get(slot)
    if not pl:
        return messagebox.showwarning("No preset", f"Slot {slot} empty")
    entry_amount.delete(0, "end"); entry_amount.insert(0, str(pl["goalAmount"]//1000))
    entry_label.delete(0, "end"); entry_label.insert(0, pl["label"])
    entry_desc.delete(0, "end"); entry_desc.insert(0, pl["description"])

def send_group_presets(group):
    for pl in presets[group].values():
        if pl:
            requests.post(CREATE_URL, json=pl, headers=HEADERS)
    fetch_and_display_goals()

# ————— Build UI —————

# Left column
left = ctk.CTkFrame(app, fg_color="#1f1f1f", corner_radius=10)
left.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
left.grid_columnconfigure(0, weight=1)

for i, label in enumerate(("Goal Amount","Label","Description")):
    ctk.CTkLabel(left, text=label, anchor="w")\
       .grid(row=i*2, column=0, sticky="w", padx=10, pady=(10,2))
    e = ctk.CTkEntry(left)
    e.grid(row=i*2+1, column=0, sticky="ew", padx=10)
    if i==0: entry_amount=e
    elif i==1: entry_label=e
    else: entry_desc=e

actions = [
    ("Send Goal", send_goal),
    ("Fetch Goals", fetch_and_display_goals),
    ("Delete All Goals", delete_all_goals),
    ("Update Goal", update_goal)
]
for j,(text,cmd) in enumerate(actions):
    btn = ctk.CTkButton(left, text=text, command=cmd, width=180)
    btn.grid(row=6+j, column=0, pady=5)
    if text=="Update Goal":
        update_btn=btn
        btn.configure(state="disabled")

# ————— Reset Goal button —————
reset_btn = ctk.CTkButton(left, text="Reset Goal", command=reset_goal, width=180)
reset_btn.grid(row=6+len(actions), column=0, pady=5)

# Middle column: Presets
mid = ctk.CTkFrame(app, fg_color="#1f1f1f", corner_radius=10)
mid.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
mid.grid_columnconfigure(0, weight=1)
mid.grid_rowconfigure(1, weight=1)

ctk.CTkLabel(mid, text="Presets", font=ctk.CTkFont(size=18, weight="bold"))\
   .grid(row=0, column=0, pady=(10,5))

tab = ctk.CTkTabview(mid)
tab.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
for grp in (1,2,3):
    tab.add(f"Group {grp}")
    frame = tab.tab(f"Group {grp}")
    frame.grid_columnconfigure((0,1,2), weight=1)

    for idx, slot in enumerate((1,2,3)):
        ctk.CTkButton(
            frame, text=f"Save {slot}",
            command=lambda g=grp,s=slot: save_preset(g,s)
        ).grid(row=0, column=idx, padx=5, pady=(10,5))
        ctk.CTkButton(
            frame, text=f"Edit {slot}",
            command=lambda g=grp,s=slot: edit_preset(g,s)
        ).grid(row=1, column=idx, padx=5, pady=(0,10))

    ctk.CTkButton(
        frame, text="Send Presets",
        command=lambda g=grp: send_group_presets(g),
        width=260
    ).grid(row=2, column=0, columnspan=3, pady=(0,15))

# Right column: Current Goals
right_frame = ctk.CTkFrame(app, fg_color="#1f1f1f", corner_radius=10)
right_frame.grid(row=0, column=2, sticky="nsew", padx=10, pady=10)
right_frame.grid_columnconfigure(0, weight=1)
right_frame.grid_rowconfigure(1, weight=1)

ctk.CTkLabel(
    right_frame, text="Current Goals",
    font=ctk.CTkFont(size=18, weight="bold")
).grid(row=0, column=0, pady=(10,5))

goals_list_frame = ctk.CTkFrame(right_frame)
goals_list_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
build_goals_list(right_frame)

# Save on exit
app.protocol("WM_DELETE_WINDOW", lambda: (
    save_config(AUTH_TOKEN, CHATROOM_ID, presets),
    app.destroy()
))

app.mainloop()
