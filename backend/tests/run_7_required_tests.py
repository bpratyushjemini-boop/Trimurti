"""
End-to-End Test Suite for NARAD V2.2 Required 7 Tests.
Executes against the live local backend (http://127.0.0.1:8000/api)
validating the full pipeline, Groq model synthesis, Krīya dispatch,
Smṛti separation, and Knowledge Base deletion.
"""

import sys
import io
import json
import time
import requests

BASE_URL = "http://127.0.0.1:8000/api"

TEST_DOC_CONTENT = """NARAD TEST DOCUMENT

Project: TRIMURTI AI

Purpose:
Build a private personal AI system.

Current modules:
NARAD
Smṛti
Krīya

Future modules:
Manthan
Vāṇī
Trinetra

TEST FACT:
The project uses a local-first architecture.
"""

def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def main():
    print_header("NARAD V2.2 VALIDATION: RUNNING 7 REQUIRED TESTS")
    results = {}

    # -------------------------------------------------------------
    # TEST 1: Add the test document
    # -------------------------------------------------------------
    print_header("TEST 1: Ingest Test Document")
    print("Uploading 'trimurti_test_document.txt'...")
    files = {
        "file": ("trimurti_test_document.txt", io.BytesIO(TEST_DOC_CONTENT.encode("utf-8")), "text/plain")
    }
    r1 = requests.post(f"{BASE_URL}/knowledge/upload", files=files)
    if r1.status_code != 201:
        print(f"FAILED: Status {r1.status_code}, {r1.text}")
        results["TEST 1"] = False
        return
    data1 = r1.json()
    telemetry = data1.get("telemetry", [])
    doc_id = data1.get("document", {}).get("id")
    print(f"Ingestion status: {data1.get('status')}")
    print(f"Telemetry: {' → '.join(telemetry)}")
    print(f"Document ID: {doc_id}")
    print(f"Chunks indexed: {data1.get('chunks_indexed')}")
    
    t1_pass = data1.get("status") == "success" and "READY" in telemetry and doc_id is not None
    results["TEST 1"] = t1_pass
    print(f">> TEST 1 Result: {'PASS' if t1_pass else 'FAIL'}")

    # Wait 1 second for DB consistency
    time.sleep(1)

    # -------------------------------------------------------------
    # TEST 2: Ask "According to the document, what is the purpose of TRIMURTI AI?"
    # -------------------------------------------------------------
    print_header("TEST 2: Document Purpose Retrieval")
    q2 = "According to the document, what is the purpose of TRIMURTI AI?"
    print(f"User Directive: '{q2}'")
    r2 = requests.post(f"{BASE_URL}/chat", json={"message": q2})
    data2 = r2.json()
    ans2 = data2.get("response", "")
    tools2 = data2.get("tools_executed", [])
    tool_names2 = [t["name"] for t in tools2]
    print(f"Tools Executed: {tool_names2}")
    for t in tools2:
        print(f" - Tool '{t['name']}': status={t.get('result', {}).get('status', 'ok')}")
    print(f"\nNARAD Response:\n{ans2}\n")

    t2_used_kb = "search_knowledge" in tool_names2
    t2_has_answer = "private personal ai system" in ans2.lower() or "build a private" in ans2.lower()
    t2_pass = t2_used_kb and t2_has_answer
    results["TEST 2"] = t2_pass
    print(f">> TEST 2 Result: {'PASS' if t2_pass else 'FAIL'} (Used search_knowledge: {t2_used_kb}, Found answer: {t2_has_answer})")

    time.sleep(1)

    # -------------------------------------------------------------
    # TEST 3: Ask "According to the document, what is the project's favorite programming language?"
    # -------------------------------------------------------------
    print_header("TEST 3: Source Discipline — Non-existent Fact must be UNKNOWN")
    q3 = "According to the document, what is the project's favorite programming language?"
    print(f"User Directive: '{q3}'")
    r3 = requests.post(f"{BASE_URL}/chat", json={"message": q3})
    data3 = r3.json()
    ans3 = data3.get("response", "")
    tools3 = data3.get("tools_executed", [])
    tool_names3 = [t["name"] for t in tools3]
    print(f"Tools Executed: {tool_names3}")
    print(f"\nNARAD Response:\n{ans3}\n")

    t3_used_kb = "search_knowledge" in tool_names3
    ans3_lower = ans3.lower()
    t3_says_unknown = ("unknown" in ans3_lower or 
                       "does not mention" in ans3_lower or 
                       "not mentioned" in ans3_lower or 
                       "not found" in ans3_lower or 
                       "does not contain" in ans3_lower or
                       "no mention" in ans3_lower)
    t3_invented = ("python" in ans3_lower or "rust" in ans3_lower or "c++" in ans3_lower or "javascript" in ans3_lower) and not t3_says_unknown
    t3_pass = t3_used_kb and t3_says_unknown and not t3_invented
    results["TEST 3"] = t3_pass
    print(f">> TEST 3 Result: {'PASS' if t3_pass else 'FAIL'} (Used search_knowledge: {t3_used_kb}, Answered UNKNOWN/Not Mentioned: {t3_says_unknown}, Did NOT invent: {not t3_invented})")

    time.sleep(1)

    # -------------------------------------------------------------
    # TEST 4: Ask "What are the future modules mentioned in the document?"
    # -------------------------------------------------------------
    print_header("TEST 4: Document Future Modules Retrieval")
    q4 = "What are the future modules mentioned in the document?"
    print(f"User Directive: '{q4}'")
    r4 = requests.post(f"{BASE_URL}/chat", json={"message": q4})
    data4 = r4.json()
    ans4 = data4.get("response", "")
    tools4 = data4.get("tools_executed", [])
    tool_names4 = [t["name"] for t in tools4]
    print(f"Tools Executed: {tool_names4}")
    print(f"\nNARAD Response:\n{ans4}\n")

    ans4_lower = ans4.lower()
    has_manthan = "manthan" in ans4_lower
    has_vaani = "vāṇī" in ans4_lower or "vani" in ans4_lower or "vaani" in ans4_lower
    has_trinetra = "trinetra" in ans4_lower
    t4_pass = "search_knowledge" in tool_names4 and has_manthan and (has_vaani or has_trinetra)
    results["TEST 4"] = t4_pass
    print(f">> TEST 4 Result: {'PASS' if t4_pass else 'FAIL'} (Found Manthan: {has_manthan}, Vaani: {has_vaani}, Trinetra: {has_trinetra})")

    time.sleep(1)

    # -------------------------------------------------------------
    # TEST 5: Ask "What is my name?"
    # -------------------------------------------------------------
    print_header("TEST 5: Smṛti Recall (Knowledge Search must NOT execute)")
    q5 = "What is my name?"
    print(f"User Directive: '{q5}'")
    r5 = requests.post(f"{BASE_URL}/chat", json={"message": q5})
    data5 = r5.json()
    ans5 = data5.get("response", "")
    tools5 = data5.get("tools_executed", [])
    tool_names5 = [t["name"] for t in tools5]
    print(f"Tools Executed: {tool_names5}")
    print(f"\nNARAD Response:\n{ans5}\n")

    t5_kb_not_executed = "search_knowledge" not in tool_names5
    t5_has_pratyush = "pratyush" in ans5.lower()
    t5_pass = t5_kb_not_executed and t5_has_pratyush
    results["TEST 5"] = t5_pass
    print(f">> TEST 5 Result: {'PASS' if t5_pass else 'FAIL'} (Knowledge Search NOT executed: {t5_kb_not_executed}, Answered Pratyush: {t5_has_pratyush})")

    time.sleep(1)

    # -------------------------------------------------------------
    # TEST 6: Ask "What is the latest AI news?"
    # -------------------------------------------------------------
    print_header("TEST 6: Web Search (Knowledge Search must NOT execute)")
    q6 = "What is the latest AI news?"
    print(f"User Directive: '{q6}'")
    r6 = requests.post(f"{BASE_URL}/chat", json={"message": q6})
    data6 = r6.json()
    ans6 = data6.get("response", "")
    tools6 = data6.get("tools_executed", [])
    tool_names6 = [t["name"] for t in tools6]
    print(f"Tools Executed: {tool_names6}")
    print(f"\nNARAD Response:\n{ans6[:200]}...\n")

    t6_web_executed = "web_search" in tool_names6
    t6_kb_not_executed = "search_knowledge" not in tool_names6
    t6_pass = t6_web_executed and t6_kb_not_executed
    results["TEST 6"] = t6_pass
    print(f">> TEST 6 Result: {'PASS' if t6_pass else 'FAIL'} (Web search executed: {t6_web_executed}, Knowledge search NOT executed: {t6_kb_not_executed})")

    time.sleep(1)

    # -------------------------------------------------------------
    # TEST 7: Delete the test document
    # -------------------------------------------------------------
    print_header("TEST 7: Delete Test Document and Verify Non-retrievability")
    print(f"Deleting document {doc_id}...")
    r7 = requests.delete(f"{BASE_URL}/knowledge/documents/{doc_id}")
    print(f"Delete response: {r7.status_code}, {r7.text}")

    # Verify no longer retrievable
    r7_search = requests.post(f"{BASE_URL}/knowledge/search", json={"query": "TRIMURTI purpose"})
    s_data = r7_search.json()
    print(f"Post-delete search results count: {s_data.get('count', 0)}")

    t7_deleted = r7.status_code == 200 and r7.json().get("success") is True
    t7_not_found = s_data.get("count", 0) == 0
    t7_pass = t7_deleted and t7_not_found
    results["TEST 7"] = t7_pass
    print(f">> TEST 7 Result: {'PASS' if t7_pass else 'FAIL'} (Deleted: {t7_deleted}, Count zero: {t7_not_found})")

    # Final summary
    print_header("FINAL TEST RESULTS SUMMARY")
    all_passed = True
    for test_name, passed in results.items():
        print(f"  {test_name}: {'PASSED' if passed else 'FAILED'}")
        if not passed:
            all_passed = False

    print("\nOVERALL V2.2 STATUS:", "PASSED" if all_passed else "FAILED")
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
