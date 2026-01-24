from pathlib import Path

from setuptools import find_packages, setup

# Read the README file
readme_file = Path(__file__).parent / "README.md"
long_description = ""
if readme_file.exists():
    long_description = readme_file.read_text(encoding="utf-8")

setup(
    name="django-admin-mcp",
    version="0.1.0",
    description="Django admin MCP integration - expose Django admin models to MCP clients",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Barbaros Goren",
    author_email="gorenbarbaros@gmail.com",
    url="https://github.com/7tg/django-admin-mcp",
    project_urls={
        "Homepage": "https://github.com/7tg/django-admin-mcp",
        "Documentation": "https://7tg.github.io/django-admin-mcp/",
        "Repository": "https://github.com/7tg/django-admin-mcp",
        "Issues": "https://github.com/7tg/django-admin-mcp/issues",
        "Changelog": "https://github.com/7tg/django-admin-mcp/releases",
    },
    packages=find_packages(exclude=["tests", "tests.*", "example", "example.*"]),
    install_requires=[
        "django>=3.2",
        "pydantic>=2.0",
    ],
    python_requires=">=3.10",
    license="GPL-3.0-or-later",
    keywords=[
        "django",
        "admin",
        "mcp",
        "model-context-protocol",
        "llm",
        "ai",
        "automation",
        "api",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Framework :: Django",
        "Framework :: Django :: 3.2",
        "Framework :: Django :: 4.0",
        "Framework :: Django :: 4.1",
        "Framework :: Django :: 4.2",
        "Framework :: Django :: 5.0",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    ],
)
