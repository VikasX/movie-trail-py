# FILE PURPOSE: Starts a separate Python process to test Vercel host/debug settings in
# isolation.
# Import json so the code below can use that module namespace.
import json

# Import os so the code below can use that module namespace.
import os

# Import subprocess so the code below can use that module namespace.
import subprocess

# Import sys so the code below can use that module namespace.
import sys

# Import pytest so the code below can use that module namespace.
import pytest


@pytest.mark.parametrize("debug_value", ["False", "True", "1"])
def test_vercel_allows_only_project_hosts_and_disables_debug(debug_value):
    # INPUTS TO THIS FUNCTION: debug_value = argument supplied by the caller.
    # Set environment: build a dictionary with named fields such as VERCEL, DEBUG, ALLOWED_HOSTS,
    # VERCEL_URL, VERCEL_BRANCH_URL, VERCEL_PROJECT_PRODUCTION_URL.
    environment = {
        **os.environ,
        "VERCEL": "1",
        "DEBUG": debug_value,
        "ALLOWED_HOSTS": "api.example.com",
        "VERCEL_URL": "cinescope-deployment.vercel.app",
        "VERCEL_BRANCH_URL": "cinescope-branch.vercel.app",
        "VERCEL_PROJECT_PRODUCTION_URL": "cinescope.vercel.app",
    }
    # Set result: call subprocess.run with the inputs shown; its definition explains the checks,
    # side effects and return value.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from config.settings import ALLOWED_HOSTS, DEBUG, "
            "SECURE_SSL_REDIRECT, SESSION_COOKIE_SECURE; "
            "assert DEBUG is False; "
            "assert SECURE_SSL_REDIRECT is True; "
            "assert SESSION_COOKIE_SECURE is True; "
            "print(json.dumps(ALLOWED_HOSTS))",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    # Test expectation: json.loads(result.stdout) == ['api.example.com', 'cinescope-
    # deployment.vercel.app', 'cinescope-branch.vercel.app', 'cinescope.vercel.app']. If false,
    # pytest reports a failure at this line.
    assert json.loads(result.stdout) == [
        "api.example.com",
        "cinescope-deployment.vercel.app",
        "cinescope-branch.vercel.app",
        "cinescope.vercel.app",
    ]
