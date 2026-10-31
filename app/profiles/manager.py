"""
Profile Manager for DualSense & DualSense Edge.
Manages stick response curves, deadzones, trigger hair-trigger thresholds,
button remappings (including Edge back paddles), and slot assignments.
"""

import json
import os
from typing import Dict, Any, List, Optional

DEFAULT_PROFILES = [
    {
        "id": "default",
        "name": "Standard / Predefinito",
        "description": "Risposta lineare standard 1:1, ideale per giochi d'avventura e uso generale.",
        "curve_type": "Linear",
        "left_stick": {
            "curve": "Linear",
            "deadzone": 2,
            "anti_deadzone": 0,
            "max_threshold": 100
        },
        "right_stick": {
            "curve": "Linear",
            "deadzone": 2,
            "anti_deadzone": 0,
            "max_threshold": 100
        },
        "triggers": {
            "l2_deadzone": 0,
            "l2_threshold": 100,
            "r2_deadzone": 0,
            "r2_threshold": 100
        },
        "vibration_intensity": 100, # 0, 50, 75, 100
        "trigger_effect_intensity": 100,
        "lightbar": {"r": 0, "g": 112, "b": 240},
        "button_mappings": {
            "back_left": "cross",
            "back_right": "square"
        }
    },
    {
        "id": "fps_competitive",
        "name": "FPS Competitivo (Rapido / Hair Trigger)",
        "description": "Ottimizzato per shooter (CoD, Apex, Warzone). Grilletti istantanei e curva rapida.",
        "curve_type": "Quick",
        "left_stick": {
            "curve": "Quick",
            "deadzone": 1,
            "anti_deadzone": 5,
            "max_threshold": 95
        },
        "right_stick": {
            "curve": "Precise",
            "deadzone": 1,
            "anti_deadzone": 3,
            "max_threshold": 98
        },
        "triggers": {
            "l2_deadzone": 0,
            "l2_threshold": 15, # Hair trigger: attiva al 15% di pressione
            "r2_deadzone": 0,
            "r2_threshold": 10  # Hair trigger per sparo istantaneo
        },
        "vibration_intensity": 50, # Ridotto per non disturbare la mira
        "trigger_effect_intensity": 0,
        "lightbar": {"r": 255, "g": 30, "b": 30},
        "button_mappings": {
            "back_left": "cross",   # Salto
            "back_right": "circle"  # Scivolata / Crouch
        }
    },
    {
        "id": "sniper_precise",
        "name": "Precisione / Cecchino (Preciso)",
        "description": "Bassa sensibilità nei movimenti minimi per micro-correzioni e mira a lungo raggio.",
        "curve_type": "Precise",
        "left_stick": {
            "curve": "Linear",
            "deadzone": 3,
            "anti_deadzone": 0,
            "max_threshold": 100
        },
        "right_stick": {
            "curve": "Precise",
            "deadzone": 2,
            "anti_deadzone": 0,
            "max_threshold": 100
        },
        "triggers": {
            "l2_deadzone": 5,
            "l2_threshold": 90,
            "r2_deadzone": 5,
            "r2_threshold": 80
        },
        "vibration_intensity": 75,
        "trigger_effect_intensity": 50,
        "lightbar": {"r": 0, "g": 230, "b": 180},
        "button_mappings": {
            "back_left": "l3",
            "back_right": "r3"
        }
    },
    {
        "id": "racing_smooth",
        "name": "Sim Racing & Guida",
        "description": "Curva costante per sterzate fluide e progressione completa della corsa dei grilletti.",
        "curve_type": "Steady",
        "left_stick": {
            "curve": "Steady",
            "deadzone": 3,
            "anti_deadzone": 0,
            "max_threshold": 100
        },
        "right_stick": {
            "curve": "Linear",
            "deadzone": 5,
            "anti_deadzone": 0,
            "max_threshold": 100
        },
        "triggers": {
            "l2_deadzone": 0, # Freno dosabile
            "l2_threshold": 100,
            "r2_deadzone": 0, # Acceleratore progressivo
            "r2_threshold": 100
        },
        "vibration_intensity": 100,
        "trigger_effect_intensity": 100,
        "lightbar": {"r": 255, "g": 140, "b": 0},
        "button_mappings": {
            "back_left": "l1", # Cambio marcia giù
            "back_right": "r1" # Cambio marcia su
        }
    }
]


class ProfileManager:
    """Manages saving, loading, editing and slot assignment for controller profiles."""

    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.profiles: List[Dict[str, Any]] = []
        self.slots: Dict[str, Optional[str]] = {
            "slot_1": "default",
            "slot_2": "fps_competitive",
            "slot_3": "sniper_precise",
            "slot_4": "racing_smooth"
        }
        self.active_slot: str = "slot_1"
        self.load()

    def load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.profiles = data.get("profiles", DEFAULT_PROFILES)
                    self.slots = data.get("slots", self.slots)
                    self.active_slot = data.get("active_slot", "slot_1")
                    return
            except Exception:
                pass
        self.profiles = [dict(p) for p in DEFAULT_PROFILES]
        self.save()

    def save(self):
        data = {
            "profiles": self.profiles,
            "slots": self.slots,
            "active_slot": self.active_slot
        }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_all_profiles(self) -> List[Dict[str, Any]]:
        return self.profiles

    def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        for p in self.profiles:
            if p["id"] == profile_id:
                return p
        return None

    def save_profile(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        pid = profile_data.get("id")
        for i, p in enumerate(self.profiles):
            if p["id"] == pid:
                self.profiles[i] = profile_data
                self.save()
                return profile_data

        # New profile
        if not pid:
            pid = f"profile_{len(self.profiles) + 1}"
            profile_data["id"] = pid

        self.profiles.append(profile_data)
        self.save()
        return profile_data

    def delete_profile(self, profile_id: str) -> bool:
        if profile_id == "default":
            return False # Protect default
        self.profiles = [p for p in self.profiles if p["id"] != profile_id]
        # Clear slots if referenced
        for k, v in self.slots.items():
            if v == profile_id:
                self.slots[k] = "default"
        self.save()
        return True

    def assign_slot(self, slot_key: str, profile_id: str) -> bool:
        if slot_key in self.slots and self.get_profile(profile_id):
            self.slots[slot_key] = profile_id
            self.save()
            return True
        return False

    def set_active_slot(self, slot_key: str) -> Optional[Dict[str, Any]]:
        if slot_key in self.slots:
            self.active_slot = slot_key
            self.save()
            target_profile_id = self.slots[slot_key]
            return self.get_profile(target_profile_id)
        return None
