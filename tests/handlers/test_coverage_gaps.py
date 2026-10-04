"""
Tests for handler branches not exercised elsewhere: fallback paths that run
without a ModelAdmin, unauthenticated audit-log users, inline permission
denials, and small pure helpers.
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser, Permission, User
from django.forms import ModelForm

from django_admin_mcp.handlers import create_mock_request, handle_update
from django_admin_mcp.handlers.base import (
    MCPMessageStorage,
    check_inline_permission,
    check_module_permission,
    check_permission,
    get_admin_queryset,
    get_model_admin,
)
from django_admin_mcp.handlers.bulk import handle_bulk_create, handle_bulk_delete, handle_bulk_update
from django_admin_mcp.handlers.crud import (
    _build_search_query,
    handle_create,
    handle_delete,
)
from django_admin_mcp.handlers.inlines import (
    _build_inline_formset_class,
    _get_inline_data,
    prepare_inline_formsets,
)
from django_admin_mcp.handlers.meta import _json_safe_admin_item
from tests.models import Article, Author


def unique_id():
    return uuid.uuid4().hex[:8]


# The undecorated handler bodies, for exercising the model_admin=None branches
# (require_registered_model always supplies the registered admin).
raw_handle_create = handle_create.__wrapped__.__wrapped__
raw_handle_update = handle_update.__wrapped__.__wrapped__
raw_handle_delete = handle_delete.__wrapped__.__wrapped__
raw_handle_bulk_create = handle_bulk_create.__wrapped__.__wrapped__
raw_handle_bulk_update = handle_bulk_update.__wrapped__.__wrapped__
raw_handle_bulk_delete = handle_bulk_delete.__wrapped__.__wrapped__


@sync_to_async
def make_author(uid):
    return Author.objects.create(name=f"Gap Author {uid}", email=f"gap_{uid}@example.com")


@sync_to_async
def make_article(author, uid):
    return Article.objects.create(title=f"Gap Article {uid}", content="content", author=author)


@sync_to_async
def make_superuser(uid):
    return User.objects.create_superuser(username=f"gap_super_{uid}", email=f"gs_{uid}@example.com", password="pw")


@sync_to_async
def make_author_only_user(uid):
    """A user with full Author permissions but none on Article."""
    user = User.objects.create_user(username=f"gap_author_only_{uid}", password="pw")
    perms = Permission.objects.filter(codename__in=["view_author", "add_author", "change_author", "delete_author"])
    user.user_permissions.add(*perms)
    return user


class TestSearchQueryFallback:
    """_build_search_query is the fallback used when no ModelAdmin exists."""

    def test_empty_term_or_fields_returns_empty_q(self):
        assert not _build_search_query(Author, ["name"], "").children
        assert not _build_search_query(Author, [], "term").children

    def test_operator_prefixes_are_stripped(self):
        q = _build_search_query(Author, ["^name", "=email", "@bio", "name"], "abc")
        lookups = [child[0] for child in q.children]
        assert lookups == ["name__icontains", "email__icontains", "bio__icontains", "name__icontains"]

    @pytest.mark.django_db
    def test_fallback_query_matches_rows(self):
        uid = unique_id()
        Author.objects.create(name=f"Fallback {uid}", email=f"fb_{uid}@example.com")
        q = _build_search_query(Author, ["^name"], uid)
        assert Author.objects.filter(q).count() == 1


class TestInlineHelpers:
    """Inline serialization/update helpers degrade gracefully without config."""

    def test_get_inline_data_without_admin(self):
        assert _get_inline_data(Author(), None, create_mock_request()) == {}

    def test_get_inline_data_skips_inline_without_model(self):
        class NoModelInline:
            pass

        class FakeAdmin:
            inlines = [NoModelInline]

        assert _get_inline_data(Author(), FakeAdmin(), create_mock_request()) == {}

    def test_prepare_inline_formsets_without_data(self):
        _, author_admin = get_model_admin("author")
        write = prepare_inline_formsets(Author(), author_admin, {}, create_mock_request(), change=True)
        assert write.formsets == []
        assert write.errors == []
        assert write.results() == {"created": [], "updated": [], "deleted": [], "errors": []}

    def test_prepare_inline_formsets_rejects_unmatched_inline_names(self):
        """An inline name no inline class answers to is an error, not a no-op (issue #118)."""

        class NoModelInline:
            pass

        class FakeAdmin:
            inlines = [NoModelInline]

        write = prepare_inline_formsets(Author(), FakeAdmin(), {"article": [{}]}, create_mock_request(), change=True)
        assert write.formsets == []
        assert [error["code"] for error in write.errors] == ["unknown_inline"]

    def test_build_inline_formset_class_prefers_custom_form(self):
        class CustomArticleForm(ModelForm):
            class Meta:
                model = Article
                fields = ["title"]

        class CustomFormInline:
            model = Article
            form = CustomArticleForm

        _, author_admin = get_model_admin("author")
        built = _build_inline_formset_class(CustomFormInline, Article, author_admin, create_mock_request(), None)
        assert issubclass(built.form, CustomArticleForm)
        assert built.fk.name == "author"

    def test_build_inline_formset_class_falls_back_to_declared_fields(self):
        class BrokenInline:
            # Not a real InlineModelAdmin: instantiating its formset fails,
            # forcing the declared-fields fallback.
            model = Article
            fields = ["title", "content"]
            readonly_fields = ["content"]

        _, author_admin = get_model_admin("author")
        built = _build_inline_formset_class(BrokenInline, Article, author_admin, create_mock_request(), None)
        assert list(built.form.base_fields) == ["title"]


@pytest.mark.asyncio
@pytest.mark.django_db
class TestNoAdminFallbacks:
    """CRUD handlers save/delete directly when no ModelAdmin is available."""

    async def test_create_without_admin_and_anonymous_user(self):
        uid = unique_id()
        request = create_mock_request(AnonymousUser())
        result = await raw_handle_create(
            "author",
            {"data": {"name": f"NoAdmin {uid}", "email": f"noadmin_{uid}@example.com"}},
            request,
            model=Author,
            model_admin=None,
        )
        data = json.loads(result[0].text)
        assert data["success"] is True

    async def test_update_without_admin_and_anonymous_user(self):
        uid = unique_id()
        author = await make_author(uid)
        request = create_mock_request(AnonymousUser())
        result = await raw_handle_update(
            "author",
            {"id": author.pk, "data": {"name": f"Updated {uid}"}},
            request,
            model=Author,
            model_admin=None,
        )
        data = json.loads(result[0].text)
        assert data["success"] is True

    async def test_delete_without_admin_and_anonymous_user(self):
        uid = unique_id()
        author = await make_author(uid)
        request = create_mock_request(AnonymousUser())
        result = await raw_handle_delete("author", {"id": author.pk}, request, model=Author, model_admin=None)
        data = json.loads(result[0].text)
        assert data["success"] is True

    async def test_bulk_create_update_delete_without_admin(self):
        uid = unique_id()
        request = create_mock_request(AnonymousUser())

        result = await raw_handle_bulk_create(
            "author",
            {"items": [{"name": f"Bulk {uid}", "email": f"bulk_{uid}@example.com"}]},
            request,
            model=Author,
            model_admin=None,
        )
        created = json.loads(result[0].text)
        assert created["results"]["success"][0]["created"] is True
        author_id = created["results"]["success"][0]["id"]

        result = await raw_handle_bulk_update(
            "author",
            {"items": [{"id": author_id, "data": {"name": f"Bulk Updated {uid}"}}]},
            request,
            model=Author,
            model_admin=None,
        )
        updated = json.loads(result[0].text)
        assert updated["results"]["success"][0]["updated"] is True

        result = await raw_handle_bulk_delete("author", {"items": [author_id]}, request, model=Author, model_admin=None)
        deleted = json.loads(result[0].text)
        assert deleted["results"]["success"][0]["deleted"] is True


@pytest.mark.asyncio
@pytest.mark.django_db
class TestValidationFailures:
    """Form validation errors surface as structured error responses."""

    async def test_update_with_invalid_data(self):
        uid = unique_id()
        author = await make_author(uid)
        user = await make_superuser(uid)
        request = create_mock_request(user)

        result = await handle_update("author", {"id": author.pk, "data": {"email": "not-an-email"}}, request)
        data = json.loads(result[0].text)
        assert data["error"] == "Validation failed"
        assert "email" in data["validation_errors"]["fields_with_errors"]

    async def test_bulk_update_with_invalid_data(self):
        uid = unique_id()
        author = await make_author(uid)
        user = await make_superuser(uid)
        request = create_mock_request(user)

        result = await handle_bulk_update(
            "author", {"items": [{"id": author.pk, "data": {"email": "not-an-email"}}]}, request
        )
        data = json.loads(result[0].text)
        assert data["results"]["errors"][0]["error"] == "Validation failed"
        assert "email" in data["results"]["errors"][0]["validation_errors"]["fields_with_errors"]


@pytest.mark.asyncio
@pytest.mark.django_db
class TestInlinePermissionDenials:
    """Inline writes require add/change/delete permission on the inline model."""

    async def _fixture(self):
        uid = unique_id()
        author = await make_author(uid)
        article = await make_article(author, uid)
        user = await make_author_only_user(uid)
        return author, article, create_mock_request(user)

    async def test_inline_delete_denied(self):
        author, article, request = await self._fixture()
        result = await handle_update(
            "author",
            {"id": author.pk, "data": {}, "inlines": {"article": [{"id": article.pk, "_delete": True}]}},
            request,
        )
        errors = json.loads(result[0].text)["inlines"]["errors"]
        assert errors[0]["code"] == "permission_denied"
        assert "delete" in errors[0]["error"]
        assert await sync_to_async(Article.objects.filter(pk=article.pk).exists)()

    async def test_inline_change_denied(self):
        author, article, request = await self._fixture()
        result = await handle_update(
            "author",
            {"id": author.pk, "data": {}, "inlines": {"article": [{"id": article.pk, "data": {"title": "New"}}]}},
            request,
        )
        errors = json.loads(result[0].text)["inlines"]["errors"]
        assert errors[0]["code"] == "permission_denied"
        assert "change" in errors[0]["error"]

    async def test_inline_add_denied(self):
        author, _, request = await self._fixture()
        result = await handle_update(
            "author",
            {"id": author.pk, "data": {}, "inlines": {"article": [{"title": "New", "content": "c"}]}},
            request,
        )
        errors = json.loads(result[0].text)["inlines"]["errors"]
        assert errors[0]["code"] == "permission_denied"
        assert "add" in errors[0]["error"]


class TestBaseHelpers:
    """Small pure helpers in handlers.base."""

    def test_message_storage_is_a_black_hole(self):
        storage = MCPMessageStorage(create_mock_request())
        assert storage._get() == ([], True)
        assert storage._store(["a message"], None) == []

    def test_check_permission_unknown_action_is_allowed(self):
        _, author_admin = get_model_admin("author")
        request = create_mock_request()
        assert check_permission(request, author_admin, "frobnicate") is True

    def test_check_permission_without_method_is_allowed(self):
        class BareAdmin:
            pass

        request = create_mock_request(object())
        assert check_permission(request, BareAdmin(), "view") is True

    def test_check_module_permission_without_admin_or_method(self):
        request = create_mock_request(object())
        assert check_module_permission(request, None) is True

        class BareAdmin:
            pass

        assert check_module_permission(request, BareAdmin()) is True

    def test_get_admin_queryset_without_admin(self):
        qs = get_admin_queryset(Author, None, create_mock_request())
        assert qs.model is Author

    def test_check_inline_permission_defaults(self):
        _, author_admin = get_model_admin("author")
        request = create_mock_request(object())
        inline_class = author_admin.inlines[0]
        assert check_inline_permission(None, author_admin, request, None, "add") is True
        assert check_inline_permission(inline_class, None, request, None, "add") is True
        assert check_inline_permission(inline_class, author_admin, request, None, "frobnicate") is True

    def test_check_inline_permission_denies_on_error(self):
        class ExplodingInline:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("cannot instantiate")

        _, author_admin = get_model_admin("author")
        request = create_mock_request(object())
        assert check_inline_permission(ExplodingInline, author_admin, request, None, "add") is False


class TestMetaHelpers:
    def test_json_safe_admin_item_for_callables(self):
        def some_callable():
            pass

        assert _json_safe_admin_item(some_callable).endswith("some_callable")
        assert isinstance(_json_safe_admin_item(len), str)


@pytest.mark.asyncio
@pytest.mark.django_db
class TestInlineCreateReadonly:
    """Creating an inline row must reject readonly fields (crud fallback path)."""

    async def test_inline_create_with_readonly_field_is_rejected(self):
        from contextlib import contextmanager  # noqa: PLC0415

        @contextmanager
        def readonly_title():
            _, author_admin = get_model_admin("author")
            inline_class = author_admin.inlines[0]
            original = getattr(inline_class, "readonly_fields", ())
            inline_class.readonly_fields = ["title"]
            try:
                yield
            finally:
                inline_class.readonly_fields = original

        uid = unique_id()
        author = await make_author(uid)
        user = await make_superuser(uid)
        request = create_mock_request(user)

        with readonly_title():
            result = await handle_update(
                "author",
                {"id": author.pk, "data": {}, "inlines": {"article": [{"title": "New", "content": "c"}]}},
                request,
            )
        errors = json.loads(result[0].text)["inlines"]["errors"]
        assert any("readonly" in e.get("error", "").lower() for e in errors), errors
