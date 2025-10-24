"""Quick diagnostic test for httpx connectivity to Google OAuth."""
import asyncio
import httpx
import sys

async def test_google_oauth():
    """Test async httpx connection to Google's OAuth metadata endpoint."""
    url = "https://accounts.google.com/.well-known/openid-configuration"
    
    print(f"Testing httpx connection to: {url}")
    print(f"Python version: {sys.version}")
    print(f"httpx version: {httpx.__version__}")
    print()
    
    try:
        # Match authlib's default behavior
        async with httpx.AsyncClient(timeout=10.0) as client:
            print("Sending request...")
            response = await client.get(url)
            print(f"✓ Success! Status: {response.status_code}")
            print(f"  Content length: {len(response.content)} bytes")
            return True
    except httpx.ConnectTimeout as e:
        print(f"✗ Connection timeout: {e}")
        return False
    except httpx.TimeoutException as e:
        print(f"✗ Timeout: {e}")
        return False
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_google_oauth())
    sys.exit(0 if result else 1)
