# Django Admin MCP Documentation

This directory contains the documentation for Django Admin MCP, deployed to GitHub Pages at [https://7tg.github.io/django-admin-mcp/](https://7tg.github.io/django-admin-mcp/).

## Files

- **index.html** - Main documentation page using Redoc
- **openapi.yaml** - OpenAPI 3.0 specification for the HTTP API
- **_config.yml** - GitHub Pages configuration
- **.nojekyll** - Prevents Jekyll processing

## Local Development

To view the documentation locally:

1. Install a local web server:
   ```bash
   npm install -g http-server
   # or use Python's built-in server
   ```

2. Serve the docs directory:
   ```bash
   cd docs
   http-server
   # or
   python -m http.server 8000
   ```

3. Open your browser to http://localhost:8000

## Deployment

Documentation is automatically deployed to GitHub Pages when changes are pushed to the `main` branch via the `.github/workflows/deploy-docs.yml` workflow.

## Updating Documentation

To update the API documentation:

1. Edit `openapi.yaml` to reflect any API changes
2. Commit and push to the `main` branch
3. GitHub Actions will automatically deploy the updated documentation

## Technology

- **Redoc** - Beautiful API documentation from OpenAPI specs
- **GitHub Pages** - Free hosting for static documentation
- **OpenAPI 3.0** - Industry-standard API specification format
