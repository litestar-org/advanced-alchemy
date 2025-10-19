===================
Schema Integration
===================

Advanced Alchemy services support multiple schema libraries for data transformation and validation.

Prerequisites
=============

Understanding of :doc:`basics` recommended.

Schema Libraries
================

Advanced Alchemy services support:

- **Pydantic** - Popular validation library with extensive features
- **Msgspec** - High-performance serialization with native validation
- **attrs** - Lightweight data classes with optional cattrs integration

Pydantic Models
===============

Pydantic provides robust validation with extensive ecosystem support:

.. code-block:: python

    from pydantic import BaseModel, EmailStr, constr
    from typing import Optional
    from datetime import datetime

    class UserCreate(BaseModel):
        name: constr(min_length=1, max_length=100)
        email: EmailStr
        age: Optional[int] = None

    class UserResponse(BaseModel):
        id: int
        name: str
        email: str
        age: Optional[int]
        created_at: datetime
        updated_at: datetime

        model_config = {"from_attributes": True}

    # Use with service
    user_data = service.to_schema(user_model, schema_type=UserResponse)

Pydantic features:

- Comprehensive validation rules
- Email, URL, and custom validators
- Nested models support
- JSON serialization built-in
- OpenAPI integration

**Note**: Pydantic v2 required. Configure with ``model_config = {"from_attributes": True}`` for SQLAlchemy compatibility.

Msgspec Structs
===============

Msgspec provides high-performance serialization:

.. code-block:: python

    from msgspec import Struct
    from typing import Optional
    from datetime import datetime

    class UserCreate(Struct):
        name: str
        email: str
        age: Optional[int] = None

    class UserResponse(Struct):
        id: int
        name: str
        email: str
        age: Optional[int]
        created_at: datetime
        updated_at: datetime

    # Use with service
    user_data = service.to_schema(user_model, schema_type=UserResponse)

Msgspec characteristics:

- Fast serialization/deserialization
- Native validation
- Type-safe
- Smaller memory footprint than Pydantic
- Supports JSON, MessagePack, YAML

Attrs Classes
=============

Attrs provides lightweight data classes:

.. code-block:: python

    from attrs import define
    from typing import Optional
    from datetime import datetime

    @define
    class UserCreate:
        name: str
        email: str
        age: Optional[int] = None

    @define
    class UserResponse:
        id: int
        name: str
        email: str
        age: Optional[int]
        created_at: datetime
        updated_at: datetime

    # Use with service
    user_data = service.to_schema(user_model, schema_type=UserResponse)

.. note::

    **Enhanced attrs Support with cattrs**: When both ``attrs`` and ``cattrs`` are installed,
    Advanced Alchemy automatically uses ``cattrs.structure()`` and ``cattrs.unstructure()``
    for improved performance and type-aware serialization. This provides better handling of
    complex types, nested structures, and custom converters.

Attrs characteristics:

- Lightweight, minimal dependencies
- Simple API
- cattrs integration for advanced features
- Good performance

Schema Conversion
=================

to_schema Method
----------------

Convert models to schemas:

.. code-block:: python

    # Single record
    user_schema = service.to_schema(user_model, schema_type=UserResponse)

    # Multiple records
    users_schemas = service.to_schema(users_list, schema_type=UserResponse)

    # SQLAlchemy Row objects
    row_schema = service.to_schema(row_object, schema_type=UserResponse)

    # With pagination
    results, total = await service.list_and_count(*filters)
    paginated_response = service.to_schema(
        results,
        total,
        filters=filters,
        schema_type=UserResponse
    )

Supports:

- SQLAlchemy model instances
- SQLAlchemy Row objects
- RowMapping objects
- Lists of any of the above
- Pagination results with total count and filter metadata

to_model Method
---------------

Convert schemas to models:

.. code-block:: python

    # Automatic in CRUD operations
    user = await service.create(UserCreate(name="Alice", email="alice@example.com"))

    # Manual conversion (advanced)
    user_model = await service.to_model(user_create_data, operation="create")

Operation parameter values:

- ``"create"`` - Preparing for insertion
- ``"update"`` - Preparing for modification
- ``None`` - General conversion

SQLAlchemy Query Result Support
================================

Services handle SQLAlchemy query results directly:

