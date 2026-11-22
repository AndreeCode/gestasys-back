from dataclasses import asdict, fields
from typing import Any, TypeVar

T = TypeVar("T")


def from_row(cls: type[T], row: Any, **extra: Any) -> T:
    keys = set(row.keys())
    values = {f.name: row[f.name] for f in fields(cls) if f.name in keys}
    values.update(extra)
    return cls(**values)


def to_dict(obj: Any, hidden: tuple[str, ...] = ()) -> dict[str, Any]:
    data = asdict(obj)
    for key in hidden:
        data.pop(key, None)
    return data
