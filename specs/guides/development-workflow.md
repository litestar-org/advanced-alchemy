# Development Workflow Guide

This document outlines the development workflow for the `advanced-alchemy` project.

## Setup

1.  **Install `uv`**: `make install-uv`
2.  **Install dependencies**: `make install`

## Gemini Agent Workflow

This project uses a checkpoint-based workflow enforced by the Gemini agent.

1.  **/prd "feature description"**: Creates a Product Requirements Document in `specs/active/`.
2.  **/implement <slug>**: Implements the feature based on the PRD.
3.  **/test <slug>**: Creates and runs tests for the implementation. (This is usually triggered automatically)
4.  **/review <slug>**: Performs final quality checks and archives the workspace. (This is usually triggered automatically)

Refer to the `.gemini/commands/*.toml` files for the detailed checkpoint requirements for each phase.

## Git Workflow

1.  Create a feature branch from `main`.
2.  Implement the feature using the Gemini agent workflow.
3.  Push the feature branch and create a pull request.
4.  Ensure all CI checks pass.
5.  Request a review.
