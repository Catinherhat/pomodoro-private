import ctypes
import json
import os
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


APP_NAME = "Taskbar Pomodoro"
FOCUS_SECONDS = 25 * 60
SHORT_BREAK_SECONDS = 5 * 60
LONG_BREAK_SECONDS = 15 * 60


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def config_path() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        path = Path(base) / APP_NAME
    else:
        path = Path.home() / ".taskbar-pomodoro"
    path.mkdir(parents=True, exist_ok=True)
    return path / "settings.json"


def get_work_area(root: tk.Tk) -> tuple[int, int, int, int]:
    if sys.platform == "win32":
        rect = RECT()
        ok = ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
        if ok:
            return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("codex.taskbarpomodoro")
    except Exception:
        pass


class PomodoroPill:
    def __init__(self) -> None:
        set_windows_app_id()
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#14161a")
        self.root.resizable(False, False)

        self.settings_file = config_path()
        self.settings = self.load_settings()

        self.focus_seconds = int(self.settings.get("focus_seconds", FOCUS_SECONDS))
        self.short_break_seconds = int(self.settings.get("short_break_seconds", SHORT_BREAK_SECONDS))
        self.long_break_seconds = int(self.settings.get("long_break_seconds", LONG_BREAK_SECONDS))
        self.mode_key = self.settings.get("mode_key", "focus")
        self.mode = self.mode_name(self.mode_key)
        self.duration = self.duration_for_key(self.mode_key)
        self.remaining = int(self.settings.get("remaining", self.duration))
        self.running = bool(self.settings.get("running", False))
        self.locked = bool(self.settings.get("locked", False))
        self.always_on_top = bool(self.settings.get("always_on_top", True))
        self.topmost_var = tk.BooleanVar(value=self.always_on_top)
        self.locked_var = tk.BooleanVar(value=self.locked)
        self.drag_offset = (0, 0)
        self.last_tick = time.monotonic()

        self.palette = {
            "bg": "#14161a",
            "panel": "#1d2027",
            "text": "#f2f5f8",
            "muted": "#9aa5b1",
            "focus": "#46c2a8",
            "break": "#f2b84b",
            "danger": "#ff6b6b",
            "button": "#2b3039",
            "button_hover": "#38404d",
        }

        self.build_ui()
        self.build_menu()
        self.apply_topmost()
        self.place_window()
        self.bind_events()
        self.update_view()
        self.tick()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

    def load_settings(self) -> dict:
        try:
            return json.loads(self.settings_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_settings(self) -> None:
        data = {
            "mode": self.mode,
            "mode_key": self.mode_key,
            "duration": self.duration,
            "remaining": self.remaining,
            "focus_seconds": self.focus_seconds,
            "short_break_seconds": self.short_break_seconds,
            "long_break_seconds": self.long_break_seconds,
            "running": self.running,
            "locked": self.locked,
            "always_on_top": self.always_on_top,
            "x": self.root.winfo_x(),
            "y": self.root.winfo_y(),
        }
        try:
            self.settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def build_ui(self) -> None:
        self.frame = tk.Frame(
            self.root,
            bg=self.palette["panel"],
            highlightthickness=1,
            highlightbackground="#303642",
        )
        self.frame.pack(fill="both", expand=True)

        self.mode_label = tk.Label(
            self.frame,
            bg=self.palette["panel"],
            fg=self.palette["focus"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        )
        self.mode_label.place(x=12, y=6, width=74, height=14)

        self.time_label = tk.Label(
            self.frame,
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI Semibold", 19),
            anchor="w",
        )
        self.time_label.place(x=11, y=18, width=84, height=30)

        self.start_button = self.make_button("Start", self.toggle)
        self.start_button.place(x=95, y=9, width=47, height=19)

        self.reset_button = self.make_button("Reset", self.reset)
        self.reset_button.place(x=95, y=31, width=47, height=19)

        self.skip_button = self.make_button(">>", self.skip_phase)
        self.skip_button.configure(font=("Segoe UI Semibold", 8))
        self.skip_button.place(x=148, y=9, width=23, height=41)

        self.settings_button = self.make_button("\u2699", self.open_settings)
        self.settings_button.configure(font=("Segoe UI Symbol", 9))
        self.settings_button.place(x=177, y=9, width=23, height=19)

        self.close_button = self.make_button("X", self.quit)
        self.close_button.configure(bg="#3a2630", fg="#ffd7de", font=("Segoe UI Semibold", 8))
        self.close_button.place(x=177, y=31, width=23, height=19)

    def make_button(self, text: str, command) -> tk.Label:
        label = tk.Label(
            self.frame,
            text=text,
            bg=self.palette["button"],
            fg=self.palette["text"],
            font=("Segoe UI", 8),
            cursor="hand2",
        )
        label.bind("<Button-1>", lambda _event: command())
        label.bind("<Enter>", lambda _event: label.configure(bg=self.palette["button_hover"]))
        label.bind("<Leave>", lambda _event: label.configure(bg=self.palette["button"]))
        return label

    def build_menu(self) -> None:
        self.menu = tk.Menu(self.root, tearoff=False, bg="#222733", fg="#f2f5f8")
        self.menu.add_command(label="Start / Pause", command=self.toggle)
        self.menu.add_command(label="Reset", command=self.reset)
        self.menu.add_command(label="Skip to next", command=self.skip_phase)
        self.menu.add_separator()
        self.menu.add_command(label="", command=lambda: self.set_mode("focus"))
        self.menu.add_command(label="", command=lambda: self.set_mode("short_break"))
        self.menu.add_command(label="", command=lambda: self.set_mode("long_break"))
        self.menu.add_separator()
        self.menu.add_command(label="Settings", command=self.open_settings)
        self.menu.add_checkbutton(label="Always on top", variable=self.topmost_var, command=self.toggle_topmost)
        self.menu.add_checkbutton(label="Lock position", variable=self.locked_var, command=self.toggle_lock)
        self.menu.add_separator()
        self.menu.add_command(label="Quit", command=self.quit)

    def bind_events(self) -> None:
        for widget in (self.root, self.frame, self.mode_label, self.time_label):
            widget.bind("<ButtonPress-1>", self.start_drag)
            widget.bind("<B1-Motion>", self.drag)
            widget.bind("<ButtonRelease-1>", lambda _event: self.save_settings())
            widget.bind("<Double-Button-1>", lambda _event: self.toggle())
            widget.bind("<Button-3>", self.show_menu)

    def place_window(self) -> None:
        width, height = 211, 58
        self.root.geometry(f"{width}x{height}")
        saved_x = self.settings.get("x")
        saved_y = self.settings.get("y")
        if isinstance(saved_x, int) and isinstance(saved_y, int):
            x, y = saved_x, saved_y
        else:
            left, top, right, bottom = get_work_area(self.root)
            x = right - width - 12
            y = bottom - height - 10
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def start_drag(self, event) -> None:
        if self.locked:
            return
        self.drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def drag(self, event) -> None:
        if self.locked:
            return
        dx, dy = self.drag_offset
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def show_menu(self, event) -> None:
        self.topmost_var.set(self.always_on_top)
        self.locked_var.set(self.locked)
        self.menu.entryconfig(4, label=f"Focus - {self.format_duration(self.focus_seconds)}")
        self.menu.entryconfig(5, label=f"Short break - {self.format_duration(self.short_break_seconds)}")
        self.menu.entryconfig(6, label=f"Long break - {self.format_duration(self.long_break_seconds)}")
        self.menu.tk_popup(event.x_root, event.y_root)

    def toggle(self) -> None:
        self.running = not self.running
        self.last_tick = time.monotonic()
        self.update_view()
        self.save_settings()

    def reset(self) -> None:
        self.running = False
        self.remaining = self.duration
        self.update_view()
        self.save_settings()

    def skip_phase(self) -> None:
        was_running = self.running
        next_mode = "short_break" if self.mode_key == "focus" else "focus"
        self.mode_key = next_mode
        self.mode = self.mode_name(next_mode)
        self.duration = self.duration_for_key(next_mode)
        self.remaining = self.duration
        self.running = was_running
        self.last_tick = time.monotonic()
        self.update_view()
        self.save_settings()

    def set_mode(self, mode_key: str) -> None:
        self.mode_key = mode_key
        self.mode = self.mode_name(mode_key)
        self.duration = self.duration_for_key(mode_key)
        self.remaining = self.duration
        self.running = False
        self.update_view()
        self.save_settings()

    def open_settings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Pomodoro Settings")
        dialog.configure(bg=self.palette["panel"])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.attributes("-topmost", self.always_on_top)

        fields = [
            ("Focus", "focus", self.focus_seconds),
            ("Short break", "short_break", self.short_break_seconds),
            ("Long break", "long_break", self.long_break_seconds),
        ]
        entries = {}

        title = tk.Label(
            dialog,
            text="Timer lengths",
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI Semibold", 11),
            anchor="w",
        )
        title.grid(row=0, column=0, columnspan=5, sticky="ew", padx=14, pady=(12, 6))

        for row, (label_text, key, total_seconds) in enumerate(fields, start=1):
            minutes, seconds = divmod(total_seconds, 60)
            tk.Label(
                dialog,
                text=label_text,
                bg=self.palette["panel"],
                fg=self.palette["text"],
                font=("Segoe UI", 9),
                anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=(14, 8), pady=5)
            minute_entry = tk.Spinbox(dialog, from_=0, to=999, width=5, font=("Segoe UI", 9))
            second_entry = tk.Spinbox(dialog, from_=0, to=59, width=4, font=("Segoe UI", 9), format="%02.0f")
            minute_entry.delete(0, "end")
            second_entry.delete(0, "end")
            minute_entry.insert(0, str(minutes))
            second_entry.insert(0, f"{seconds:02d}")
            minute_entry.grid(row=row, column=1, sticky="w", pady=5)
            tk.Label(dialog, text="min", bg=self.palette["panel"], fg=self.palette["muted"], font=("Segoe UI", 8)).grid(row=row, column=2, padx=(4, 10), pady=5)
            second_entry.grid(row=row, column=3, sticky="w", pady=5)
            tk.Label(dialog, text="sec", bg=self.palette["panel"], fg=self.palette["muted"], font=("Segoe UI", 8)).grid(row=row, column=4, padx=(4, 14), pady=5)
            entries[key] = (minute_entry, second_entry)

        buttons = tk.Frame(dialog, bg=self.palette["panel"])
        buttons.grid(row=4, column=0, columnspan=5, sticky="e", padx=14, pady=(8, 14))
        cancel_button = tk.Button(buttons, text="Cancel", command=dialog.destroy, relief="flat")
        save_button = tk.Button(buttons, text="Save", command=lambda: self.save_timer_settings(dialog, entries), relief="flat")
        cancel_button.pack(side="left", padx=(0, 8))
        save_button.pack(side="left")

        dialog.update_idletasks()
        x = self.root.winfo_x() - dialog.winfo_width() + self.root.winfo_width()
        y = self.root.winfo_y() - dialog.winfo_height() - 8
        if y < 0:
            y = self.root.winfo_y() + self.root.winfo_height() + 8
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.grab_set()
        minute_first, _second_first = entries["focus"]
        minute_first.focus_set()

    def save_timer_settings(self, dialog: tk.Toplevel, entries: dict) -> None:
        try:
            values = {}
            for key, (minute_entry, second_entry) in entries.items():
                minutes = int(minute_entry.get())
                seconds = int(second_entry.get())
                if minutes < 0 or seconds < 0 or seconds > 59:
                    raise ValueError
                total = minutes * 60 + seconds
                if total <= 0:
                    raise ValueError
                values[key] = total
        except ValueError:
            messagebox.showerror(APP_NAME, "Enter positive timer lengths. Seconds must be 0 through 59.")
            return

        self.focus_seconds = values["focus"]
        self.short_break_seconds = values["short_break"]
        self.long_break_seconds = values["long_break"]
        self.duration = self.duration_for_key(self.mode_key)
        if self.running:
            self.remaining = min(self.remaining, self.duration)
        else:
            self.remaining = self.duration
        self.update_view()
        self.save_settings()
        dialog.destroy()

    def toggle_topmost(self) -> None:
        self.always_on_top = self.topmost_var.get()
        self.apply_topmost()
        self.save_settings()

    def toggle_lock(self) -> None:
        self.locked = self.locked_var.get()
        self.save_settings()

    def apply_topmost(self) -> None:
        self.root.attributes("-topmost", self.always_on_top)

    def duration_for_key(self, mode_key: str) -> int:
        if mode_key == "short_break":
            return self.short_break_seconds
        if mode_key == "long_break":
            return self.long_break_seconds
        return self.focus_seconds

    def mode_name(self, mode_key: str) -> str:
        if mode_key == "short_break":
            return "Short break"
        if mode_key == "long_break":
            return "Long break"
        return "Focus"

    def format_duration(self, total_seconds: int) -> str:
        minutes, seconds = divmod(total_seconds, 60)
        if seconds:
            return f"{minutes}:{seconds:02d}"
        return f"{minutes} minutes"

    def tick(self) -> None:
        now = time.monotonic()
        if self.running:
            elapsed = int(now - self.last_tick)
            if elapsed > 0:
                self.remaining = max(0, self.remaining - elapsed)
                self.last_tick = now
                if self.remaining == 0:
                    self.running = False
                    self.update_view()
                    self.alert_done()
                    self.save_settings()
        self.update_view()
        self.root.after(250, self.tick)

    def alert_done(self) -> None:
        if sys.platform == "win32":
            try:
                import winsound

                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass
        self.root.lift()
        messagebox.showinfo(APP_NAME, f"{self.mode} timer finished.")

    def update_view(self) -> None:
        minutes, seconds = divmod(max(0, self.remaining), 60)
        accent = self.palette["focus"] if self.mode == "Focus" else self.palette["break"]
        self.mode_label.configure(text=self.mode.upper(), fg=accent)
        self.time_label.configure(text=f"{minutes:02d}:{seconds:02d}")
        self.start_button.configure(text="Pause" if self.running else "Start")
        self.root.title(f"{minutes:02d}:{seconds:02d} - {APP_NAME}")

    def quit(self) -> None:
        self.save_settings()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    PomodoroPill().run()
