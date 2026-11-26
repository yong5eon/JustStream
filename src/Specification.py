from collections.abc import Mapping
from copy import deepcopy
from re import fullmatch
from typing import (
	Any,
	Callable,
	Optional,
)

from .Descriptor import (
	Schema,
	schema_to_dict,
)
from .Descriptor.Value import (
	Condition,
	Descriptor,
)

__all__ = (
	'Specification',
)


class Specification:
	def __init__(
		self,
		schema: Any = None,
		validator: Optional[Callable[[Any], Any]] = None,
		example: Any = ...,
		format: str = 'application/json',
	):
		if not isinstance(
			format,
			str,
		) or fullmatch(
			r"[!#$%&'+.^_`|~0-9A-Za-z-]+/[!#$%&'+.^_`|~0-9A-Za-z-]+(?:[ \t]*;[^\r\n]+)?",
			format,
		) is None:
			raise ValueError('Specification format must be a concrete media type')
		if validator is not None and not callable(validator):
			raise TypeError('A Specification validator must be callable')
		if schema is not None and not isinstance(
			schema,
			(
				Schema,
				Descriptor,
				Condition,
				Mapping,
			),
		):
			raise TypeError('A Descriptor schema or schema mapping is required')
		self.schema = schema
		self.validator = validator
		self.example = example
		self.format = format
		self.document()

	def __call__(
		self,
		value: Any,
	) -> Any:
		return self.validator(value) if self.validator is not None else value

	def document(self) -> dict:
		payload = {} if self.schema is None else schema_to_dict(
			self.schema if isinstance(
				self.schema,
				Schema,
			) else Schema(
				'Payload',
				self.schema,
			),
		)
		message = {
			'contentType': self.format,
			'payload': payload,
		}
		if self.example is not ...:
			message['examples'] = [{'payload': deepcopy(self.example)}]
		return message
