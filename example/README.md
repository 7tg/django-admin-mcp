# Example Django Application with django-admin-mcp

This directory contains a simple example Django application demonstrating how to use django-admin-mcp.

## Setup

1. Install dependencies:
```bash
pip install django django-admin-mcp
```

2. Set up the database:
```bash
cd example
python manage.py migrate
python manage.py createsuperuser
```

3. Run the MCP server:
```bash
python manage.py run_mcp_server
```

## Project Structure

- `blog/` - A simple blog app with Article and Author models
- `manage.py` - Django management script
- `example_project/` - Django project settings

## Models

### Author
- name (CharField)
- email (EmailField)
- bio (TextField)

### Article
- title (CharField)
- content (TextField)
- author (ForeignKey to Author)
- published_date (DateTimeField)
- is_published (BooleanField)

## MCP Tools Available

Once the server is running, you'll have access to:

- `list_article`, `get_article`, `create_article`, `update_article`, `delete_article`
- `list_author`, `get_author`, `create_author`, `update_author`, `delete_author`
