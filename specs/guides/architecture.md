# Architecture Guide

This document outlines the architecture of the `advanced-alchemy` project.

## Core Concepts

- **Repository Pattern**: Decouples the business logic from the data access layer.
- **Service Layer**: Contains the business logic of the application.
- **Async/Sync Support**: Provides both asynchronous and synchronous implementations for repositories and services.

## Directory Structure

- `advanced_alchemy/repository`: Contains the repository implementations.
- `advanced_alchemy/service`: Contains the service layer implementations.
- `advanced_alchemy/config`: Handles database configuration.
- `advanced_alchemy/extensions`: Provides integrations with web frameworks like Litestar, FastAPI, etc.
