import os

# A fake key that exists only inside the test run (the real key lives in Render's environment).
os.environ.setdefault("API_KEY", "test-key-not-a-secret")
