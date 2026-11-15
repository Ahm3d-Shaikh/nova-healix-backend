"""Base model: camelCase on the wire, snake_case in Python, optional fields omitted when unset."""

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, model_serializer
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    # Fields declared `x?: T` in the frontend types. They are left out when None;
    # fields declared `T | null` are always sent (as null).
    omit_when_none: ClassVar[frozenset[str]] = frozenset()

    @model_serializer(mode="wrap")
    def _drop_unset_optionals(self, handler: Any) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for name in self.omit_when_none:
            field = self.__class__.model_fields[name]
            key = field.serialization_alias or field.alias or name
            if key in data and data[key] is None:
                del data[key]
        return data
