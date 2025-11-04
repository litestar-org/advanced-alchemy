# Guide: Custom SQLAlchemy Types

`advanced-alchemy` provides a rich set of custom SQLAlchemy types to handle common patterns like timezone-aware datetimes, platform-independent UUIDs, data encryption, password hashing, and more.

## Date and Time

### `DateTimeUTC`

This is a `TypeDecorator` that ensures all `datetime` objects are stored in the database as UTC and are returned as timezone-aware `datetime` objects. It's crucial for applications that handle users across different timezones.

**Usage:**

```python
from sqlalchemy.orm import Mapped, mapped_column
from advanced_alchemy.types import DateTimeUTC
import datetime

class MyModel(Base):
    # ...
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTimeUTC(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
```

## Platform-Independent Types

### `GUID`

This type provides a platform-independent way to store `UUID` objects. It automatically uses the best native UUID type available on the target database (e.g., `UUID` on PostgreSQL, `UNIQUEIFIER` on MSSQL) and falls back to `BINARY(16)` or `CHAR(32)` on others.

**Usage:**

```python
from sqlalchemy.orm import Mapped, mapped_column
from advanced_alchemy.types import GUID
from uuid import UUID, uuid4

class MyModel(Base):
    # ...
    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
```

### `JsonB`

This type provides a JSON type that uses the native `JSONB` type on PostgreSQL and CockroachDB, `BLOB` on Oracle, and falls back to the standard `JSON` type on other backends. It's the recommended way to store JSON data.

**Usage:**

```python
from sqlalchemy.orm import Mapped, mapped_column
from advanced_alchemy.types import JsonB

class MyModel(Base):
    # ...
    data: Mapped[dict] = mapped_column(JsonB)
```

### `BigIntIdentity`

This is a `BigInteger` type that automatically falls back to a standard `Integer` on backends that don't support `BigInteger` (like older versions of SQLite). It's useful for primary keys that might exceed the capacity of a standard integer.

**Usage:**

It's often used in conjunction with the `BigIntPrimaryKeyMixin`.

```python
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Identity
from advanced_alchemy.types import BigIntIdentity

class MyModel(Base):
    # ...
    id: Mapped[int] = mapped_column(
        BigIntIdentity,
        Identity(start=1),
        primary_key=True
    )
```

## Security and Encryption

### `EncryptedString` and `EncryptedText`

These types provide transparent, application-level encryption for string and text columns. The data is encrypted before being sent to the database and decrypted when retrieved.

**Configuration:**
You must provide an encryption key. This can be a `bytes` key, a string, or a callable that returns one. It's highly recommended to load this from a secure configuration source.

```python
from sqlalchemy.orm import Mapped, mapped_column
from advanced_alchemy.types import EncryptedString, EncryptedText

# Load your key securely, e.g., from environment variables
ENCRYPTION_KEY = b'your-32-byte-fernet-key-here'

class User(Base):
    # ...
    social_security_number: Mapped[str] = mapped_column(
        EncryptedString(key=ENCRYPTION_KEY)
    )
    medical_notes: Mapped[str] = mapped_column(
        EncryptedText(key=ENCRYPTION_KEY)
    )
```

-   `EncryptedString`: Use for shorter, sensitive strings.
-   `EncryptedText`: Use for larger blocks of sensitive text.

### `PasswordHash`

This type provides transparent password hashing for a string column. When you assign a plain-text password to the model field, it is automatically hashed. When you access the field, you get a `HashedPassword` object that you can use to verify a password.

**Configuration:**
It requires a hashing backend. `advanced-alchemy` provides helpers for `pwdlib`, `passlib`, and `argon2-cffi`.

```python
from advanced_alchemy.types import PasswordHash
from advanced_alchemy.types.password_hash.pwdlib import PwdlibHasher
from pwdlib import PasswordHash as PwdLibPasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# 1. Configure the hasher
argon2_hasher = Argon2Hasher()
password_hasher = PwdLibPasswordHash((argon2_hasher,))
pwdlib_backend = PwdlibHasher(hasher=password_hasher)

# 2. Use it in your model
class User(Base):
    # ...
    hashed_password: Mapped[str] = mapped_column(
        PasswordHash(backend=pwdlib_backend)
    )

# 3. Usage
user = User()
user.hashed_password = "my-secret-password" # Automatically hashed

# `user.hashed_password` is now a HashedPassword object
print(user.hashed_password.verify("my-secret-password")) # -> True
print(user.hashed_password.verify("wrong-password"))   # -> False
```

## File Storage

### `StoredObject`

This type is the core of the [File Storage Backends](./06-storage-backends.md) system. It stores file metadata as JSON in the database while the file content is saved to a configured storage backend (like S3 or the local filesystem).

**Usage:**

```python
from sqlalchemy.orm import Mapped, mapped_column
from advanced_alchemy.types import FileObject, StoredObject

class DocumentModel(Base):
    __tablename__ = "document"
    # ...
    
    # This column will store file metadata as JSON
    # The 's3_media' backend must be configured in the storages registry
    file: Mapped[FileObject] = mapped_column(StoredObject(backend="s3_media"))
```
For a complete guide on using this type, see the [File Storage Backends](./06-storage-backends.md) guide.

## Mutable Collections

### `MutableList`

This is a `TypeDecorator` that provides a list-like collection that automatically tracks changes. When you append, remove, or modify items in a `MutableList`, it notifies SQLAlchemy's session, ensuring that changes to JSON columns are correctly persisted.

**Usage:**
It is often used with the `JsonB` type for storing lists of objects.

```python
from sqlalchemy.orm import Mapped, mapped_column
from advanced_alchemy.types import JsonB, MutableList

class MyModel(Base):
    # ...
    # The `MutableList[dict]` type ensures changes to the list are tracked.
    data: Mapped[list[dict]] = mapped_column(MutableList.as_mutable(JsonB))

# Usage
my_instance = MyModel(data=[{"key": "value"}])
session.add(my_instance)
session.commit()

# Later...
my_instance.data.append({"another": "item"})
session.commit() # This change will be persisted correctly.
```