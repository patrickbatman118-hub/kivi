"""
Automated evaluation runner for Kivi.

Loads evaluation/cases.json, drives the running API through every case,
compares actual vs expected behaviour, and writes evaluation/results.json.

Usage:
    uv run python evaluation/run_eval.py [--base-url http://localhost:8000]
"""
import argparse
import json
import os
import sys

import httpx

CASES_PATH = os.path.join(os.path.dirname(__file__), "cases.json")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "results.json")

# Cases documented as accepted known limitations (see TASK_LIST.md / README.md) —
# scored separately rather than counted as failures.
KNOWN_LIMITATION_IDS = {"C7_04"}


class Client:
    def __init__(self, base_url):
        self.http = httpx.Client(base_url=base_url, timeout=10.0)

    def reset(self):
        self.http.post("/memory/reset")

    def add_memory(self, canonical_form, category, variants):
        r = self.http.post("/memory", json={
            "canonical_form": canonical_form,
            "category": category,
            "variants": variants,
        })
        return r.status_code, r.json()

    def set_status(self, entry_id, status):
        r = self.http.patch(f"/memory/{entry_id}", json={"status": status})
        return r.status_code, r.json()

    def delete_memory(self, entry_id):
        r = self.http.delete(f"/memory/{entry_id}")
        return r.status_code

    def list_memory(self):
        r = self.http.get("/memory")
        return r.status_code, r.json()

    def process(self, asr_output, formatted_output):
        r = self.http.post("/process", json={
            "asr_output": asr_output,
            "formatted_output": formatted_output,
        })
        return r.status_code, r.json()

    def correct(self, original_formatted, corrected_text):
        r = self.http.post("/correct", json={
            "original_formatted": original_formatted,
            "corrected_text": corrected_text,
        })
        return r.status_code, r.json()

    def setup_memory_state(self, memory_state):
        """Creates entries from a cases.json memory_state list, applying status after creation."""
        ids = {}
        for m in memory_state:
            _, body = self.add_memory(m["canonical_form"], m["category"], m.get("variants", []))
            entry_id = body.get("id") or (body.get("entry") or {}).get("id")
            ids[m["canonical_form"]] = entry_id
            wanted_status = m.get("status", "active")
            if wanted_status != "active" and entry_id:
                self.set_status(entry_id, wanted_status)
        return ids


def decisions_match(actual_log, expected_decisions):
    """Checks that every expected (token, decision) pair appears in the actual log with the same decision."""
    ok = True
    mismatches = []
    for exp in expected_decisions:
        found = [d for d in actual_log if d["token"] == exp["token"]]
        if not found or found[0]["decision"] != exp["decision"]:
            ok = False
            mismatches.append({
                "token": exp["token"],
                "expected_decision": exp["decision"],
                "actual": found[0] if found else None,
            })
    return ok, mismatches


def run_process_case(client, case):
    client.reset()
    client.setup_memory_state(case.get("memory_state", []))
    status, body = client.process(case["asr_output"], case["formatted_output"])

    result = {
        "id": case["id"],
        "name": case["name"],
        "input": {"asr_output": case["asr_output"], "formatted_output": case["formatted_output"]},
        "expected_output": case.get("expected_memory_aware_output"),
        "actual_output": body.get("memory_aware_output") if status == 200 else None,
        "actual_decisions": body.get("intervention_log") if status == 200 else None,
    }

    if case["id"] in KNOWN_LIMITATION_IDS or "expected_memory_aware_output" not in case:
        result["passed"] = None
        result["known_limitation"] = True
        return result

    output_ok = status == 200 and body["memory_aware_output"] == case["expected_memory_aware_output"]
    decisions_ok, mismatches = True, []
    if "expected_decisions" in case:
        decisions_ok, mismatches = decisions_match(body.get("intervention_log", []), case["expected_decisions"])

    result["passed"] = output_ok and decisions_ok
    if mismatches:
        result["decision_mismatches"] = mismatches
    return result


