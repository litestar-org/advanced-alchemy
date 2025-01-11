=====
Usage
=====

This guide demonstrates building a complete blog system using Advanced Alchemy's features. We'll create a system that supports:

- Posts with tags and slugs
- Tag management with automatic deduplication
- Efficient querying and pagination
- Type-safe database operations
- Schema validation and transformation

.. toctree::
    :maxdepth: 2
    :caption: Core Features

    modeling
    repositories
    services
    types
    utilities

.. toctree::
    :maxdepth: 2
    :caption: Framework Integration

    frameworks/litestar
    frameworks/fastapi

The guide follows a practical approach:

1. **Modeling**: Define SQLAlchemy models with Advanced Alchemy's enhanced base classes
2. **Repositories**: Implement type-safe database operations using repositories
3. **Services**: Build business logic with automatic schema validation
4. **Framework Integration**: Integrate with Litestar and FastAPI

Each section includes:

- Concepts and usage overview
- Complete code examples
- Best practices
- Performance considerations
- Error handling strategies

Prerequisites
-------------

- Python 3.8+
- SQLAlchemy 2.0+
- Pydantic v2 or Msgspec (for schema validation)
- Basic understanding of SQLAlchemy and async programming
- Basic understanding of Pydantic or Msgspec