.. code-block:: python

    from sqlalchemy import select

    # Direct support for SQLAlchemy Row objects
    query_results = await session.execute(select(User))
    rows = query_results.fetchall()  # Returns list[Row[Any]]

    # Convert Row objects to schema types
    user_data = service.to_schema(rows[0], schema_type=UserSchema)
    users_paginated = service.to_schema(rows, schema_type=UserSchema)

    # Also supports RowMapping objects
    row_mapping_results = await session.execute(select(User)).mappings()
    mapping_data = service.to_schema(row_mapping_results.first(), schema_type=UserSchema)

Characteristics:

- No manual conversion needed
- Works with complex queries
- Handles aggregations
- Preserves type safety

Implementation Patterns
=======================

Schema Validation in Services
------------------------------

Services validate input automatically:

.. code-block:: python

    from pydantic import BaseModel, validator

    class PostCreate(BaseModel):
        title: str
        content: str
        published: bool = False

        @validator("title")
        def title_must_not_be_empty(cls, v):
            if not v.strip():
                raise ValueError("title cannot be empty")
            return v

    # Validation happens automatically
    try:
        post = await post_service.create(PostCreate(title="", content="Test"))
    except ValueError as e:
        print(f"Validation error: {e}")

Pydantic validators run before database operations.

Nested Schemas
--------------

Handle nested relationships:

.. code-block:: python

    from pydantic import BaseModel
    from typing import List

    class TagResponse(BaseModel):
        id: int
        name: str
        slug: str

        model_config = {"from_attributes": True}

    class PostResponse(BaseModel):
        id: int
        title: str
        content: str
        tags: List[TagResponse]  # Nested schema

        model_config = {"from_attributes": True}

    # Automatic nested conversion
    post_with_tags = await post_service.get(post_id)
    response = post_service.to_schema(post_with_tags, schema_type=PostResponse)
    # response.tags is list of TagResponse instances

Nested schemas convert automatically when models have relationships.

Partial Updates
---------------

Handle optional fields for updates:

.. code-block:: python

    from pydantic import BaseModel
    from typing import Optional

    class PostUpdate(BaseModel):
        title: Optional[str] = None
        content: Optional[str] = None
        published: Optional[bool] = None

    # Update only provided fields
    await post_service.update(
        post_id,
        PostUpdate(title="New Title"),  # Only updates title
        auto_commit=True
    )

Optional fields allow partial updates.

Technical Constraints
=====================

Schema Library Comparison
--------------------------

Different libraries have distinct characteristics:

**Pydantic**

- Validation: Comprehensive validators, custom rules
- Performance: Moderate (validation overhead)
- Features: Extensive ecosystem, OpenAPI support
- Serialization: JSON via ``model_dump_json()``

**Msgspec**

- Validation: Native type validation
- Performance: High (optimized Rust/C core)
- Features: Multiple formats (JSON, MessagePack, YAML)
- Serialization: Fast native serialization

**Attrs**

- Validation: Basic (with cattrs enhancement)
- Performance: High (minimal overhead)
- Features: Lightweight, simple API
- Serialization: Via cattrs or manual

Choose based on requirements.

Pydantic from_attributes Requirement
------------------------------------

Pydantic v2 requires explicit configuration:

.. code-block:: python

    # ✅ Correct - enables ORM mode
    class UserResponse(BaseModel):
        id: int
        name: str

        model_config = {"from_attributes": True}

    # ❌ Incorrect - missing configuration
    class UserResponse(BaseModel):
        id: int
        name: str
        # Will fail when converting from SQLAlchemy models

Always include ``model_config = {"from_attributes": True}`` for Pydantic schemas.

Schema Field Matching
----------------------

Schema fields must match model attributes:

.. code-block:: python

    # ✅ Correct - fields match model
    class UserResponse(BaseModel):
        id: int
        name: str  # Matches User.name
        email: str  # Matches User.email

    # ❌ Incorrect - field name mismatch
    class UserResponse(BaseModel):
        id: int
        username: str  # User model has 'name', not 'username'
        # Will fail during conversion

Field names must match model attributes or use aliases.

Next Steps
==========

For complex business logic, see :doc:`advanced`.

Related Topics
==============

- :doc:`advanced` - Complex operations and custom logic
- :doc:`basics` - Service pattern fundamentals
- :doc:`../frameworks/index` - Framework integration examples
