"""
Tests for django_admin_mcp.server module
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from django_admin_mcp.server import get_server, get_registered_models, run_mcp_server
from django_admin_mcp.mixin import MCPAdminMixin
from tests.models import Author, Article


@pytest.mark.django_db
class TestServerModule:
    """Test suite for server module functions."""

    def test_get_server(self):
        """Test that get_server returns the MCP server instance."""
        server = get_server()
        assert server is not None, "Server should not be None"
        assert server.name == "django-admin-mcp", "Server should have correct name"

    def test_get_registered_models(self):
        """Test that get_registered_models returns a copy of registered models."""
        registered = get_registered_models()

        # Check that models are registered
        assert "author" in registered, "Author model should be registered"
        assert "article" in registered, "Article model should be registered"

        # Check that it returns a copy (not the original dict)
        original = MCPAdminMixin._registered_models
        assert registered is not original, "Should return a copy, not the original"
        assert registered == original, "Copy should equal the original"

        # Verify structure of registered models
        assert "model" in registered["author"], "Should have model key"
        assert "admin" in registered["author"], "Should have admin key"
        assert registered["author"]["model"] == Author, "Should have correct model"

    def test_get_registered_models_isolation(self):
        """Test that modifying returned dict doesn't affect internal state."""
        registered = get_registered_models()
        original_count = len(registered)

        # Modify the returned dict
        registered["fake_model"] = {"model": None, "admin": None}

        # Get it again and check it wasn't affected
        new_registered = get_registered_models()
        assert len(new_registered) == original_count, "Original should not be modified"
        assert "fake_model" not in new_registered, "Original should not have fake model"


@pytest.mark.django_db
@pytest.mark.asyncio
class TestRunMCPServer:
    """Test suite for run_mcp_server function."""

    async def test_run_mcp_server_basic(self):
        """Test that run_mcp_server sets up and runs the server correctly."""
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        with patch('django_admin_mcp.server.stdio_server') as mock_stdio:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=(mock_read_stream, mock_write_stream))
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_stdio.return_value = mock_context

            with patch.object(MCPAdminMixin.get_mcp_server(), 'run', new_callable=AsyncMock) as mock_run:
                await run_mcp_server()

                mock_stdio.assert_called_once()
                mock_run.assert_called_once()
                args = mock_run.call_args[0]
                assert args[0] == mock_read_stream
                assert args[1] == mock_write_stream

    async def test_run_mcp_server_registers_handlers(self):
        """Test that run_mcp_server registers list_tools and call_tool handlers."""
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        list_tools_calls = []
        call_tool_calls = []

        original_server = MCPAdminMixin.get_mcp_server()
        original_list_tools = original_server.list_tools
        original_call_tool = original_server.call_tool

        def mock_list_tools():
            def decorator(func):
                list_tools_calls.append(func)
                return original_list_tools()(func)
            return decorator

        def mock_call_tool():
            def decorator(func):
                call_tool_calls.append(func)
                return original_call_tool()(func)
            return decorator

        with patch('django_admin_mcp.server.stdio_server') as mock_stdio:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=(mock_read_stream, mock_write_stream))
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_stdio.return_value = mock_context

            with patch.object(original_server, 'run', new_callable=AsyncMock):
                with patch.object(original_server, 'list_tools', mock_list_tools):
                    with patch.object(original_server, 'call_tool', mock_call_tool):
                        await run_mcp_server()

                        assert len(list_tools_calls) == 1
                        assert len(call_tool_calls) == 1

    async def test_run_mcp_server_list_tools_includes_find_models(self):
        """Test that the list_tools handler includes find_models tool."""
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        captured_handler = None
        original_server = MCPAdminMixin.get_mcp_server()
        original_list_tools = original_server.list_tools

        def capture_list_tools():
            def decorator(func):
                nonlocal captured_handler
                captured_handler = func
                return original_list_tools()(func)
            return decorator

        with patch('django_admin_mcp.server.stdio_server') as mock_stdio:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=(mock_read_stream, mock_write_stream))
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_stdio.return_value = mock_context

            with patch.object(original_server, 'run', new_callable=AsyncMock):
                with patch.object(original_server, 'list_tools', capture_list_tools):
                    await run_mcp_server()

                    assert captured_handler is not None
                    tools = await captured_handler()
                    tool_names = [t.name for t in tools]
                    assert "find_models" in tool_names

    async def test_run_mcp_server_call_tool_delegates(self):
        """Test that the call_tool handler delegates to MCPAdminMixin.handle_tool_call."""
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        captured_handler = None
        original_server = MCPAdminMixin.get_mcp_server()
        original_call_tool = original_server.call_tool

        def capture_call_tool():
            def decorator(func):
                nonlocal captured_handler
                captured_handler = func
                return original_call_tool()(func)
            return decorator

        with patch('django_admin_mcp.server.stdio_server') as mock_stdio:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=(mock_read_stream, mock_write_stream))
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_stdio.return_value = mock_context

            with patch.object(original_server, 'run', new_callable=AsyncMock):
                with patch.object(original_server, 'call_tool', capture_call_tool):
                    with patch.object(MCPAdminMixin, 'handle_tool_call', new_callable=AsyncMock) as mock_handle:
                        mock_handle.return_value = {"result": "success"}

                        await run_mcp_server()

                        assert captured_handler is not None
                        result = await captured_handler(name="test_tool", arguments={"arg": "value"})
                        mock_handle.assert_called_once_with("test_tool", {"arg": "value"})
