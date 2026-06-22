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

        self.mode = self.settings.get("mode", "Focus")
        self.duration = int(self.settings.get("duration", FOCUS_SECONDS))
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
            "duration": self.duration,
            "remaining": self.remaining,
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
        self.mode_label.place(x=12, y=6, width=82, height=14)

        self.time_label = tk.Label(
            self.frame,
            bg=self.palette["panel"],
            fg=self.palette["text"],
            font=("Segoe UI Semibold", 19),
            anchor="w",
        )
        self.time_label.place(x=11, y=18, width=88, height=30)

        self.start_button = self.make_button("Start", self.toggle)
        self.start_button.place(x=102, y=9, width=55, height=19)

        self.reset_button = self.make_button("Reset", self.reset)
        self.reset_button.place(x=102, y=31, width=55, height=19)

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
        self.menu.add_separator()
        self.menu.add_command(label="Focus - 25 minutes", command=lambda: self.set_mode("Focus", FOCUS_SECONDS))
        self.menu.add_command(label="Short break - 5 minutes", command=lambda: self.set_mode("Break", SHORT_BREAK_SECONDS))
        self.menu.add_command(label="Long break - 15 minutes", command=lambda: self.set_mode("Break", LONG_BREAK_SECONDS))
        self.menu.add_separator()
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
        width, height = 168, 58
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

    def set_mode(self, mode: str, duration: int) -> None:
        self.mode = mode
        self.duration = duration
        self.remaining = duration
        self.running = False
        self.update_view()
        self.save_settings()

    def toggle_topmost(self) -> None:
        self.always_on_top = self.topmost_var.get()
        self.apply_topmost()
        self.save_settings()

    def toggle_lock(self) -> None:
        self.locked = self.locked_var.get()
        self.save_settings()

    def apply_topmost(self) -> None:
        self.root.attributes("-topmost", self.always_on_top)

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
