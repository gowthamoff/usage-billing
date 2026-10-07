"""Root test config: redirects DATABASE_URL to TEST_DATABASE_URL before the app is imported."""

import os

# Must run before anything imports app.config, which builds settings and the engine at import.
_test_url = os.environ.get("TEST_DATABASE_URL")
if _test_url:
    os.environ["DATABASE_URL"] = _test_url
