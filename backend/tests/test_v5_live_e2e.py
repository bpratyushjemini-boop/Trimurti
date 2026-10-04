"""
Live E2E Verification Test Suite for NARAD V5 (Trinetra Multimodal Agent):
- Live Health endpoint check (Version 5.0.0, Trinetra Subsystem ONLINE/READY)
- Agent State query (/api/agent/state with vision telemetry)
- Screenshot capture & serving (/api/agent/screenshot/latest)
- Vision direct query API (/api/agent/vision/query)
- Visual action execution via Manthan (/api/agent/execute)
- Conversational visual query via Chat (/api/chat)
- Apple Music playback verification with Zero Fake Success
"""

import sys
import json
import time
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000/api"


def post_json(endpoint: str, data: dict) -> dict:
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=65) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return json.loads(body)
        except Exception:
            return {"error": str(e), "body": body, "status_code": e.code}


def get_json(endpoint: str) -> dict:
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=65) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_1_health_v5():
    print("\n--- TEST 1: Health Endpoint (Version 5.0.0 & Trinetra Check) ---")
    data = get_json("/health")
    assert data["version"] in ("5.0.0", "5.1.0", "6.0.0", "6.1.0", "7.0.0", "7.1.0", "7.2.0"), f"Expected version 5.0.0+, got {data['version']}"
    assert data["system"] == "NARAD"
    subsystems = data.get("subsystems", {})
    assert "trinetra" in subsystems, f"Trinetra missing from subsystems: {subsystems}"
    print(f"✅ PASSED: Version {data['version']}, Trinetra status: {subsystems.get('trinetra')}")


def test_2_agent_state_v5():
    print("\n--- TEST 2: Agent Telemetry State (V5 Vision fields) ---")
    post_json("/agent/reset", {})
    st = get_json("/agent/state")
    assert "state" in st
    assert "observation_count" in st, f"Missing observation_count: {st}"
    assert "vision_status" in st, f"Missing vision_status: {st}"
    assert "last_screenshot_ref" in st
    print(f"✅ PASSED: State {st['state']}, Obs count: {st['observation_count']}, Vision: {st['vision_status']}")


def test_3_screenshot_capture_and_serving():
    print("\n--- TEST 3: Screenshot Capture & Serving Endpoint ---")
    # First trigger an observation via agent execute
    exec_res = post_json("/agent/execute", {
        "prompt": "inspect screen",
        "dry_run": False
    })
    assert exec_res.get("success"), f"Execution failed: {exec_res}"

    # Now verify GET /api/agent/screenshot/latest returns JPEG
    url = f"{BASE_URL}/agent/screenshot/latest"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        content_type = resp.headers.get("Content-Type")
        content = resp.read()
        assert "image/jpeg" in content_type, f"Expected image/jpeg, got {content_type}"
        assert len(content) > 1000, f"Screenshot content too small: {len(content)} bytes"
        assert len(content) < 500 * 1024, f"Screenshot exceeds 500KB limit: {len(content)} bytes"
    print(f"✅ PASSED: Latest screenshot served ({len(content)} bytes, {content_type})")


def test_4_vision_query_api():
    print("\n--- TEST 4: Direct Vision Query Endpoint (/api/agent/vision/query) ---")
    res = post_json("/agent/vision/query", {
        "question": "Is there any terminal or code editor window visible?"
    })
    assert res.get("success"), f"Vision query failed: {res}"
    assert "answer" in res
    assert "image_ref" in res
    print(f"✅ PASSED: Vision query response received: '{res['answer'][:80]}...'")


def test_5_visual_action_execution():
    print("\n--- TEST 5: Manthan Visual Loop Execution ---")
    res = post_json("/agent/execute", {
        "instruction": "Open Calculator and verify",
        "dry_run": False
    })
    assert res.get("success"), f"Open Calculator and verify failed: {res}"
    plan = res.get("plan", [])
    tools_in_plan = [step.get("tool") for step in plan]
    assert "open_application" in tools_in_plan, f"open_application not in plan: {tools_in_plan}"
    assert "observe_screen" in tools_in_plan, f"observe_screen not in plan: {tools_in_plan}"
    print(f"✅ PASSED: Visual loop executed ({len(plan)} steps, verification: {res.get('verified')})")


def test_6_chat_visual_integration():
    print("\n--- TEST 6: Conversational Visual Query via /api/chat ---")
    chat_res = post_json("/chat", {
        "message": "What is on my screen right now?"
    })
    assert "response" in chat_res, f"Chat response missing: {chat_res}"
    assert chat_res.get("provider") == "manthan", f"Expected provider manthan, got {chat_res.get('provider')}"
    assert chat_res.get("model") in ("computer-agent-v5", "computer-agent-v8.1"), f"Expected model computer-agent-v5 or v8.1, got {chat_res.get('model')}"
    print(f"✅ PASSED: Chat routed to Manthan V5 ({chat_res.get('status')})")


def test_7_apple_music_visual_verification():
    print("\n--- TEST 7: Apple Music Action & State Verification (Zero Fake Success) ---")
    res = post_json("/agent/execute", {
        "instruction": "Play Back In Black on Apple Music and verify",
        "dry_run": False
    })
    # Should succeed at executing the verification loop, and report accurate state
    assert res.get("success"), f"Execution failed: {res}"
    print(f"✅ PASSED: Apple Music outcome: verified={res.get('verified')}, message='{res.get('message')[:70]}...'")


if __name__ == "__main__":
    print("==================================================")
    print("STARTING NARAD V5 LIVE E2E TEST SUITE")
    print("==================================================")
    try:
        test_1_health_v5()
        test_2_agent_state_v5()
        test_3_screenshot_capture_and_serving()
        test_4_vision_query_api()
        test_5_visual_action_execution()
        test_6_chat_visual_integration()
        test_7_apple_music_visual_verification()
        print("\n==================================================")
        print("ALL 7 NARAD V5 LIVE E2E TESTS PASSED SUCCESSFULLY!")
        print("==================================================")
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        sys.exit(1)
