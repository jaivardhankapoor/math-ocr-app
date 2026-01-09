#!/usr/bin/env python3
"""Security and functionality tests for auth system"""

import os
import time
import requests
from jose import jwt

API_URL = "http://localhost:8000"

# Test JWT secret (you'll need to set this to match your NEXTAUTH_SECRET)
NEXTAUTH_SECRET = os.getenv("NEXTAUTH_SECRET", "test-secret-change-me")


def create_test_token(user_id: str, email: str, name: str = "Test User") -> str:
    """Create a test JWT token"""
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, NEXTAUTH_SECRET, algorithm="HS256")


def test_1_health_check():
    """Test: API is running"""
    print("\n[TEST 1] Health check...")
    resp = requests.get(f"{API_URL}/health")
    print(f"  Status: {resp.status_code}")
    print(f"  Response: {resp.json()}")
    assert resp.status_code == 200


def test_2_no_auth():
    """Test: Endpoints require authentication"""
    print("\n[TEST 2] Endpoints require auth...")

    # Try to list jobs without auth
    resp = requests.get(f"{API_URL}/jobs")
    print(f"  GET /jobs without auth: {resp.status_code}")
    assert resp.status_code == 422  # Missing header

    # Try with invalid token
    resp = requests.get(f"{API_URL}/jobs", headers={"Authorization": "Bearer invalid"})
    print(f"  GET /jobs with invalid token: {resp.status_code}")
    assert resp.status_code == 401


def test_3_user_sync():
    """Test: User sync endpoint"""
    print("\n[TEST 3] User sync...")

    token = create_test_token("user123", "test@example.com")

    resp = requests.post(
        f"{API_URL}/users/sync",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "id": "user123",
            "email": "test@example.com",
            "name": "Test User",
            "image": None,
        }
    )
    print(f"  Status: {resp.status_code}")
    print(f"  Response: {resp.json()}")
    assert resp.status_code == 200


def test_4_get_user_info():
    """Test: Get user info"""
    print("\n[TEST 4] Get user info...")

    token = create_test_token("user123", "test@example.com")

    resp = requests.get(
        f"{API_URL}/users/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"  Status: {resp.status_code}")
    data = resp.json()
    print(f"  User: {data['email']}, Tier: {data['tier']}, Usage: {data['usage_24h']}/{data['limit']}")
    assert resp.status_code == 200
    assert data["tier"] == "free"
    assert data["limit"] == 3


def test_5_token_mismatch():
    """Test: Can't sync user with mismatched token"""
    print("\n[TEST 5] Token mismatch protection...")

    token = create_test_token("user123", "test@example.com")

    # Try to sync a different user
    resp = requests.post(
        f"{API_URL}/users/sync",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "id": "user456",  # Different user!
            "email": "hacker@example.com",
            "name": "Hacker",
        }
    )
    print(f"  Status: {resp.status_code}")
    print(f"  Response: {resp.json()}")
    assert resp.status_code == 403


def test_6_rate_limiting():
    """Test: Rate limiting works"""
    print("\n[TEST 6] Rate limiting (free tier = 3/day)...")

    token = create_test_token("ratelimit_test", "ratelimit@example.com")

    # Sync user first
    requests.post(
        f"{API_URL}/users/sync",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "id": "ratelimit_test",
            "email": "ratelimit@example.com",
            "name": "Rate Limit Test",
        }
    )

    # Try to submit jobs (would need actual PDF, so this will fail at PDF decode)
    # But we can check the rate limit logic runs first
    for i in range(4):
        resp = requests.post(
            f"{API_URL}/jobs",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "pdf_base64": "invalid_base64_but_testing_rate_limit",
                "filename": f"test{i}.pdf",
            }
        )
        print(f"  Attempt {i+1}: {resp.status_code} - {resp.json().get('detail', '')}")

        if i < 3:
            # First 3 should fail at base64 decode (400), not rate limit
            # But if they were valid PDFs, they'd succeed
            assert resp.status_code in (400, 429)
        else:
            # 4th should be rate limited (429)
            assert resp.status_code == 429


def test_7_algorithm_confusion():
    """Test: Can't use 'none' algorithm"""
    print("\n[TEST 7] Algorithm confusion attack...")

    # Try to create a token with no signature
    payload = {
        "sub": "hacker",
        "email": "hacker@example.com",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }

    # Create token with "none" algorithm (unsigned)
    import base64
    import json
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    fake_token = f"{header}.{body}."

    resp = requests.get(
        f"{API_URL}/users/me",
        headers={"Authorization": f"Bearer {fake_token}"}
    )
    print(f"  Status: {resp.status_code}")
    print(f"  Response: {resp.json()}")
    assert resp.status_code == 401  # Should reject


def test_8_user_isolation():
    """Test: Users can only see their own jobs"""
    print("\n[TEST 8] User isolation...")

    # Create two users
    token1 = create_test_token("user1", "user1@example.com")
    token2 = create_test_token("user2", "user2@example.com")

    # Sync both
    for token, uid, email in [
        (token1, "user1", "user1@example.com"),
        (token2, "user2", "user2@example.com"),
    ]:
        requests.post(
            f"{API_URL}/users/sync",
            headers={"Authorization": f"Bearer {token}"},
            json={"id": uid, "email": email, "name": f"User {uid}"}
        )

    # List jobs as user1
    resp1 = requests.get(f"{API_URL}/jobs", headers={"Authorization": f"Bearer {token1}"})
    jobs1 = resp1.json()["jobs"]

    # List jobs as user2
    resp2 = requests.get(f"{API_URL}/jobs", headers={"Authorization": f"Bearer {token2}"})
    jobs2 = resp2.json()["jobs"]

    print(f"  User1 sees {len(jobs1)} jobs")
    print(f"  User2 sees {len(jobs2)} jobs")

    # Check no overlap (assuming they have different jobs)
    job_ids_1 = {j["id"] for j in jobs1}
    job_ids_2 = {j["id"] for j in jobs2}
    overlap = job_ids_1 & job_ids_2

    print(f"  Overlap: {len(overlap)} jobs (should be 0)")
    assert len(overlap) == 0


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("SECURITY & FUNCTIONALITY TESTS")
    print("=" * 60)

    tests = [
        test_1_health_check,
        test_2_no_auth,
        test_3_user_sync,
        test_4_get_user_info,
        test_5_token_mismatch,
        # test_6_rate_limiting,  # Skip: needs valid PDFs
        test_7_algorithm_confusion,
        test_8_user_isolation,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            print(f"  ✓ PASSED")
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
