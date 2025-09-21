# demo_run.py
# Example usage / demo launcher for the GameFullUI in `game_full_ui.py`.
# Put this file next to your game_full_ui.py and run it.
#
# This demo does two things:
# - If you press any key or click, you can take manual control at any time.
# - Otherwise, a short automated sequence will run:
#     2s -> Start (enter playing)
#     5s -> Open Pause menu
#     8s -> Resume
#    11s -> Open Options panel
#    15s -> Quit
#
# Note: GUI must run in the main thread. We use timers that only set state flags.
import time
import threading
import os
import sys

# import the UI class you created earlier
# Make sure game_full_ui.py exports GameFullUI (the class name used in prior samples).
# If your file has a different class name, adjust the import below.
from window_gui import GameFullUI

class AutoDemo:
    def __init__(self, app: GameFullUI):
        self.app = app
        self.timers = []

    def schedule(self, delay, fn, *a, **kw):
        t = threading.Timer(delay, fn, args=a, kwargs=kw)
        t.daemon = True
        t.start()
        self.timers.append(t)

    def start_sequence(self):
        # 2s: start the game (move from Home/Menu to Playing)
        self.schedule(2.0, self._safe_call, self.app.start_game)
        # 5s: open pause menu
        self.schedule(5.0, self._safe_call, self._open_pause)
        # 8s: resume
        self.schedule(8.0, self._safe_call, self.app.resume_from_pause if hasattr(self.app, 'resume_from_pause') else self._resume_fallback)
        # 11s: open options
        self.schedule(11.0, self._safe_call, self._open_options)
        # 15s: quit
        self.schedule(15.0, self._safe_call, self.app.quit_game)

    def _safe_call(self, fn, *a, **kw):
        """
        We only call thread-safe setters on the app.
        Avoid calling internal GL functions from this background thread.
        """
        try:
            fn(*a, **kw)
        except Exception as e:
            print("AutoDemo: error calling", fn, e)

    def _open_pause(self):
        # toggle pause & open pause menu if available
        if hasattr(self.app, "paused"):
            self.app.paused = True
        if hasattr(self.app, "pause_menu_open"):
            self.app.pause_menu_open = True

    def _resume_fallback(self):
        if hasattr(self.app, "paused"):
            self.app.paused = False
        if hasattr(self.app, "pause_menu_open"):
            self.app.pause_menu_open = False

    def _open_options(self):
        # open options panel
        if hasattr(self.app, "show_options"):
            self.app.show_options = True

def run_manual_or_auto_demo():
    # create the GameFullUI (or your class name)
    app = GameFullUI(1280, 720, "Demo - Full OpenGL UI")

    # create auto-demo and schedule actions
    demo = AutoDemo(app)
    demo.start_sequence()

    # Run the app. The app's run() uses a main loop that polls attributes we mutate above.
    # If you interact manually (mouse/keyboard/gamepad), your actions will override the demo state.
    app.run()

if __name__ == "__main__":
    run_manual_or_auto_demo()
