# Taskbar Pomodoro

A small Windows desktop Pomodoro countdown that docks near the taskbar like a glanceable taskbar widget.

## Run it

Double-click `start_taskbar_pomodoro.bat`.

If Windows asks what app to use, run this from PowerShell instead:

```powershell
pythonw .\taskbar_pomodoro.py
```

## Controls

- Click `Start` to begin or pause.
- Click `Reset` to restart the current timer.
- Click `>>` to skip from Focus to Short Break, or from any break back to Focus.
- Click the gear button to set exact focus, short break, and long break times.
- Click `X` to completely close the app.
- Double-click the pill to start or pause.
- Drag the pill to move it.
- Right-click for Focus, Short Break, Long Break, skip, settings, lock position, always-on-top, and quit.

The app remembers its position and timer state in your Windows app data folder.
