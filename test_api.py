#!/usr/bin/env python3
"""Quick API test for PayShield"""

import requests
import json

BASE_URL = "http://localhost:8000"

# Test 1: Analyze a normal payment
print("\n" + "="*60)
print("TEST 1: Normal Payment (Should be LOW risk)")
print("="*60)

payload = {
    "sender_id": "USER123",
    "recipient_name": "Google Pay",
    "recipient_id": "GOOG",
    "amount": 100.00,
    "note": "Regular payment"
}

response = requests.post(f"{BASE_URL}/api/analyze", json=payload)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")

# Test 2: Analyze a suspicious payment
print("\n" + "="*60)
print("TEST 2: Suspicious Payment (Should be HIGH risk)")
print("="*60)

payload = {
    "sender_id": "USER123",
    "recipient_name": "Unknown Person",
    "recipient_id": "UNKNOWN001",
    "amount": 5000.00,
    "note": "Urgent: refund needed immediately. Please verify your account."
}

response = requests.post(f"{BASE_URL}/api/analyze", json=payload)
print(f"Status: {response.status_code}")
analysis = response.json()
print(f"Response: {json.dumps(analysis, indent=2)}")

# Test 3: Confirm payment
print("\n" + "="*60)
print("TEST 3: Confirm Payment")
print("="*60)

confirm_payload = {
    "request": payload,
    "confirmed": True
}

response = requests.post(f"{BASE_URL}/api/confirm", json=confirm_payload)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")

# Test 4: Get audit history
print("\n" + "="*60)
print("TEST 4: Get Audit History")
print("="*60)

response = requests.get(f"{BASE_URL}/api/audit-history?limit=5")
print(f"Status: {response.status_code}")
history = response.json()
print(f"Entries: {len(history)}")
for entry in history[-2:]:
    print(f"  - {entry.get('request', {}).get('recipient_name')} | Score: {entry.get('final_score')} | Outcome: {entry.get('outcome')}")

print("\n" + "="*60)
print("All tests completed!")
print("="*60)
