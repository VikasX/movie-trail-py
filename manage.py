#!/usr/bin/env python
# FILE PURPOSE: Terminal entry point. Django reads the command you type and runs the matching
# tool.
"""Django's command-line utility for administrative tasks."""

# Import os so the code below can use that module namespace.
import os

# Import sys so the code below can use that module namespace.
import sys


# Tell Django which settings to use, then hand the terminal arguments to its command runner.
def main():
    # Reuse the existing entry, or create the provided starting value only if absent.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    # Import execute_from_command_line from django.core.management (Django
    # framework/database/security helpers).
    from django.core.management import execute_from_command_line

    # Call execute_from_command_line with the inputs shown; its definition explains the checks,
    # side effects and return value.
    execute_from_command_line(sys.argv)


# Enter this branch only when __name__ == '__main__'. Otherwise execution uses its alternative or
# continues below.
if __name__ == "__main__":
    # Call main with the inputs shown; its definition explains the checks, side effects and return
    # value.
    main()
