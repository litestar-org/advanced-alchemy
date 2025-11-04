# Guide: Utilities and Helper Methods

`advanced-alchemy` includes a variety of utility functions and helper methods designed to simplify common tasks, from data manipulation to asynchronous programming and reflection.

## General Utilities (`advanced_alchemy.utils`)

This section covers the general-purpose functions available in the `utils` modules.

### Dataclass Utilities (`utils.dataclass`)

These functions provide helpers for working with Python's dataclasses.

-   **`is_dataclass_instance(obj)`**: A type guard that checks if an object is a dataclass instance.
-   **`simple_asdict(obj)`**: A non-recursive, non-copying version of the standard library's `asdict`. It's a faster way to convert a dataclass to a dictionary, especially when the dataclass contains complex, non-serializable objects.
-   **`extract_dataclass_fields(dt, ...)`**: Returns a tuple of `dataclasses.Field` objects for a given dataclass instance, with options to include or exclude fields.
-   **`extract_dataclass_items(dt, ...)`**: Returns a tuple of `(name, value)` pairs for a given dataclass instance.

### Module Loading (`utils.module_loader`)

-   **`import_string(dotted_path)`**: Imports an object from a module using a dotted path string (e.g., `"my_app.services.UserService"`). This is useful for dynamically loading classes or functions based on a configuration value.
-   **`module_to_os_path(dotted_path)`**: Converts a dotted module path to an absolute filesystem path.

### Text Manipulation (`utils.text`)

-   **`slugify(value)`**: Converts a string into a URL-friendly "slug" (e.g., `"My Awesome Post"` becomes `"my-awesome-post"`).
-   **`camelize(string)`**: Converts a `snake_case` string to `camelCase`.
-   **`check_email(email)`**: Performs a basic validation check on an email string.

### Asynchronous Utilities (`utils.sync_tools`)

These functions are powerful tools for working in mixed sync/async codebases.

-   **`run_(async_function)`**: A decorator or function that takes an `async` function and returns a synchronous version that will run the async function in a new event loop.
-   **`await_(async_function)`**: Converts an `async` function to a synchronous one, but attempts to run it on the *currently running* event loop. This is useful for calling async code from a sync function that was itself called from an async context.
-   **`async_(function)`**: A decorator or function that takes a regular `sync` function and returns an `async` version that runs the synchronous code in a thread pool, preventing it from blocking the event loop.

### Fixture Loading (`utils.fixtures`)

-   **`open_fixture(fixtures_path, fixture_name)`**: Loads a JSON fixture file. It automatically handles `.json`, `.json.gz`, and `.json.zip` files.
-   **`open_fixture_async(fixtures_path, fixture_name)`**: An asynchronous version of `open_fixture`.

### Deprecation Warnings (`utils.deprecation`)

-   **`@deprecated(version, ...)`**: A decorator to mark a function or method as deprecated, which will issue a `DeprecationWarning` when it's used.
-   **`warn_deprecation(...)`**: A function to manually issue a deprecation warning.

## Service and Repository Helpers

The `SQLAlchemy...Service` and `SQLAlchemy...Repository` classes provide several `is_*` type guard methods that are useful for introspection and handling different types of input data.

-   **`is_model_instance(value)`**: Checks if a value is an instance of the repository's or service's configured `model_type`.
-   **`is_dict(value)`**: Checks if a value is a dictionary.
-   **`is_list_of_dicts(value)`**: Checks if a value is a list of dictionaries.
-   **`is_list_of_models(value)`**: Checks if a value is a list of model instances.

### Usage Example

These helpers are particularly useful inside service methods when you need to handle different data shapes.

```python
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService, ModelDictT
from .models import MyModel

class MyService(SQLAlchemyAsyncRepositoryService[MyModel]):
    # ...

    async def create(self, data: ModelDictT[MyModel]) -> MyModel:
        # You can use the helpers to inspect the data
        if self.is_dict(data):
            print("Creating a single model from a dictionary.")
        
        if self.is_model_instance(data):
            print("Creating from an existing model instance.")

        return await super().create(data)
```
