"""
End-to-end integration test against running NARAD V3.1 server.
Tests live conversation, memory, sliding window context continuity,
and tool execution.
"""

import requests
import json

BASE_URL = "http://127.0.0.1:8000/api"

def test_e2e():
    print("\n--- 1. Testing GET /api/health ---")
    h_res = requests.get(f"{BASE_URL}/health")
    assert h_res.status_code == 200, f"Health check failed: {h_res.text}"
    health_data = h_res.json()
    print(f"Health Status: {health_data.get('status')}")
    print(f"Version: {health_data.get('version')}")
    print(f"Active Provider: {health_data.get('active_provider')}")
    print(f"Active Model: {health_data.get('active_model')}")
    print(f"Provider Matrix: {json.dumps(health_data.get('provider_matrix'), indent=2)}")

    print("\n--- 2. Create New Chat Session ---")
    c_res = requests.post(f"{BASE_URL}/chats", json={"title": "V3.1 Verification"})
    assert c_res.status_code in (200, 201), f"Chat creation failed (status {c_res.status_code}): {c_res.text}"
    chat_id = c_res.json()["id"]
    print(f"Created chat session: {chat_id}")

    print("\n--- 3. Turn 1: User says 'My name is Pratyush.' ---")
    t1_res = requests.post(f"{BASE_URL}/chat", json={
        "message": "My name is Pratyush.",
        "chat_id": chat_id
    })
    assert t1_res.status_code == 200, f"Turn 1 failed: {t1_res.text}"
    t1_data = t1_res.json()
    print(f"NARAD Response: {t1_data['response']}")
    print(f"Provider: {t1_data['provider']} | Model: {t1_data['model']} | Route: {t1_data.get('route_reason')} | Latency: {t1_data['latency_ms']}ms")

    print("\n--- 4. Turn 2: Follow-up 'What is my name?' ---")
    t2_res = requests.post(f"{BASE_URL}/chat", json={
        "message": "What is my name?",
        "chat_id": chat_id
    })
    assert t2_res.status_code == 200, f"Turn 2 failed: {t2_res.text}"
    t2_data = t2_res.json()
    print(f"NARAD Response: {t2_data['response']}")
    print(f"Provider: {t2_data['provider']} | Model: {t2_data['model']} | Route: {t2_data.get('route_reason')} | Latency: {t2_data['latency_ms']}ms")
    assert "Pratyush" in t2_data["response"], f"Name 'Pratyush' not in response: {t2_data['response']}"

    print("\n--- 5. Turn 3: User says 'I want to build a website.' ---")
    t3_res = requests.post(f"{BASE_URL}/chat", json={
        "message": "I want to build a personal portfolio website.",
        "chat_id": chat_id
    })
    assert t3_res.status_code == 200, f"Turn 3 failed: {t3_res.text}"
    t3_data = t3_res.json()
    print(f"NARAD Response: {t3_data['response'][:120]}...")
    print(f"Provider: {t3_data['provider']} | Latency: {t3_data['latency_ms']}ms")

    print("\n--- 6. Turn 4: Follow-up pronoun reference 'Continue that.' ---")
    t4_res = requests.post(f"{BASE_URL}/chat", json={
        "message": "Continue that with the tech stack recommendations.",
        "chat_id": chat_id
    })
    assert t4_res.status_code == 200, f"Turn 4 failed: {t4_res.text}"
    t4_data = t4_res.json()
    print(f"NARAD Response: {t4_data['response'][:150]}...")
    print(f"Provider: {t4_data['provider']} | Route: {t4_data.get('route_reason')} | Latency: {t4_data['latency_ms']}ms")
    assert any(w in t4_data["response"].lower() for w in ["website", "portfolio", "stack", "react", "html", "css", "frontend"]), \
        f"Context not continued: {t4_data['response']}"

    print("\n--- 7. Turn 5: Tool Execution 'What is 157 * 23?' ---")
    t5_res = requests.post(f"{BASE_URL}/chat", json={
        "message": "What is 157 * 23?",
        "chat_id": chat_id
    })
    assert t5_res.status_code == 200, f"Turn 5 failed: {t5_res.text}"
    t5_data = t5_res.json()
    print(f"NARAD Response: {t5_data['response']}")
    print(f"Tools Executed: {[t['name'] for t in t5_data.get('tools_executed', [])]}")
    assert "3611" in t5_data["response"].replace(",", ""), f"3611 not found in response: {t5_data['response']}"

    print("\n--- 8. Testing SSE Streaming Endpoint /api/chat/stream ---")
    stream_res = requests.post(
        f"{BASE_URL}/chat/stream",
        json={"message": "Say 'NARAD V3.1 Streaming Nominal' exactly.", "chat_id": chat_id},
        stream=True
    )
    assert stream_res.status_code == 200, f"Stream failed: {stream_res.status_code}"
    stream_chunks = []
    for line in stream_res.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith("data: "):
                payload = json.loads(decoded[6:])
                if payload.get("event") == "token":
                    stream_chunks.append(payload.get("token"))
    full_streamed = "".join(stream_chunks)
    print(f"Streamed Text: {full_streamed}")
    assert len(full_streamed) > 0, "No tokens received from stream"

    print("\n✅ ALL E2E LIVE TESTS PASSED NOMINALLY!")

if __name__ == "__main__":
    test_e2e()
