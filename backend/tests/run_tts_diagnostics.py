#!/usr/bin/env python3
"""
Vāṇī TTS Diagnostic Utility for NARAD.
Validates local environment, Chatterbox Multilingual availability, and sample generation.

Usage:
  python backend/tests/run_tts_diagnostics.py
"""
import sys
import os
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.tts.manager import tts_manager, DIAGNOSTIC_SAMPLES


def main():
    print("=" * 65)
    print("NARAD V1 — VĀṆĪ LOCAL TTS DIAGNOSTIC UTILITY")
    print("=" * 65)
    print(f"Current Python Runtime : {sys.version.split()[0]} ({sys.executable})")

    status = tts_manager.get_status()
    print("\n[TELEMETRY STATUS]")
    print(f"  • Provider           : {status.provider.upper()}")
    print(f"  • Mode               : {status.mode.upper()}")
    print(f"  • Installed          : {status.installed}")
    print(f"  • Model Loaded       : {status.model_loaded}")
    print(f"  • Ready for Audio    : {status.ready}")
    print(f"  • Target Device      : {status.device.upper()}")
    print(f"  • Supported Langs    : {', '.join(status.supported_languages)}")
    print(f"  • Fallback Active    : {status.active_fallback}")
    print(f"  • Fallback Provider  : {status.fallback_provider}")

    if status.error:
        print(f"\n[DIAGNOSTIC NOTICE / LIMITATION]")
        print(f"  {status.error}")

    print("\n[REQUIRED TEST PHRASES]")
    for key, item in DIAGNOSTIC_SAMPLES.items():
        print(f"  [{key.upper()}] ({item['lang']}):")
        print(f"    Text: \"{item['text']}\"")
        print(f"    Desc: {item['description']}")

    if not status.ready:
        print("\n" + "=" * 65)
        print("RESULT: Engine is in graceful FALLBACK mode.")
        print("Vāṇī will speak using browser Web Speech API until Chatterbox is installed.")
        print("To enable full local Chatterbox neural audio:")
        print("  1. Ensure Python >= 3.10 is active (recommended: Python 3.11).")
        print("  2. pip install torch torchaudio chatterbox-tts")
        print("=" * 65)
        return 0
    else:
        print("\n" + "=" * 65)
        print("RESULT: Chatterbox Multilingual local engine is READY!")
        print("=" * 65)
        return 0


if __name__ == "__main__":
    sys.exit(main())
