import http.server
import os
import sys

# Setup mock objects for the server to start without hardware
class MockControllerManager:
    def get_status(self): return {"connected": False, "model": "DualSense Edge V2"}
    def get_inputs(self): return {}
    def set_lightbar(self, r, g, b): pass
    def set_rumble(self, l, r, d): pass
    def set_player_led(self, n): pass

class MockProfileManager:
    def __init__(self):
        self.slots = {"slot_1": None, "slot_2": None, "slot_3": None, "slot_4": None}
        self.active_slot = None
    def get_all_profiles(self): return []
    def save_profile(self, data): return data
    def delete_profile(self, pid): return True
    def assign_slot(self, slot, pid): return True
    def set_active_slot(self, slot): return None

# Import the handler and server creation logic
sys.path.append(os.path.dirname(__file__))
from server import create_server

# Start server on 0.0.0.0:8080
if __name__ == "__main__":
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    server = create_server("0.0.0.0", 8080, MockControllerManager(), MockProfileManager(), static_dir)
    print("Starting Preview Server V2.0 on port 8080...")
    server.serve_forever()
