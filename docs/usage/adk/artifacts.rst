=========
Artifacts
=========

``ADKAsyncArtifactService`` stores artifact metadata in a user-owned model that
subclasses ``ADKArtifactModelMixin``. Artifact bytes are stored as
``FileObject`` values through Advanced Alchemy's storage backend registry.

.. code-block:: python

    from advanced_alchemy.extensions.adk.artifacts import ADKAsyncArtifactService

    artifact_service = ADKAsyncArtifactService(
        db_session,
        artifact_model=ADKArtifact,
        backend_key="adk-artifacts",
    )

    version = await artifact_service.save_artifact(
        app_name="support-bot",
        user_id="user-123",
        session_id="session-123",
        filename="transcript.txt",
        artifact=types.Part(text="hello"),
    )

The default backend key is ``adk-artifacts``. Register a storage backend with
that key, or pass another ``backend_key`` when constructing the service.

Artifact file paths preserve ADK's app/user/session layout:

- session-scoped artifacts: ``{app}/{user}/{session}/{filename}/{version}``
- user-scoped artifacts: ``{app}/{user}/user/{filename}/{version}``

Because artifact blobs are normal ``FileObject`` values, Advanced Alchemy's
file-object session listeners handle upload and delete timing. Blob writes occur
after commit, and rollbacks do not upload orphaned content.
