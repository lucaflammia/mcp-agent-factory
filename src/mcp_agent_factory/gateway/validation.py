"""ValidationGate — validates tool arguments against a Pydantic model."""
from __future__ import annotations

from typing import Any, Type

from pydantic import BaseModel


class ValidationGate:
    """Validates a dict of arguments against a Pydantic model class.

    Raises ``pydantic.ValidationError`` on failure so callers can catch it
    and return a structured error response.
    """

    def validate(self, model_cls: Type[BaseModel], data: dict[str, Any]) -> BaseModel:
        """Instantiate *model_cls* with *data* and return the validated instance.

        Raises:
            pydantic.ValidationError: if *data* does not conform to *model_cls*.
        """
        return model_cls(**data)
