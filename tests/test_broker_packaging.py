from importlib.metadata import (
	Distribution,
	PackageNotFoundError,
	distributions,
)
from json import dumps
from pathlib import Path
from subprocess import run
from sys import executable
from tempfile import TemporaryDirectory
from unittest import (
	TestCase,
	main,
)

from tests._support import require_value

PROJECT = Path(__file__).resolve().parents[1]


def installed_distribution(
	name: str,
) -> Distribution:
	expected: str = name.lower().replace(
		'_',
		'-',
	)
	for package in distributions():
		actual: str = package.metadata.get(
			'Name',
			'',
		).lower().replace(
			'_',
			'-',
		)
		location: Path = Path(str(package.locate_file(''))).resolve()
		if actual == expected and location != PROJECT:
			return package
	raise PackageNotFoundError(name)


def distribution_files(package: Distribution) -> set[str]:
	return {
		str(path).replace(
			'\\',
			'/',
		)
		for path in require_value(package.files)
	}


class BrokerPackagingTests(TestCase):
	def test_distribution_contains_play_extension_and_template(self) -> None:
		package = installed_distribution('JustStream')
		files: set[str] = distribution_files(package)
		for name in (
			'Play.py',
			'Play.html',
		):
			self.assertIn(
				'JustStream/Inspector/Extensions/' + name,
				files,
			)
		for name in (
			'Console.py',
			'Console.html',
		):
			self.assertNotIn(
				'JustStream/Inspector/Extensions/' + name,
				files,
			)
		return

	def test_brokers_are_part_of_the_distribution(self) -> None:
		package = installed_distribution('JustStream')
		files: set[str] = distribution_files(package)
		for broker in (
			'RabbitMQ',
			'Redis',
		):
			with self.subTest(broker=broker):
				for module in (
					'__init__',
					'Configuration',
					'Connection',
					'Consumer',
					'Event',
					'Queue',
					'Serializer',
					'Subscription',
				):
					self.assertIn(
						f'JustStream/Broker/Implements/{broker}/{module}.py',
						files,
					)
		return

	def test_extras_only_add_client_dependencies(self) -> None:
		package = installed_distribution('JustStream')
		dependencies = require_value(package.requires)
		self.assertEqual(
			len(dependencies),
			2,
		)
		for requirement, extra in (
			('pika>=1.3.2', 'RabbitMQ'),
			('redis>=5.1.1', 'Redis'),
		):
			self.assertTrue(any(
				dependency.startswith(requirement + ';')
				and extra.lower() in dependency.lower()
				for dependency in dependencies
			))
		self.assertFalse(any(
			dependency.startswith('JustStream-')
			for dependency in dependencies
		))
		return

	def test_imports_do_not_require_unselected_clients(self):
		for blocked, modules in (
			(
				['pika', 'redis'],
				['JustStream', 'JustStream.Broker', 'JustStream.Inspector'],
			),
			(
				['redis'],
				['JustStream.Broker.Implements.RabbitMQ'],
			),
			(
				['pika'],
				['JustStream.Broker.Implements.Redis'],
			),
		):
			with self.subTest(blocked=blocked), TemporaryDirectory() as directory:
				code = '\n'.join((
					'from importlib import import_module',
					'from sys import modules',
					f'for name in {dumps(blocked)}:',
					'    modules[name] = None',
					f'for name in {dumps(modules)}:',
					'    import_module(name)',
				))
				result = run(
					[
						executable,
						'-I',
						'-c',
						code,
					],
					cwd=Path(directory),
					capture_output=True,
					text=True,
					timeout=30,
				)
				self.assertEqual(
					result.returncode,
					0,
					result.stderr,
				)
		return


if __name__ == '__main__':
	main()
