# Guide: FastAPI Integration

`advanced-alchemy` provides a powerful integration helper for FastAPI: the `AdvancedAlchemy` class. This helper simplifies dependency injection for services and automatically generates complex filtering and pagination dependencies based on a simple configuration.

## 1. Setup

Instantiate `AdvancedAlchemy` and connect it to your FastAPI app.

```python
from fastapi import FastAPI
from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, SQLAlchemyAsyncConfig

alchemy_config = SQLAlchemyAsyncConfig(connection_string="...")
app = FastAPI()
alchemy = AdvancedAlchemy(config=alchemy_config, app=app)
```

## 2. Service & Filter Dependencies

In FastAPI, you use `Depends` with the `alchemy.provide_service()` and `alchemy.provide_filters()` helpers directly in your route handler's signature.

```python
from typing import Annotated
from fastapi import APIRouter, Depends
from advanced_alchemy.filters import FilterTypes
from . import services, models as m

router = APIRouter()

@router.get("/")
async def list_tags(
    # Injects the configured TagService instance
    tags_service: Annotated[
        services.TagService,
        Depends(alchemy.provide_service(services.TagService, load=[m.Tag.workspaces]))
    ],
    # Injects a list of filter objects based on query parameters
    filters: Annotated[
        list[FilterTypes],
        Depends(
            alchemy.provide_filters({
                "id_filter": UUID,
                "created_at": True,
                "updated_at": True,
                "sort_field": "name",
                "search": "name,slug,description",
            })
        )
    ],
) -> ...:
    results, total = await tags_service.list_and_count(*filters)
    # ...
```

## Configuring Relationship Loading (`load`)

The `load` parameter is a powerful feature that simplifies eager loading. It accepts:

- **A SQLAlchemy `Load` object**: e.g., `selectinload(MyModel.relationship)`.
- **A model's instrumented attribute**: e.g., `MyModel.relationship`. `advanced-alchemy` will intelligently choose `selectinload` for collection relationships (`list[]`) and `joinedload` for scalar relationships (`Model | None`). This is the recommended shorthand.
- **The string `"*"`**: This wildcard will eager load all relationships on the model using a `joinedload`. Use with caution as it can be inefficient.

## Configuring Filters

The `filters` dictionary is a declarative way to generate dependencies that parse query parameters into `Filter` objects.

- `"id_filter": <type>`: Enables filtering by a collection of IDs (e.g., `/tags?ids=...`).
- `"created_at": True`: Enables `createdBefore` and `createdAfter` timestamp filters.
- `"updated_at": True`: Enables `updatedBefore` and `updatedAfter` timestamp filters.
- `"sort_field": "<field_name>"`: Enables `orderBy` and `sortOrder` query parameters.
- `"search": "<field_1>,<field_2>"`: Enables a `searchString` query parameter that performs a case-insensitive search across the specified fields.
- `"pagination_type": "limit_offset"`: Enables `currentPage` and `pageSize` parameters for pagination.
