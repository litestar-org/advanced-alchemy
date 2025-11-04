# Guide: 3rd Party DI & Dishka Integration

While `advanced-alchemy` provides convenient built-in dependency injection helpers for frameworks like Litestar and FastAPI, it is designed to be compatible with other DI frameworks. This guide demonstrates how to integrate `advanced-alchemy` services with `dishka`, a powerful and flexible DI container.

The principles shown here can be adapted for other DI frameworks like `punq` or `svcs`.

## Core Concepts

The key to integration is to teach your DI container how to provide two things:

1.  A SQLAlchemy `AsyncSession` or `Session`.
2.  Your `advanced-alchemy` `Service` class, which depends on the session.

## Litestar & Dishka Integration Example

This example shows how to set up `dishka` in a Litestar application to inject an `advanced-alchemy` service.

### 1. Define the Service

First, define your `advanced-alchemy` service as you normally would. Here, we use the inline repository pattern.

```python
# In your services.py

from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from .models import MyModel

class MyService(SQLAlchemyAsyncRepositoryService[MyModel]):
    """My service with an inline repository."""
    class Repo(SQLAlchemyAsyncRepository[MyModel]):
        model_type = MyModel
    
    repository_type = Repo
```

### 2. Create the Dishka Provider

Next, create a `dishka.Provider`. This class tells `dishka` how to create and provide instances of your dependencies.

-   **`provide_session`**: This factory method gets the `AsyncEngine` from the Litestar application state (put there by the `SQLAlchemyPlugin`) and creates a request-scoped `AsyncSession`.
-   **`provide_service`**: This factory method depends on the `AsyncSession` provided by the method above and uses it to instantiate `MyService`.

```python
# In your providers.py

from dishka import Provider, Scope, provide
from litestar import Litestar
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from .services import MyService

class MyProvider(Provider):
    
    @provide(scope=Scope.REQUEST)
    async def provide_session(self, app: Litestar) -> AsyncSession:
        """Provide a request-scoped SQLAlchemy session."""
        engine = app.state.db_engine  # Assuming engine is stored in app.state
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as session:
            yield session

    @provide(scope=Scope.REQUEST)
    async def provide_service(self, db_session: AsyncSession) -> MyService:
        """Provide an instance of MyService."""
        return MyService(session=db_session)
```

### 3. Configure the Litestar Application

Finally, tie everything together in your Litestar application setup.

-   Instantiate your `dishka` provider.
-   Create an async container with your provider.
-   Use `setup_dishka` to attach the container to your Litestar app.
-   Use the `FromDishka` dependency marker in your route handler to inject the service.

```python
# In your app.py

from litestar import Litestar, get
from litestar.di import Provide
from dishka import make_async_container
from dishka.integrations.litestar import FromDishka, setup_dishka

from .providers import MyProvider
from .services import MyService

# The @get handler where the service is injected
@get("/")
async def my_handler(my_service: FromDishka[MyService]) -> list[...]:
    """Handler that uses the injected service."""
    return await my_service.list()

# Standard SQLAlchemyPlugin setup
alchemy_plugin = SQLAlchemyPlugin(...) 

# Dishka setup
container = make_async_container(MyProvider())
app = Litestar(
    route_handlers=[my_handler],
    plugins=[alchemy_plugin],
)

# Attach the dishka container to the app
setup_dishka(container=container, app=app)
```

By following this pattern, you can seamlessly integrate `advanced-alchemy`'s powerful service layer with `dishka` or any other dependency injection framework, giving you maximum flexibility in how you structure your application.

## Litestar & svcs Integration Example

This example shows how to set up `svcs` in a Litestar application to inject an `advanced-alchemy` service.

### 1. Define the Service

First, define your `advanced-alchemy` service. This is the same regardless of the DI framework you use.

```python
# In your services.py

from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from .models import MyModel

class MyService(SQLAlchemyAsyncRepositoryService[MyModel]):
    """My service with an inline repository."""
    class Repo(SQLAlchemyAsyncRepository[MyModel]):
        model_type = MyModel
    
    repository_type = Repo
```

### 2. Define Factories

`svcs` works with factories, which are functions that create and clean up your services.

-   **`session_factory`**: An async generator that creates a request-scoped `AsyncSession`. It gets the `AsyncEngine` from the application state.
-   **`service_factory`**: A simple function that depends on the `AsyncSession` to instantiate `MyService`.

```python
# In your factories.py

import svcs
from litestar import Litestar
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .services import MyService

async def session_factory(app: Litestar) -> AsyncGenerator[AsyncSession, None]:
    """Create a request-scoped SQLAlchemy session."""
    engine = app.state.db_engine
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session

def service_factory(db_session: AsyncSession) -> MyService:
    """Create an instance of MyService."""
    return MyService(session=db_session)
```

### 3. Configure the Litestar Application

Next, configure the Litestar application to use `svcs`.

-   Create an `svcs.Registry`.
-   Register your factories with the registry.
-   Use a `lifespan` context manager to manage the `svcs` registry's lifecycle.
-   Add the `svcs.litestar.SVCSMiddleware` to the application's middleware stack.

```python
# In your app.py
import svcs
from contextlib import asynccontextmanager
from litestar import Litestar, get
from svcs.litestar import SVCSMiddleware, DepContainer

from .factories import session_factory, service_factory
from .services import MyService

# 1. Create the registry and register factories
registry = svcs.Registry()
registry.register_factory(AsyncSession, session_factory)
registry.register_factory(MyService, service_factory)

# 2. Create a lifespan manager
@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    yield
    await registry.aclose()

# The @get handler where the service is injected
@get("/")
async def my_handler(services: DepContainer) -> list[...]:
    """Handler that uses the injected service."""
    my_service = await services.aget(MyService)
    return await my_service.list()

# Standard SQLAlchemyPlugin setup
alchemy_plugin = SQLAlchemyPlugin(...) 

# 3. Create the app with middleware and lifespan
app = Litestar(
    route_handlers=[my_handler],
    plugins=[alchemy_plugin],
    middleware=[SVCSMiddleware],
    lifespan=[lifespan],
)
```

### 4. Injecting the Service

In your route handler, you inject the `svcs.litestar.DepContainer`. From the container, you can asynchronously get any registered service using `await services.aget(MyService)`.

This pattern provides a clean and explicit way to manage dependencies, fully integrating the power of `svcs` with `advanced-alchemy` services.
