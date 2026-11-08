===================================
Litestar Services, Filters and DTOs
===================================

When building CRUD routes in Litestar, you rarely want to wire up ``db_session`` manually or hand-write query parameters for pagination, search, and sorting on every controller.

Advanced Alchemy provides two Litestar helpers that remove that boilerplate:

1. **Service & Filter Dependencies** (``create_service_dependencies``) — injects your service and pre-built query filters directly into controller methods.
2. **SQLAlchemy DTOs** (``SQLAlchemyDTO``) — generates Litestar request and response DTOs straight from your SQLAlchemy models.

Injecting Services and Query Filters
------------------------------------

Declare ``dependencies = create_service_dependencies(...)`` on a Litestar ``Controller`` to inject both your service and a ``filters: list[FilterTypes]`` parameter with automatic OpenAPI query parameters:

.. code-block:: python

    from typing import Annotated
    from uuid import UUID
    from litestar import Controller, get
    from litestar.params import Dependency
    from sqlalchemy.orm import Mapped
    from advanced_alchemy.extensions.litestar import base, filters, providers, repository, service


    class ProductModel(base.UUIDAuditBase):
        __tablename__ = "litestar_dto_product"
        name: Mapped[str]


    class ProductRepository(repository.SQLAlchemyAsyncRepository[ProductModel]):
        model_type = ProductModel


    class ProductService(service.SQLAlchemyAsyncRepositoryService[ProductModel, ProductRepository]):
        repository_type = ProductRepository


    class ProductController(Controller):
        path = "/products"
        dependencies = providers.create_service_dependencies(
            ProductService,
            key="products_service",
            filters=providers.FilterConfig(
                id_filter=UUID,
                search="name",
                pagination_type="limit_offset",
                pagination_size=20,
                created_at=True,
                updated_at=True,
            ),
        )

        @get("/")
        async def list_products(
            self,
            products_service: ProductService,
            filters: Annotated[list[filters.FilterTypes], Dependency(skip_validation=True)],
        ) -> list[ProductModel]:
            results, _ = await products_service.get_many_and_count(*filters)
            return list(results)

If a route only needs the service without query filters, use ``create_service_provider(ProductService)`` instead.

Auto-Generating DTOs from Models
--------------------------------

Instead of maintaining separate schema classes for simple tables, ``SQLAlchemyDTO`` inspects your SQLAlchemy columns, relationships, ``@property``, and ``@cached_property`` attributes automatically:

.. tab-set::

    .. tab-item:: Read DTO (with @property)

        .. code-block:: python

            from functools import cached_property
            from sqlalchemy.orm import Mapped
            from advanced_alchemy.extensions.litestar import SQLAlchemyDTO, SQLAlchemyDTOConfig, base


            class UserAccount(base.UUIDAuditBase):
                __tablename__ = "litestar_dto_user_account"
                first_name: Mapped[str]
                last_name: Mapped[str]
                password_hash: Mapped[str]

                @property
                def full_name(self) -> str:
                    return f"{self.first_name} {self.last_name}"

                @cached_property
                def initials(self) -> str:
                    return f"{self.first_name[:1]}{self.last_name[:1]}".upper()


            class UserReadDTO(SQLAlchemyDTO[UserAccount]):
                config = SQLAlchemyDTOConfig(
                    exclude={"password_hash"},
                    rename_strategy="camel",
                )

    .. tab-item:: Write & Patch DTOs

        .. code-block:: python

            class UserCreateDTO(SQLAlchemyDTO[UserAccount]):
                config = SQLAlchemyDTOConfig(
                    exclude={"id", "created_at", "updated_at", "full_name", "initials"},
                )


            class UserPatchDTO(SQLAlchemyDTO[UserAccount]):
                config = SQLAlchemyDTOConfig(
                    exclude={"id", "created_at", "updated_at", "full_name", "initials"},
                    partial=True,
                )

Related Guides
--------------

* :doc:`/usage/frameworks/litestar` — Litestar plugin setup and complete runnable app.
* :doc:`/usage/frameworks/litestar_sessions` — Transactions, multi-binds, and server-side session stores.
* :doc:`/reference/extensions/litestar/dto` — ``SQLAlchemyDTO`` and ``SQLAlchemyDTOConfig`` API reference.
