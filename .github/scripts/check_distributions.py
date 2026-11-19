from argparse import ArgumentParser
from email.parser import BytesParser
from os import environ
from pathlib import Path
from shutil import copy2
from subprocess import run
from sys import executable
from tempfile import TemporaryDirectory
from venv import EnvBuilder
from zipfile import ZipFile

PROJECT = 'JustStream'
ROOT = Path(__file__).resolve().parents[2]
EXTRAS = (
	'RabbitMQ',
	'Redis',
)
MODULES = (
	'Broker.Implements.RabbitMQ',
	'Broker.Implements.Redis',
)


def check(
	command: list[str],
	directory: Path,
	environment: dict[str, str],
) -> None:
	result = run(
		command,
		cwd=directory,
		env=environment,
		capture_output=True,
		text=True,
	)
	if result.returncode:
		raise RuntimeError(
			'Command failed: {}\n{}\n{}'.format(
				command,
				result.stdout,
				result.stderr,
			)
		)
	return


def python_in(directory: Path) -> str:
	EnvBuilder(with_pip=True).create(directory)
	python = str(directory / ('Scripts/python.exe' if environ.get('OS') == 'Windows_NT' else 'bin/python'))
	check(
		[
			executable,
			'-m',
			'pip',
			'--python',
			python,
			'install',
			'--upgrade',
			'pip>=23',
		],
		directory,
		dict(environ),
	)
	return python


def verify_install(
	python: str,
	directory: Path,
	environment: dict[str, str],
	clients: bool,
) -> None:
	code = (
		'from importlib import import_module\n'
		'from importlib.util import find_spec\n'
		f'import_module({PROJECT!r})\n'
		f'for path in {MODULES!r}:\n'
		f'    module = {PROJECT!r} + "." + path\n'
		'    assert find_spec(module) is not None, module\n'
		f'    if {clients!r}:\n'
		'        import_module(module)\n'
		f'for client in {("pika", "redis")!r}:\n'
		f'    assert (find_spec(client) is not None) == {clients!r}, client\n'
	)
	check(
		[
			python,
			'-I',
			'-c',
			code,
		],
		directory,
		environment,
	)
	check(
		[
			python,
			'-m',
			'pip',
			'check',
		],
		directory,
		environment,
	)
	return


def read_wheel(wheel: Path) -> tuple[dict[str, str], dict[str, bytes]]:
	with ZipFile(wheel) as archive:
		metadata_path, = (
			name for name in archive.namelist()
			if name.endswith('.dist-info/METADATA')
		)
		metadata = BytesParser().parsebytes(archive.read(metadata_path))
		payload = {
			path: archive.read(path)
			for path in archive.namelist()
			if path.startswith(PROJECT + '/')
		}
	return {
		'Name': metadata['Name'],
		'Version': metadata['Version'],
		'Extras': ','.join(sorted(metadata.get_all('Provides-Extra', []))),
		'Requires': '\n'.join(metadata.get_all('Requires-Dist', [])),
	}, payload


def main() -> None:
	parser = ArgumentParser(description='Verify the distribution contents, rebuilds and installation.')
	parser.add_argument(
		'--dist-dir',
		default='dist',
	)
	parser.add_argument(
		'--editable',
		action='store_true',
	)
	options = parser.parse_args()
	dist = Path(options.dist_dir).resolve()
	environment: dict[str, str] = dict(environ)
	environment.pop(
		'SETUPTOOLS_SCM_PRETEND_VERSION',
		None,
	)
	wheel, = dist.glob('*.whl')
	metadata, payload = read_wheel(wheel)
	assert metadata['Name'] == PROJECT, metadata['Name']
	assert metadata['Extras'].lower() == ','.join(sorted(extra.lower() for extra in EXTRAS)), metadata['Extras']
	assert f'{PROJECT}-' not in metadata['Requires'], metadata['Requires']
	for path in MODULES:
		prefix = PROJECT + '/' + path.replace(
			'.',
			'/',
		) + '/'
		assert any(item.startswith(prefix) for item in payload), path
	version = metadata['Version']

	with TemporaryDirectory() as temporary:
		directory = Path(temporary)
		sources = sorted(dist.glob('*.tar.gz'))
		assert len(sources) in (
			0,
			1,
		)
		for source in sources:
			rebuilt = directory / 'rebuilt'
			check(
				[
					executable,
					'-m',
					'pip',
					'wheel',
					str(source),
					'--no-deps',
					'--no-build-isolation',
					'--no-cache-dir',
					'--wheel-dir',
					str(rebuilt),
				],
				directory,
				environment,
			)
			rebuilt_metadata, rebuilt_payload = read_wheel(next(rebuilt.glob('*.whl')))
			assert rebuilt_metadata == metadata
			assert rebuilt_payload == payload
		python = python_in(directory / 'plain')
		check(
			[
				python,
				'-m',
				'pip',
				'install',
				str(wheel),
			],
			directory,
			environment,
		)
		verify_install(
			python,
			directory,
			environment,
			False,
		)
		python = python_in(directory / 'extras')
		check(
			[
				python,
				'-m',
				'pip',
				'install',
				f'{PROJECT}[{",".join(EXTRAS)}] @ {wheel.as_uri()}',
			],
			directory,
			environment,
		)
		verify_install(
			python,
			directory,
			environment,
			True,
		)
		if options.editable:
			source = directory / 'source'
			source.mkdir()
			for filename in (
				'setup.py',
				'README.setup.md',
				'LICENSE',
			):
				copy2(
					ROOT / filename,
					source / filename,
				)
			(source / 'src').mkdir()
			for item in (ROOT / 'src').rglob('*'):
				if '__pycache__' in item.parts:
					continue
				destination = source / item.relative_to(ROOT)
				if item.is_dir():
					destination.mkdir(
						parents=True,
						exist_ok=True,
					)
				else:
					destination.parent.mkdir(
						parents=True,
						exist_ok=True,
					)
					copy2(
						item,
						destination,
					)
			probe = source / 'src' / '_editable_probe.py'
			probe.write_text(
				'VALUE = 1\n',
				encoding='utf-8',
			)
			python = python_in(directory / 'editable')
			environment['SETUPTOOLS_SCM_PRETEND_VERSION'] = version
			check(
				[
					python,
					'-m',
					'pip',
					'install',
					'-e',
					f'{source}[{",".join(EXTRAS)}]',
				],
				directory,
				environment,
			)
			verify_install(
				python,
				directory,
				environment,
				True,
			)
			probe.write_text(
				'VALUE = 200\n',
				encoding='utf-8',
			)
			check(
				[
					python,
					'-I',
					'-c',
					f'from {PROJECT}._editable_probe import VALUE; assert VALUE == 200',
				],
				directory,
				environment,
			)
	print(f'{PROJECT}: contents, sdist rebuild and installation checks passed')
	return


if __name__ == '__main__':
	main()
