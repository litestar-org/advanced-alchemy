from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import Mapped, sessionmaker

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.repository import SQLAlchemySyncRepository

SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
db = SQLAlchemy(app)


class Message(UUIDBase):
    text: Mapped[str]


class MessageRepository(SQLAlchemySyncRepository[Message]):
    model_type = Message


# Working
with app.app_context():
    with db.engine.begin() as conn:
        Message.metadata.create_all(conn)

    session = sessionmaker(db.engine)()

    repo = MessageRepository(session=session)
    repo.add(Message(text="Hello, world!"))

    message = repo.list()[0]
    assert message.text == "Hello, world!"  # noqa: S101


# Not working
with app.app_context():
    with db.engine.begin() as conn:
        Message.metadata.create_all(conn)

    session = db.session
    repo = MessageRepository(session=session)
    repo.add(Message(text="Hello, world!"))

    message = repo.list()[0]
    assert message.text == "Hello, world!"  # noqa: S101
