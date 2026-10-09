# Security policy

django-admin-mcp gives MCP clients authenticated access to data behind the Django admin, so reports about anything that lets a token see or change more than its user may are welcome and taken seriously.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private reporting instead:

**[Report a vulnerability](https://github.com/7tg/django-admin-mcp/security/advisories/new)**

Include the django-admin-mcp, Django and Python versions, the `ModelAdmin` and token configuration involved, and the MCP request that demonstrates the problem. You will get an acknowledgement within a few days, and a fix or a mitigation before any public disclosure. Credit goes to the reporter in the advisory and the release notes unless you prefer otherwise.

## What counts

Examples of what to report:

- a token reading, creating, changing or deleting records its linked user may not
- fields hidden with `mcp_fields` or `mcp_exclude_fields` reaching the client through any tool, resource or error message
- rows outside `get_queryset()` becoming reachable
- a write that bypasses `full_clean()`, `save_model()` or `save_related()`
- a change that leaves no `LogEntry`, or one logged under the wrong user
- token secrets or hashes leaking through logs, responses or the admin
- expired, deactivated or revoked tokens still being accepted

Hardening advice for deployments is in the [Permissions](https://7tg.github.io/django-admin-mcp/guide/permissions/) and [Token Management](https://7tg.github.io/django-admin-mcp/guide/tokens/) guides.

## Supported versions

Fixes land in the latest release on PyPI. Older releases are not patched, so keep `django-admin-mcp` up to date.