def run_c3(client, cases):
    results = []
    for case in cases:
        if case["id"] == "C3_01":
            client.reset()
            for m in case["memory_state_after_setup"]:
                client.add_memory(m["canonical_form"], m["category"], m.get("variants", []))
            status, body = client.process(case["asr_output"], case["formatted_output"])
            passed = status == 200 and body["memory_aware_output"] == case["expected_memory_aware_output"]
            results.append({
                "id": case["id"], "name": case["name"], "passed": passed,
                "expected_output": case["expected_memory_aware_output"],
                "actual_output": body.get("memory_aware_output"),
            })
        elif case["id"] == "C3_02":
            client.reset()
            _, body = client.add_memory("Sarvam", "org_name", ["Saram"])
            passed = bool(body.get("phonetic_hash"))
            results.append({
                "id": case["id"], "name": case["name"], "passed": passed,
                "expected": "non-null phonetic_hash", "actual": body.get("phonetic_hash"),
            })
    return results


def run_c4(client, cases):
    results = []
    for case in cases:
        client.reset()
        client.setup_memory_state(case.get("memory_state_before", []))
        ci = case["correction_input"]
        status, body = client.correct(ci["original_formatted"], ci["corrected_text"])

        expected_after = case["expected_memory_state_after"]
        if not expected_after:
            passed = status == 200 and body == []
            results.append({
                "id": case["id"], "name": case["name"], "passed": passed,
                "correction_input": ci, "actual_correction_response": body,
            })
            continue

        _, mem = client.list_memory()
        passed = True
        for exp in expected_after:
            match = [m for m in mem if m["canonical_form"] == exp["canonical_form"]]
            if not match:
                passed = False
                continue
            variant_texts = {v["variant_text"] for v in match[0]["variants"]}
            if not set(exp["variants"]).issubset(variant_texts):
                passed = False

        case_result = {
            "id": case["id"], "name": case["name"], "passed": passed,
            "correction_input": ci, "expected_memory_state_after": expected_after,
            "actual_memory_state": mem,
        }

        if passed and "followup_transcript" in case:
            ft = case["followup_transcript"]
            status2, body2 = client.process(ft["asr_output"], ft["formatted_output"])
            followup_ok = status2 == 200 and body2["memory_aware_output"] == ft["expected_memory_aware_output"]
            case_result["passed"] = case_result["passed"] and followup_ok
            case_result["followup"] = {
                "expected_output": ft["expected_memory_aware_output"],
                "actual_output": body2.get("memory_aware_output"),
            }

        results.append(case_result)
    return results


def run_c5(client, cases):
    results = []
    for case in cases:
        if case["id"] != "C5_01":
            continue
        client.reset()
        client.add_memory("Aditya", "person_name", ["Aditya"])
        status2, body2 = client.add_memory("Aaditya", "person_name", ["Aditya"])
        passed = status2 == 409 and body2.get("status") == "conflict"
        results.append({
            "id": case["id"], "name": case["name"], "passed": passed,
            "expected_status_code": 409, "actual_status_code": status2, "actual_response": body2,
        })
    return results


