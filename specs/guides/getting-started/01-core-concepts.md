# Guide: Core Concepts

Welcome to `advanced-alchemy`! This guide introduces the foundational architectural patterns that underpin the library. Understanding these concepts is the key to building robust, scalable, and maintainable applications.

The two core patterns are:

1.  **The Repository Pattern**: This pattern provides a clean abstraction for all data access. It decouples your business logic from the specifics of your database, making your code easier to test and reason about. All database queries, whether simple or complex, are encapsulated within a `Repository`.

2.  **The Service Layer**: This pattern sits on top of the repository. The `Service` is responsible for orchestrating business logic. It calls repository methods to interact with the database and contains the core logic of your application. Your API controllers should talk to services, not directly to repositories.

By layering your application this way, you create a clear separation of concerns:

-   **Controllers (API Layer)**: Handle HTTP requests and responses. They are thin and delegate all work to the service layer.
-   **Services (Business Logic Layer)**: Contain the core application logic. They orchestrate operations, handle data validation, and call repositories.
-   **Repositories (Data Access Layer)**: Manage all interactions with the database.

This architecture, often called a "three-layer" or "domain-centric" architecture, is the foundation of `advanced-alchemy`. The following guides will explore the `Repository` and `Service` layers in detail.
