from setuptools import setup, find_packages

setup(
    name="django-admin-mcp",
    version="0.1.0",
    description="Django admin MCP integration - expose Django admin models to MCP clients",
    author="django-admin-mcp contributors",
    packages=find_packages(),
    install_requires=[
        "django>=3.2",
        "mcp>=0.9.0",
    ],
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Framework :: Django",
        "Framework :: Django :: 3.2",
        "Framework :: Django :: 4.0",
        "Framework :: Django :: 4.1",
        "Framework :: Django :: 4.2",
        "Framework :: Django :: 5.0",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