def run_c6(client, cases):
    results = []
    for case in cases:
        client.reset()
        if case["id"] == "C6_01":
            _, added = client.add_memory("Aaditya", "person_name", ["Aditya"])
            del_status = client.delete_memory(added["id"])
            _, mem = client.list_memory()
            _, proc = client.process("ask aditya", "Ask Aditya.")
            passed = (del_status == 204 and mem == []
                      and all(d["decision"] != "APPLY" for d in proc["intervention_log"]))
            results.append({"id": case["id"], "name": case["name"], "passed": passed,
                             "actual_memory_after_delete": mem, "actual_process_after_delete": proc})
        elif case["id"] == "C6_02":
            _, added = client.add_memory("Aaditya", "person_name", ["Aditya"])
            client.set_status(added["id"], "suppressed")
            _, mem = client.list_memory()
            _, proc = client.process("ask aditya", "Ask Aditya.")
            passed = (mem[0]["status"] == "suppressed"
                      and any(d["decision"] == "ABSTAIN" for d in proc["intervention_log"]))
            results.append({"id": case["id"], "name": case["name"], "passed": passed,
                             "actual_memory": mem, "actual_process": proc})
        elif case["id"] == "C6_03":
            client.add_memory("Aaditya", "person_name", ["Aditya"])
            client.add_memory("Kivi", "product_name", ["Kiwi"])
            client.reset()
            _, mem = client.list_memory()
            passed = mem == []
            results.append({"id": case["id"], "name": case["name"], "passed": passed, "actual_memory": mem})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("EVAL_BASE_URL", "http://localhost:8000"))
    args = parser.parse_args()

    with open(CASES_PATH) as f:
        cases = json.load(f)["categories"]

    client = Client(args.base_url)

    all_results = []

    for case in cases["C1_correct_interventions"]["cases"]:
        all_results.append({**run_process_case(client, case), "category": "C1_correct_interventions"})

    for case in cases["C2_correct_abstentions"]["cases"]:
        all_results.append({**run_process_case(client, case), "category": "C2_correct_abstentions"})

    for r in run_c3(client, cases["C3_learning_explicit"]["cases"]):
        all_results.append({**r, "category": "C3_learning_explicit"})

    for r in run_c4(client, cases["C4_learning_correction"]["cases"]):
        all_results.append({**r, "category": "C4_learning_correction"})

    for r in run_c5(client, cases["C5_conflict_handling"]["cases"]):
        all_results.append({**r, "category": "C5_conflict_handling"})

    for r in run_c6(client, cases["C6_user_control"]["cases"]):
        all_results.append({**r, "category": "C6_user_control"})

    for case in cases["C7_edge_cases"]["cases"]:
        all_results.append({**run_process_case(client, case), "category": "C7_edge_cases"})

    client.reset()

    # --- Precision / recall / abstention correctness over every annotated (token, decision) pair ---
    tp = fp = fn = correct_abstain = total_abstain = 0
    for case in cases["C1_correct_interventions"]["cases"] + cases["C2_correct_abstentions"]["cases"] + cases["C7_edge_cases"]["cases"]:
        expected_decisions = case.get("expected_decisions")
        if not expected_decisions:
            continue
        result = next(r for r in all_results if r["id"] == case["id"])
        actual_log = result.get("actual_decisions") or []
        for exp in expected_decisions:
            found = [d for d in actual_log if d["token"] == exp["token"]]
            actual_decision = found[0]["decision"] if found else None
            if exp["decision"] == "APPLY":
                if actual_decision == "APPLY":
                    tp += 1
                else:
                    fn += 1
            else:  # expected ABSTAIN or PASS — both mean "should not intervene"
                total_abstain += 1
                if actual_decision == exp["decision"]:
                    correct_abstain += 1
                elif actual_decision == "APPLY":
                    fp += 1

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    abstention_correctness = correct_abstain / total_abstain if total_abstain else None

    total = len(all_results)
    known_limitations = [r for r in all_results if r.get("known_limitation")]
    scored = [r for r in all_results if r.get("passed") is not None]
    passed = [r for r in scored if r["passed"]]
    failed = [r for r in scored if not r["passed"]]

    summary = {
        "total_cases": total,
        "scored_cases": len(scored),
        "passed": len(passed),
        "failed": len(failed),
        "known_limitations": [r["id"] for r in known_limitations],
        "precision": precision,
        "recall": recall,
        "abstention_correctness": abstention_correctness,
    }

    output = {"summary": summary, "results": all_results}
    with open(RESULTS_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"Kivi evaluation — {args.base_url}")
    print(f"  Total cases:         {total}")
    print(f"  Scored:              {len(scored)}")
    print(f"  Passed:              {len(passed)}")
    print(f"  Failed:              {len(failed)}")
    print(f"  Known limitations:   {[r['id'] for r in known_limitations]}")
    print(f"  Precision:           {precision}")
    print(f"  Recall:              {recall}")
    print(f"  Abstention correct.: {abstention_correctness}")
    if failed:
        print("\nFailed cases:")
        for r in failed:
            print(f"  - {r['id']}: {r['name']}")
    print(f"\nFull results written to {RESULTS_PATH}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
