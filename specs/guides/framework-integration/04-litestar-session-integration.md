# Guide: Litestar Session Integration

A core feature of the `advanced-alchemy` Litestar integration is its robust and automatic management of database sessions. The `SQLAlchemyPlugin` handles the lifecycle of database connections and provides sessions to your application's components through Litestar's dependency injection system.

## 1. The Role of the `SQLAlchemyPlugin`

The `SQLAlchemyPlugin` is responsible for:
-   **Engine Management:** Creating and managing the lifecycle of the SQLAlchemy `Engine` instance(s) based on your provided configuration.
-   **Session Provision:** Making a request-scoped `AsyncSession` (or `Session` for sync applications) available for dependency injection.
-   **Automatic Transaction Handling:** By default, the session provided by the plugin is configured to automatically handle the transaction lifecycle (begin, commit, rollback) for each request.

## 2. Injecting the `AsyncSession`

The most direct way to get a database session is to inject it into your route handlers or, more commonly, into your dependency provider functions.

You can type-hint `AsyncSession` in your function signature, and the `SQLAlchemyPlugin` will ensure that Litestar's DI system provides an active session.

**Example: A Custom Service Provider**

This is the most common pattern. You create a provider function (a dependency) that itself depends on the `AsyncSession`. This provider then uses the session to instantiate a repository or service.

```python
# In your dependencies.py or services.py

from sqlalchemy.ext.asyncio import AsyncSession
from .services import MyService

async def provide_my_service(db_session: AsyncSession) -> MyService:
    """
    This function is a dependency provider.
    Litestar will inject an `AsyncSession` into the `db_session` parameter.
    """
    return MyService(session=db_session)
```

You would then use this provider in your controller:

```python
# In your controllers.py

from litestar.controller import Controller
from litestar.di import Provide
from .dependencies import provide_my_service
from .services import MyService

class MyController(Controller):
    dependencies = {"my_service": Provide(provide_my_service)}
    
    @get("/")
    async def my_handler(self, my_service: MyService) -> ...:
        # The `my_service` instance has been created with a request-scoped session.
        return await my_service.list()
```

## 3. Session Management in Multi-Database Setups

The session integration works seamlessly with the multi-database configuration described in the [Multiple Database Setup Guide](./14-multiple-database-setup.md).

-   **Automatic Resolution:** When you use an `advanced-alchemy` `Repository` or `Service`, the underlying session is automatically routed to the correct database based on the model's `bind_key`. You do not need to do anything special to get a session for a specific database.

-   **Manual Session Injection (Rarely Needed):** If you need to manually inject a session for a *specific* database bind, you can do so, but it requires a custom provider. The `SQLAlchemyPlugin` makes the session for each bind available under a specific key.

    ```python
    from litestar.di import Provide
    from sqlalchemy.ext.asyncio import AsyncSession

    # This provider will inject the session associated with the 'logs' bind key
    def provide_logs_db_session(logs_db_session: AsyncSession) -> AsyncSession:
        return logs_db_session

    # In your controller or app dependencies:
    dependencies = {
        "logs_db_session": Provide(provide_logs_db_session, key="logs_db_session")
    }
    ```

In general, you should rely on the automatic resolution provided by the `Service` and `Repository` classes and only resort to manual session injection for specific, low-level database operations that fall outside the repository pattern.
