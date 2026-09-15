# Changelog

All notable changes to Django Admin MCP are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed — BREAKING
- **Token-level permissions are now enforced.** Authorization answers from the token's own `permissions` and `groups` fields (via a permission proxy placed on `request.user`); the linked user's Django permissions are no longer consulted, and a token bound to a superuser has no implicit access. The linked user remains the audit identity for `LogEntry` records. **Upgrade note:** existing tokens that relied on their user's permissions must be granted equivalent permissions/groups on the token itself before upgrading, or their requests will be denied.
- Leaving **Expires At** blank in the admin form now creates a token that never expires, matching the field's help text. Programmatic creation without an `expires_at` kwarg still defaults to 90 days.

### Added
- `MCPToken.has_module_perms(app_label)` — module-level permission check mirroring Django's `User.has_module_perms`, used by `find_models` discovery
- `TokenUser` permission proxy (`django_admin_mcp.models.TokenUser`) answering Django's permission API from token permissions while delegating identity attributes to the linked user

### Fixed
- `find_models` now reports `tools_exposed` based on each admin's `mcp_expose` flag instead of always `true`
- The advertised `autocomplete_*` limit default now matches the handler default (10, was 20 in the schema)
- The generated `list_*` tool description now advertises the full filter-lookup whitelist (`contains`, `gt`, and `lt` were missing)

