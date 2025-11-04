# Guide: Litestar Integration

`advanced-alchemy` provides powerful integration helpers for Litestar through the `SQLAlchemyPlugin` and the `providers` module. These helpers simplify dependency injection for services and automatically generate complex filtering and pagination dependencies based on a simple configuration.

## 1. Setup

First, configure the `SQLAlchemyPlugin` in your Litestar application.

```python
from litestar import Litestar
from advanced_alchemy.extensions.litestar import SQLAlchemyPlugin, SQLAlchemyAsyncConfig

# Configure the database connection
alchemy_config = SQLAlchemyAsyncConfig(connection_string="...")

# Configure the plugin
alchemy_plugin = SQLAlchemyPlugin(config=alchemy_config)

# Include the plugin in your app
app = Litestar(plugins=[alchemy_plugin], ...)
```

## 2. Basic Dependency Injection

The `providers.create_service_dependencies()` function is the easiest way to create dependencies for a service and its filters. You typically use it in a controller's `dependencies` dictionary.

```python
from litestar import Controller
from advanced_alchemy.extensions.litestar import providers
from . import services, models as m

class TagController(Controller):
    path = "/tags"
    dependencies = providers.create_service_dependencies(
        # The service class to inject
        services.TagService,
        # The key for the injected service dependency
        key="tags_service",
        # Eager loading configuration (see below)
        load=[m.Tag.workspaces],
        # Filter configuration (see below)
        filters={
            "id_filter": UUID,
            "created_at": True,
            "updated_at": True,
            "sort_field": "name",
            "search": "name,slug,description",
        },
    )
    # ... controller methods
```

## 3. Advanced Dependency Composition

For more complex scenarios, you may need to create the service and filter dependencies separately. This gives you more control, for example, when your service provider requires custom logic.

The pattern is to:

1. Create your service dependency manually using `Provide`.
2. Create your filter dependencies using `providers.create_filter_dependencies()`.
3. Merge the two dictionaries into the controller's `dependencies`.

```python
from litestar import Controller
from litestar.di import Provide
from advanced_alchemy.extensions.litestar.providers import create_filter_dependencies
from . import services, models as m

# Assume provide_workspaces_service is a custom provider function
# that yields a WorkspaceService instance.
async def provide_workspaces_service(db_session: AsyncSession) -> AsyncGenerator[services.WorkspaceService, None]:
    async with services.WorkspaceService.new(session=db_session) as service:
        yield service

class WorkspaceController(Controller):
    path = "/workspaces"
    dependencies = {
        # 1. Manual service dependency
        "workspaces_service": Provide(provide_workspaces_service),
    } | create_filter_dependencies(
        # 2. Automatic filter dependencies
        {
            "id_filter": UUID,
            "search": "name,customer_name,description",
            "search_ignore_case": True,
            "pagination_type": "limit_offset",
            "pagination_size": 20,
            "created_at": True,
            "updated_at": True,
            "sort_field": "created_at",
            "sort_order": "desc",
        },
    )
    # ... controller methods
```

## 4. Using Injected Dependencies

Once configured, you can type-hint the service and the generated `filters` list in your route handlers.

```python
from litestar import get
from litestar.params import Dependency
from advanced_alchemy.filters import FilterTypes

@get("/")
async def list_items(
    self,
    # Injects the configured service instance
    my_service: services.MyService,
    # Injects a list of filter objects based on query parameters
    filters: list[FilterTypes] = Dependency(skip_validation=True),
) -> ...:
    results, total = await my_service.list_and_count(*filters)
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
