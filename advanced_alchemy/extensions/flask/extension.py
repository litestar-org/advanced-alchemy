"""Main module."""

import os
from pathlib import Path
from typing import Optional
from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.config.sync import SQLAlchemySyncConfig

from flask import Flask 
from advanced_alchemy.exceptions import AdvancedAlchemyError
 

class AdvancedAlchemy:
    app: Optional[Flask] = None 

    def __init__(self, app: Optional[Flask] = None, db: SQLALchemy ):
        self.app = app 
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask):
        if "advanced_alchemy" in app.extensions:
            raise AdvancedAlchemyError(
                "This extension is already registered on this Flask app."
            )

        app.extensions["advanced_alchemy"] = self

        config = app.config
        if config.get("SQLALCHEMY_DATABASE_URI"):
            app.after_request(self.after_request)

 