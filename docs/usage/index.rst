=====
Usage
=====

This guide provides detailed information about using Advanced Alchemy in your applications.
Each section builds upon the previous ones to give you a complete understanding of the library's capabilities.

.. toctree::
    :maxdepth: 2
    :caption: Core Features

    modeling
    repositories
    services
    utilities

.. toctree::
    :maxdepth: 2
    :caption: Framework Integration

    frameworks/litestar
    frameworks/fastapi

The guide follows a practical approach, building a complete blog application to demonstrate Advanced Alchemy's features:

1. **Modeling**: Learn how to define SQLAlchemy models using Advanced Alchemy's enhanced base classes and mixins
2. **Repositories**: Implement type-safe database operations using the repository pattern
3. **Services**: Build business logic layers with automatic schema validation and transformation
4. **Framework Integration**: Integrate with popular frameworks like Litestar and FastAPI

Each section includes:

- Detailed explanations of core concepts
- Practical code examples
- Best practices and common patterns
- Performance considerations
- Error handling strategies

Prerequisites
-------------

Before starting, ensure you have:

- Python 3.8+
- SQLAlchemy 2.0+
- A supported async database driver (asyncpg, aiomysql, or aiosqlite)
- Basic understanding of SQLAlchemy and async Python

Getting Started
---------------

The best way to follow this guide is sequentially, as each section builds upon concepts introduced in previous sections. The example blog application will grow in complexity as we progress through the guide.

For framework-specific guidance, refer to the respective integration sections after completing the core concepts.
