from collections.abc import Mapping
from inspect import (
	Parameter,
	signature,
)
from typing import (
	Any,
	get_args,
	get_type_hints,
)
from unittest import (
	TestCase,
	main,
)

from JustStream.Descriptor import (
	AllOf,
	Array,
	Binary,
	BinaryBase64Encoded,
	Boolean,
	Integer,
	IntegerFormat,
	Number,
	NumberFormat,
	Object,
	OneOf,
	Properties,
	Schema,
	String,
	StringFormat,
	Value,
	schema_to_dict,
)
from JustStream.Descriptor.Value import (
	Type,
)
from JustStream import Specification


class DescriptorTests(TestCase):
	def test_none_defaults_have_nullable_annotations(self) -> None:
		targets = (
			Value,
			Boolean,
			Integer,
			Number,
			String,
			Binary,
			BinaryBase64Encoded,
			Object,
			Array,
			Schema,
			OneOf,
		)
		for target in targets:
			function = target.__init__ if isinstance(target, type) else target
			hints = get_type_hints(function)
			for name, parameter in signature(function).parameters.items():
				if parameter.default is None and parameter.annotation is not Parameter.empty:
					with self.subTest(
						target=target,
						parameter=name,
					):
						annotation = hints[name]
						self.assertTrue(
							annotation is Any or type(None) in get_args(annotation),
						)
		return

	def test_public_schema_nodes_and_conditions(self) -> None:
		properties = Properties(
			a=Integer(),
			items=Array(format=Object()),
			wrapped=Schema(
				'Text',
				String(required=False),
			),
			choice=OneOf(
				Integer(),
				String(),
			),
		)
		result = schema_to_dict(Schema(
			'Object',
			Object(properties=properties),
		))
		self.assertEqual(
			result['required'],
			[
				'a',
				'items',
				'choice',
			],
		)
		self.assertEqual(
			result['properties']['items']['items']['type'],
			'object',
		)
		self.assertEqual(
			result['properties']['wrapped'],
			{
				'type': 'string',
				'default': None,
			},
		)
		condition = AllOf(
			Integer(min=0),
			OneOf(
				Integer(max=3),
				Array(format=Schema(
					'Item',
					String(),
				)),
			),
		)
		self.assertEqual(
			schema_to_dict(Schema(
				'Conditions',
				condition,
			))['allOf'][1]['oneOf'][1]['items'],
			{'type': 'string'},
		)
		return

	def test_schema_mappings_keep_specification_compatible(self) -> None:
		mapping = {
			'type': 'object',
			'properties': {'name': {'type': 'string'}},
		}
		self.assertEqual(
			schema_to_dict(Schema(
				'Mapping',
				mapping,
			)),
			mapping,
		)
		self.assertEqual(
			Specification(schema=mapping).document()['payload'],
			mapping,
		)
		self.assertEqual(
			schema_to_dict(Schema(
				'Outer',
				Schema(
					'Inner',
					Integer(),
				),
			)),
			{'type': 'integer'},
		)
		return

	def test_mapping_contract(self) -> None:
		value = Integer(
			description='정수',
			format=IntegerFormat.int32,
			min=0,
			max=9,
			enum=['1'],
		)
		self.assertIsInstance(
			value,
			Mapping,
		)
		value['custom'] = 3
		self.assertEqual(
			value['custom'],
			3,
		)
		self.assertEqual(
			value.get('custom', 4),
			3,
		)
		self.assertEqual(
			value.get('missing', 4),
			4,
		)
		self.assertIsNone(value.get('missing'))
		self.assertEqual(
			list(value),
			list(value.keys()),
		)
		self.assertEqual(
			len(value),
			len(value.items()),
		)
		self.assertEqual(
			list(value.values()),
			list(dict(value).values()),
		)
		self.assertEqual(
			value,
			dict(value),
		)
		self.assertFalse(value != dict(value))
		del value['custom']
		self.assertNotIn(
			'custom',
			value,
		)
		with self.assertRaises(KeyError):
			value['missing']
		return

	def test_defaults_formats_and_explicit_none(self) -> None:
		for node in (
			Boolean(description=None),
			Integer(
				description=None,
				format=None,
			),
			Number(
				description=None,
				format=None,
			),
			String(
				description=None,
				format=None,
			),
			Binary(
				description=None,
				default=None,
			),
			BinaryBase64Encoded(
				description=None,
				default=None,
			),
			Object(
				properties=None,
				default=None,
			),
			Array(
				description=None,
				format=None,
				default=None,
			),
		):
			self.assertNotIn(
				'default',
				schema_to_dict(Schema(
					'Value',
					node,
				)),
			)
		self.assertEqual(
			Number(format=NumberFormat.double)['format'],
			'double',
		)
		self.assertEqual(
			String(
				format=StringFormat.date,
				min=2,
				max=5,
				default='x',
				required=False,
			),
			{
				'type': 'string',
				'format': 'date',
				'minLength': 2,
				'maxLength': 5,
				'default': 'x',
			},
		)
		self.assertEqual(
			Value(Type.Integer)['type'],
			Type.Integer,
		)
		return


if __name__ == '__main__':
	main()
