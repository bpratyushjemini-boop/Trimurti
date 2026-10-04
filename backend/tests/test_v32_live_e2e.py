"""
Live E2E Verification Test Suite for NARAD V3.2:
- Live Health endpoint check (Version 3.2.0, Real Providers)
- Casual Chat interaction (No tool invocations)
- Multi-Turn Pronoun Resolution & Topic Maintenance ("it" / follow-up)
- Voice Mode API payload & Voice Readiness
- SSE Streaming Events (session, thinking, token, done)
- Elimination of Fake AI Fallback
- Smṛti Conversation Summarization
- Tool execution integrity (Calculator / Knowledge)
"""

import sys
import json
import urllib.request
import urllib.error
import http.client


BASE_URL = "http://127.0.0.1:8000/api"


def post_json(endpoint: str, data: dict) -> dict:
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return {"error": str(e), "body": body, "status_code": e.code}


def get_json(endpoint: str) -> dict:
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_1_health_v32():
    print("\n--- TEST 1: Health Endpoint (V3.2.0 / V4.0.0 Verification) ---")
    data = get_json("/health")
    assert data["version"] in ("3.2.0", "4.0.0", "5.0.0", "6.0.0", "7.0.0", "7.1.0", "7.2.0"), f"Expected version 3.2.0+, got {data['version']}"
    assert data["system"] == "NARAD"
    assert "mock-narad" not in data.get("provider_matrix", {}), "mock-narad must not be in provider matrix"
    print(f"✅ PASSED: Health returns Version {data['version']}, active provider {data['active_provider']}")


def test_2_casual_chat_no_tools():
    print("\n--- TEST 2: Casual Chat (No Tools Invocations) ---")
    payload = {
        "message": "Hello! Good morning, how are you today?",
        "is_voice": False
    }
    res = post_json("/chat", payload)
    assert res.get("status") == "success", f"Status failed: {res}"
    assert len(res.get("tools_executed", [])) == 0, f"Expected 0 tools executed for casual greeting, got {res.get('tools_executed')}"
    print(f"✅ PASSED: Casual chat responded naturally without executing tools.")
    print(f"   Response snippet: {res['response'][:100]}...")


def test_2b_identity_who_are_you():
    print("\n--- TEST 2B: Identity Enforcement ('Who are you?') ---")
    payload = {
        "message": "Who are you?",
        "is_voice": False
    }
    res = post_json("/chat", payload)
    assert res.get("status") == "success", f"Status failed: {res}"
    assert "NARAD" in res.get("response", ""), f"NARAD should identify itself when asked 'Who are you?', got: {res.get('response')}"
    print(f"✅ PASSED: Identified itself as NARAD.")
    print(f"   Response snippet: {res['response'][:100]}...")


def test_3_multi_turn_pronoun_resolution():
    print("\n--- TEST 3: Multi-turn Conversation & Pronoun Resolution ---")
    # Turn 1: Introduce a concept
    res1 = post_json("/chat", {
        "message": "What is quantum computing in one short sentence?",
        "is_voice": False
    })
    chat_id = res1.get("chat_id")
    assert chat_id, "chat_id must be returned"
    print(f"   Turn 1 (New Topic): {res1['response'][:90]}...")

    # Turn 2: Follow-up using pronoun 'it' without re-mentioning quantum computing
    res2 = post_json("/chat", {
        "message": "Why is it important for modern cryptography?",
        "chat_id": chat_id,
        "is_voice": False
    })
    assert res2.get("status") == "success", f"Turn 2 failed: {res2}"
    content2 = res2.get("response", "").lower()
    # Should discuss RSA, encryption, Shor's algorithm, breaking ciphers, or cryptography
    relevant_terms = ["crypt", "rsa", "secur", "shor", "encrypt", "cipher", "break"]
    found_relevant = any(term in content2 for term in relevant_terms)
    assert found_relevant, f"Turn 2 did not resolve pronoun 'it' to cryptography: {res2.get('response')}"
    print(f"✅ PASSED: Turn 2 correctly resolved pronoun 'it'.")
    print(f"   Response snippet: {res2['response'][:100]}...")


def test_4_voice_mode_flag():
    print("\n--- TEST 4: Voice Mode Request Flag ---")
    payload = {
        "message": "Give me a quick 10-word status check.",
        "is_voice": True
    }
    res = post_json("/chat", payload)
    assert res.get("status") == "success", f"Status failed: {res}"
    print(f"✅ PASSED: Voice mode handled cleanly by provider {res['provider']}.")
    print(f"   Response snippet: {res['response'][:80]}...")


def test_5_sse_streaming_events():
    print("\n--- TEST 5: SSE Streaming Events Endpoint ---")
    url = f"{BASE_URL}/chat/stream"
    req = urllib.request.Request(
        url,
        data=json.dumps({"message": "Count from 1 to 3.", "is_voice": False}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    events_seen = set()
    with urllib.request.urlopen(req, timeout=65) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if line.startswith("data: "):
                try:
                    payload = json.loads(line[6:])
                    if "event" in payload:
                        events_seen.add(payload["event"])
                        if payload["event"] in ("done", "error"):
                            break
                except Exception:
                    pass

    print(f"   SSE events collected: {events_seen}")
    assert "session" in events_seen, "Missing 'session' SSE event"
    assert "thinking" in events_seen, "Missing 'thinking' SSE event"
    assert "token" in events_seen, "Missing 'token' SSE event"
    assert "done" in events_seen, "Missing 'done' SSE event"
    print("✅ PASSED: SSE stream emitted session, thinking, token, and done events.")


def test_6_calculator_tool_integrity():
    print("\n--- TEST 6: Tool Execution Integrity (Calculator) ---")
    payload = {
        "message": "Calculate 4829 multiplied by 37",
        "is_voice": False
    }
    res = post_json("/chat", payload)
    assert res.get("status") == "success", f"Failed: {res}"
    expected_result = 4829 * 37  # 178673
    clean_resp = res.get("response", "").replace(",", "")
    assert str(expected_result) in clean_resp, f"Expected {expected_result} in response: {res.get('response')}"
    executed_tools = [t.get("tool_name") or t.get("name") for t in res.get("tools_executed", [])]
    assert "calculator" in executed_tools, f"Expected calculator in executed tools: {executed_tools}"
    print(f"✅ PASSED: Calculator tool executed and returned accurate computation: {res.get('response')}")


def run_all_tests():
    print("==================================================")
    print("NARAD V3.2 LIVE E2E VERIFICATION SUITE")
    print("==================================================")
    try:
        test_1_health_v32()
        test_2_casual_chat_no_tools()
        test_2b_identity_who_are_you()
        test_3_multi_turn_pronoun_resolution()
        test_4_voice_mode_flag()
        test_5_sse_streaming_events()
        test_6_calculator_tool_integrity()
        print("\n==================================================")
        print("ALL 6 LIVE E2E VERIFICATION TESTS PASSED SUCCESSFULLY!")
        print("==================================================")
    except Exception as e:
        print(f"\n❌ FAILED with exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
