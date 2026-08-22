"""
Vivy AI — Action System: Windows System Adapter
===============================================
Encapsulates OS-level Windows API input interactions (SendInput / ctypes).
Used by system_executor.py to avoid coupling the executor to Win32 mechanics.
"""

import logging

logger = logging.getLogger(__name__)

class WindowsSystemAdapter:
    @staticmethod
    def send_shortcut(action: str) -> tuple[bool, str]:
        """
        Translates a system action string into the appropriate Win32 keybd_event sequence.
        """
        try:
            import ctypes
            VK_LWIN = 0x5B
            VK_CONTROL = 0x11
            VK_MENU = 0x12 # Alt
            VK_SHIFT = 0x10
            VK_LEFT = 0x25
            VK_RIGHT = 0x27
            VK_D = 0x44
            VK_TAB = 0x09
            VK_ESCAPE = 0x1B
            VK_RETURN = 0x0D
            VK_SNAPSHOT = 0x2C # Print Screen
            VK_VOLUME_MUTE = 0xAD
            VK_VOLUME_DOWN = 0xAE
            VK_VOLUME_UP = 0xAF
            VK_MEDIA_NEXT_TRACK = 0xB0
            VK_MEDIA_PREV_TRACK = 0xB1
            VK_MEDIA_PLAY_PAUSE = 0xB3
            
            KEYEVENTF_KEYUP = 0x0002
            KEYEVENTF_EXTENDEDKEY = 0x0001

            if action == "show_desktop":
                ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_D, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_D, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
                return True, "Showing desktop."

            elif action == "previous_desktop":
                ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_LEFT, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_LEFT, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
                return True, "Switched to previous desktop."

            elif action == "next_desktop":
                ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_RIGHT, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_RIGHT, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
                return True, "Switched to next desktop."
                
            elif action == "task_view":
                ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_TAB, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_TAB, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
                return True, "Opened Task View."
                
            elif action == "next_app":
                # Alt + Esc switches to next window directly
                ctypes.windll.user32.keybd_event(VK_MENU, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
                return True, "Switched to next app."
                
            elif action == "previous_app":
                # Alt + Shift + Esc switches to previous window directly
                ctypes.windll.user32.keybd_event(VK_MENU, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_SHIFT, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
                return True, "Switched to previous app."
                
            elif action == "screenshot":
                ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_SHIFT, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x53, 0, 0, 0) # 'S' key
                ctypes.windll.user32.keybd_event(0x53, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
                return True, "Triggered screenshot tool."
                
            elif action == "volume_up":
                ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, KEYEVENTF_KEYUP, 0)
                return True, "Volume Up."
                
            elif action == "volume_down":
                ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, KEYEVENTF_KEYUP, 0)
                return True, "Volume Down."
                
            elif action == "mute_toggle":
                ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, KEYEVENTF_KEYUP, 0)
                return True, "Mute toggled."
                
            elif action == "escape" or action == "cancel":
                ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
                return True, "Escape pressed."
                
            elif action == "confirm" or action == "like":
                ctypes.windll.user32.keybd_event(VK_RETURN, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
                return True, "Enter pressed."

            elif action == "task_view_prev":
                # Left Arrow navigates thumbnails natively (requires EXTENDEDKEY flag)
                ctypes.windll.user32.keybd_event(VK_LEFT, 0, KEYEVENTF_EXTENDEDKEY, 0)
                ctypes.windll.user32.keybd_event(VK_LEFT, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
                return True, "Task View: Prev (Left Arrow)."

            elif action == "task_view_next":
                # Right Arrow navigates thumbnails natively (requires EXTENDEDKEY flag)
                ctypes.windll.user32.keybd_event(VK_RIGHT, 0, KEYEVENTF_EXTENDEDKEY, 0)
                ctypes.windll.user32.keybd_event(VK_RIGHT, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
                return True, "Task View: Next (Right Arrow)."

            elif action == "task_view_select":
                # Enter selects the focused thumbnail in Task View
                ctypes.windll.user32.keybd_event(VK_RETURN, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
                return True, "Task View: Selected."

            elif action == "scroll_up":
                # MOUSEEVENTF_WHEEL = 0x0800, dwData = 120 (one wheel notch up)
                ctypes.windll.user32.mouse_event(0x0800, 0, 0, 120, 0)
                return True, "Scrolled Up."

            elif action == "scroll_down":
                # MOUSEEVENTF_WHEEL = 0x0800, dwData = -120 (one wheel notch down)
                ctypes.windll.user32.mouse_event(0x0800, 0, 0, -120, 0)
                return True, "Scrolled Down."

            elif action == "click":
                # MOUSEEVENTF_LEFTDOWN = 0x0002, MOUSEEVENTF_LEFTUP = 0x0004
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                return True, "Mouse Clicked."

            else:
                return False, f"Unsupported adapter action: {action}"
        except Exception as e:
            logger.error(f"[WindowsSystemAdapter] Error: {e}")
            return False, str(e)
