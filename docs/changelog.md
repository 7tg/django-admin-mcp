# 📋 Changelog

All notable changes to Django Admin MCP are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- 🔐 Hashed token authentication with `mcp_<key>.<secret>` format
- 🔑 O(1) token lookup via indexed `token_key` field
- 🛡️ Constant-time secret comparison to prevent timing attacks
- 📝 `require_registered_model` and `require_permission` decorators
- 📦 Bulk create support (`handle_bulk_create`)
- 🔒 `mcp_fields` and `mcp_exclude_fields` for field filtering

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

## 📊 Version History

| Version | Python | Django |
|---------|--------|--------|
| 0.3.0 | 3.10+ | 3.2+ |
| 0.2.1 | 3.10+ | 3.2+ |
| 0.2.0 | 3.10+ | 3.2+ |
| 0.1.0 | 3.10+ | 3.2+ |

---

## ⬆️ Upgrade Guide

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

## 📌 Deprecation Policy

- Features are deprecated for at least one minor version before removal
- Deprecated features will emit warnings
- Migration guides are provided for breaking changes
