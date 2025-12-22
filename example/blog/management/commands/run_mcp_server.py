"""Management command to run the MCP server."""
import asyncio
from django.core.management.base import BaseCommand
from django_admin_mcp import run_mcp_server


class Command(BaseCommand):
    """Run the MCP server for Django admin."""
    help = 'Run the MCP server for Django admin models'

    def handle(self, *args, **options):
        """Handle the command execution."""
        self.stdout.write(self.style.SUCCESS('Starting MCP server...'))
        asyncio.run(run_mcp_server())
