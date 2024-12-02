# test_endpoints.py
import httpx
import asyncio
import json
from typing import Dict, Any

BASE_URL = "https://0c3a54fe-3b1d-4852-8501-f173cf8fc328-00-2l1pywatsvnm9.sisko.replit.dev"

async def test_endpoint(client: httpx.AsyncClient, endpoint: str, method: str = "GET", data: Dict[str, Any] = None) -> Dict[str, Any]:
    """Generic test function for endpoints"""
    try:
        if method == "GET":
            response = await client.get(f"{BASE_URL}{endpoint}")
        elif method == "POST":
            response = await client.post(f"{BASE_URL}{endpoint}", json=data)

        print(f"\nTesting {method} {endpoint}")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.json()
    except Exception as e:
        print(f"Error testing {endpoint}: {str(e)}")
        return {"error": str(e)}

async def run_tests():
    """Run all tests"""
    async with httpx.AsyncClient() as client:
        # Test health check
        await test_endpoint(client, "/")

        # Test database health
        await test_endpoint(client, "/database/health")

        # Test session management
        test_phone = "+1234567890"

        # Reset session
        await test_endpoint(client, f"/test/reset-session/{test_phone}")

        # Create test session
        session_data = {
            "phone_number": test_phone,
            "session_data": {"state": "awaiting_name"},
            "language": "en"
        }
        await test_endpoint(client, "/test/create-session", "POST", session_data)

        # Check session state
        await test_endpoint(client, f"/debug/session/{test_phone}")

        # Test maintenance flow
        await test_endpoint(client, f"/debug/maintenance-flow/{test_phone}")

        # Create test maintenance request
        maintenance_data = {
            "customer_name": "Test User",
            "phone_number": test_phone,
            "equipment_type": "cooking",
            "problem_description": "Test problem",
            "preferred_time": "Morning (9 AM - 12 PM)",
        }
        await test_endpoint(client, "/test/create-maintenance", "POST", maintenance_data)

        # Test system check
        await test_endpoint(client, "/test/system-check")

def main():
    """Main test function"""
    print("Starting endpoint tests...")
    asyncio.run(run_tests())
    print("\nTests completed!")

if __name__ == "__main__":
    main()