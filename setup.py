# -*- coding: utf-8 -*-

from pathlib import Path

from setuptools import (
	Distribution,
	find_namespace_packages,
	setup,
)

PACKAGE = 'JustStream'
SOURCE = 'src'
EXTRAS = {
	'RabbitMQ': ['pika>=1.3.2'],
	'Redis': ['redis>=5.1.1'],
}
PACKAGES = [PACKAGE]
PACKAGE_DIR = {PACKAGE: SOURCE}

for package in find_namespace_packages(SOURCE):
	qualified = '{}.{}'.format(
		PACKAGE,
		package,
	)
	PACKAGES.append(qualified)
	PACKAGE_DIR[qualified] = '{}/{}'.format(
		SOURCE,
		package.replace(
			'.',
			'/',
		),
	)


class VersionedDistribution(Distribution):
	def finalize_options(self) -> None:
		super().finalize_options()
		from setuptools_scm import get_version

		version: str = get_version(
			dist_name=PACKAGE,
			tag_regex=r'^v?(?P<version>[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:(?:rc|\.post)[0-9]+)?)$',
			# changes/<SHA> 릴리스 노트 태그가 버전 태그로 해석되지 않도록 버전 형태의 태그만 조회
			git_describe_command=[
				'git',
				'describe',
				'--dirty',
				'--tags',
				'--long',
				'--match',
				'[0-9]*.[0-9]*',
				'--match',
				'v[0-9]*.[0-9]*',
			],
		)
		self.metadata.version = version
		return


setup(
	name=PACKAGE,
	setup_requires=[
		'setuptools>=77',
		'setuptools-scm>=8,<10',
		'wheel',
	],
	distclass=VersionedDistribution,
	description='Synchronous message processing with pluggable broker adapters',
	long_description=Path('README.setup.md').read_text(encoding='utf-8'),
	long_description_content_type='text/markdown',
	author='Heo Yongseon',
	url='https://github.com/yong5eon/JustStream',
	project_urls={
		'Source': 'https://github.com/yong5eon/JustStream',
		'Issues': 'https://github.com/yong5eon/JustStream/issues',
		'Releases': 'https://github.com/yong5eon/JustStream/releases',
	},
	extras_require=EXTRAS,
	packages=PACKAGES,
	package_dir=PACKAGE_DIR,
	include_package_data=False,
	package_data={
		'JustStream.Inspector.Extensions': [
			'Play.html',
			'Status.html',
		],
	},
	classifiers=[
		'Programming Language :: Python :: 3.9',
		'Programming Language :: Python :: 3.10',
		'Programming Language :: Python :: 3.11',
		'Programming Language :: Python :: 3.12',
		'Programming Language :: Python :: 3.13',
		'Programming Language :: Python :: 3.14',
	],
	python_requires='>=3.9',
)
