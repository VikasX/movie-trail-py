import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("debug_value", ["False", "True", "1"])
def test_vercel_allows_only_project_hosts_and_disables_debug(debug_value):
    environment = {
        **os.environ,
        "VERCEL": "1",
        "DEBUG": debug_value,
        "ALLOWED_HOSTS": "api.example.com",
        "VERCEL_URL": "cinescope-deployment.vercel.app",
        "VERCEL_BRANCH_URL": "cinescope-branch.vercel.app",
        "VERCEL_PROJECT_PRODUCTION_URL": "cinescope.vercel.app",
    }
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
    assert json.loads(result.stdout) == [
        "api.example.com",
        "cinescope-deployment.vercel.app",
        "cinescope-branch.vercel.app",
        "cinescope.vercel.app",
    ]
