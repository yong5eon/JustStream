from argparse import ArgumentParser
from importlib import import_module
from pathlib import Path
from typing import (
	Callable,
	Sequence,
)

from Common import (
	Config,
	Measurement,
	write_measurement,
)

BROKERS = (
	'rabbitmq',
	'redis',
)
TARGETS = {
	'juststream': 'JustStreamTarget',
	'faststream': 'FastStreamTarget',
}


def create_parser() -> ArgumentParser:
	parser = ArgumentParser(description='Run one phase of one benchmark in this process.')
	parser.add_argument(
		'--framework',
		choices=sorted(TARGETS),
		required=True,
	)
	parser.add_argument(
		'--broker',
		choices=BROKERS,
		required=True,
	)
	parser.add_argument(
		'--phase',
		choices=('publish', 'consume'),
		required=True,
	)
	parser.add_argument(
		'--count',
		type=int,
		required=True,
	)
	parser.add_argument(
		'--size',
		type=int,
		required=True,
	)
	parser.add_argument(
		'--concurrency',
		type=int,
		required=True,
	)
	parser.add_argument(
		'--queue',
		required=True,
	)
	parser.add_argument(
		'--port',
		type=int,
		required=True,
	)
	parser.add_argument(
		'--result',
		type=Path,
		required=True,
	)
	return parser


def main(arguments: Sequence[str]) -> None:
	args = create_parser().parse_args(arguments)
	config = Config(
		broker=args.broker,
		count=args.count,
		size=args.size,
		concurrency=args.concurrency,
		queue=args.queue,
		port=args.port,
	)
	target = import_module(TARGETS[args.framework])
	phase: Callable[[Config], Measurement] = getattr(
		target,
		args.phase,
	)
	write_measurement(
		args.result,
		phase(config),
	)
	return


if __name__ == '__main__':
	from sys import argv

	main(argv[1:])