### Documentation
- Documentation audited against the code: corrected request/response shapes (JSON-RPC envelope, `params`-nested `tools/call`), error payloads, permission semantics (checks run against the token's linked user), serialization details, and settings reference (`MCP_MAX_LIST_LIMIT`, `MCP_ACTION_MAX_FILE_BYTES`); documented the action confirmation flow, file downloads, inline editing, and queryset scoping

## [0.4.0] - 2026-09-15

### Added
- **MCP Prompts** support: `prompts/list` and `prompts/get` serve workflow guides (`explore_models`, `understand_model`, `crud_guide`, `bulk_operations_guide`) ([#65](https://github.com/7tg/django-admin-mcp/issues/65))
- **MCP Resources** support: `resources/list`, `resources/templates/list`, and `resources/read` expose model schemas (`models://<model>/schema`) and instance data (`data://<model>/`, `data://<model>/<id>`), permission-filtered ([#66](https://github.com/7tg/django-admin-mcp/issues/66))
- Two-step **confirmation workflow for admin actions**: actions returning an HTML page report `requires_confirmation: true`; re-calling with `confirm: true` (plus optional `confirmation_data`) executes them. Actions also receive Django's standard POST fields (`action`, `_selected_action`) ([#63](https://github.com/7tg/django-admin-mcp/issues/63))
- `min_num`/`max_num` inline constraints are enforced when editing inlines via `update_<model>` ([#61](https://github.com/7tg/django-admin-mcp/issues/61), [#62](https://github.com/7tg/django-admin-mcp/issues/62))

### Changed
- `find_models` respects `ModelAdmin.has_module_permission()`: hidden modules are excluded from discovery ([#64](https://github.com/7tg/django-admin-mcp/issues/64))
- `list_<model>` validates `limit`/`offset` and caps page size at `MCP_MAX_LIST_LIMIT` (default 1000) ([#47](https://github.com/7tg/django-admin-mcp/issues/47))
- The two HTTP view code paths now share one auth/parse/validate/execute pipeline ([#43](https://github.com/7tg/django-admin-mcp/issues/43))

## [0.3.3] - 2026-09-15

### Added
- `mcp_use_admin_queryset` option (default `True`): list/get and admin actions now start from `ModelAdmin.get_queryset(request)`, so proxy models, soft-delete, and multi-tenant scoping match the admin changelist ([#84](https://github.com/7tg/django-admin-mcp/pull/84), [#85](https://github.com/7tg/django-admin-mcp/pull/85))
- Admin action `HttpResponse` / `StreamingHttpResponse` downloads are returned as structured file payloads (UTF-8 or base64) instead of `str(response)`, with a size cap via `MCP_ACTION_MAX_FILE_BYTES` (default 5 MiB) ([#86](https://github.com/7tg/django-admin-mcp/pull/86))
- MCP Inspector troubleshooting guide for Bearer token setup ([#81](https://github.com/7tg/django-admin-mcp/issues/81))

### Fixed
- `FileField`/`ImageField` values serialize as storage-path strings; empty image fields no longer crash `list_*` responses ([#87](https://github.com/7tg/django-admin-mcp/pull/87))
- `describe_*` no longer crashes when `ModelAdmin.ordering` is `None` (the Django default); filter classes and callables in admin config serialize as dotted paths ([#83](https://github.com/7tg/django-admin-mcp/pull/83))
- The MCP `initialize` response now reports the real package version instead of a hardcoded one

### Security
- Filter lookups are restricted to a whitelist (`exact`, `contains`, `icontains`, `gt`, `gte`, `lt`, `lte`, `in`, `isnull`) on direct fields only — relation traversal and regex lookups are rejected ([#40](https://github.com/7tg/django-admin-mcp/issues/40))
- Sensitive values (passwords, tokens, secrets) are redacted from admin `LogEntry` audit messages ([#42](https://github.com/7tg/django-admin-mcp/issues/42))
- `mcp_exclude_fields` is now applied on list and related serialization, not just get/create/update ([#82](https://github.com/7tg/django-admin-mcp/pull/82))
- `delete_selected` checks delete permission before any ID lookup to avoid leaking row existence ([#85](https://github.com/7tg/django-admin-mcp/pull/85))

## [0.3.2] - 2026-07-09

### Changed
- License changed from GPL-3.0 to MIT

## [0.3.1] - 2026-03-12

### Changed
- CRUD handlers use `ModelAdmin.save_model()` and `delete_model()` for the standard Django admin pipeline ([#74](https://github.com/7tg/django-admin-mcp/pull/74))

### Fixed
- M2M fields serialize as lists of PKs in list/get responses ([#77](https://github.com/7tg/django-admin-mcp/pull/77))

## [0.3.0] - 2026-02-08

### Added
- `non_atomic_requests` decorator to async views for `ATOMIC_REQUESTS` compatibility ([#72](https://github.com/7tg/django-admin-mcp/issues/72))
- `require_registered_model` and `require_permission` decorators for handler authorization
- Comprehensive MkDocs Material documentation with getting started guides, tool reference, and example conversations

### Changed
- Use Django's `get_actions()` to resolve admin actions for listing and execution ([#73](https://github.com/7tg/django-admin-mcp/issues/73))
- Replace `json` module with Pydantic `TypeAdapter` across all handlers ([#53](https://github.com/7tg/django-admin-mcp/issues/53), [#54](https://github.com/7tg/django-admin-mcp/issues/54), [#55](https://github.com/7tg/django-admin-mcp/issues/55), [#56](https://github.com/7tg/django-admin-mcp/issues/56))
- Wrap CRUD and bulk operations in `transaction.atomic()` for data integrity ([#57](https://github.com/7tg/django-admin-mcp/issues/57))
- Apply `require_registered_model` and `require_permission` decorators to CRUD, relations, and meta handlers
- Narrow broad exception handling in `authenticate_token`

### Fixed
- URL path duplication when mounting at custom path (e.g., `path("mcp/", ...)` produced `/mcp/mcp/`) ([#68](https://github.com/7tg/django-admin-mcp/issues/68), [#71](https://github.com/7tg/django-admin-mcp/issues/71))

### Security
- Sanitize error responses to prevent internal detail leakage ([#70](https://github.com/7tg/django-admin-mcp/issues/70))
- Add permission checks to `handle_history()`, `handle_related()`, `handle_autocomplete()`, `handle_describe()`, and `handle_find_models()`
- Inline permission checks to prevent privilege escalation
- Add field filtering to `serialize_instance()` to prevent sensitive data exposure ([#58](https://github.com/7tg/django-admin-mcp/issues/58))

## [0.2.1] - 2025

### Changed
- Restrict model lookups to MCPAdminMixin registry only
- Remove redundant `str()` calls in `_get_action_info`

## [0.2.0] - 2025

### Added
- Hashed token authentication with `mcp_<key>.<secret>` format
- O(1) token lookup via indexed `token_key` field
- Constant-time secret comparison to prevent timing attacks
- `require_registered_model` and `require_permission` decorators
- Bulk create support (`handle_bulk_create`)
- `mcp_fields` and `mcp_exclude_fields` for field filtering

### Changed
- Split `handle_bulk` into `handle_bulk_create`, `handle_bulk_update`, `handle_bulk_delete`
- Extracted permission decorators to `handlers/decorators.py`

### Security
- Token secret is now hashed with per-token salt (SHA-256)
- Token format changed to `mcp_<key>.<secret>` for structured authentication

## [0.1.0] - 2024-01-15

### Added
- Initial release
- `MCPAdminMixin` for exposing Django admin models
- Token-based authentication with `MCPToken` model
- CRUD operations: `list_*`, `get_*`, `create_*`, `update_*`, `delete_*`
- Model introspection: `describe_*`, `find_models`
- Admin actions: `actions_*`, `action_*`, `bulk_*`
- Relationships: `related_*`, `history_*`, `autocomplete_*`
- Full Django admin permission integration
- Support for Django 3.2, 4.0, 4.1, 4.2, 5.0
- Support for Python 3.10, 3.11, 3.12

### Security
- Bearer token authentication
- Token expiration (default 90 days)
- Django permission checking on all operations
- Principle of least privilege (tokens start with no permissions)

---

## Version History

| Version | Python | Django |
|---------|--------|--------|
| 0.4.0 | 3.10+ | 3.2+ |
| 0.3.x | 3.10+ | 3.2+ |
| 0.2.x | 3.10+ | 3.2+ |
| 0.1.0 | 3.10+ | 3.2+ |

---

## Upgrade Guide

### From 0.1.x to 0.2.x

Token format has changed. You must:

1. Update the package:
   ```bash
   pip install --upgrade django-admin-mcp
   ```

2. Run migrations:
   ```bash
   python manage.py migrate django_admin_mcp
   ```

3. Recreate all tokens (token format changed to `mcp_<key>.<secret>`)

### From Pre-release to 0.1.0

If you were using a pre-release version:

1. Update the package:
   ```bash
   pip install --upgrade django-admin-mcp
   ```

2. Run migrations:
   ```bash
   python manage.py migrate django_admin_mcp
   ```

3. Recreate any tokens (token format may have changed)

---

## Deprecation Policy

- Features are deprecated for at least one minor version before removal
- Deprecated features will emit warnings
- Migration guides are provided for breaking changes
