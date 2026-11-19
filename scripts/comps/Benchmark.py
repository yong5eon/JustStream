from argparse import ArgumentParser
from datetime import datetime
from importlib.metadata import version
from json import dumps
from os import cpu_count
from pathlib import Path
from platform import (
	platform,
	python_version,
)
from statistics import median
from subprocess import (
	DEVNULL,
	run,
)
from sys import (
	executable,
	stderr,
)
from tempfile import TemporaryDirectory
from time import (
	monotonic,
	sleep,
)
from typing import (
	Any,
	Dict,
	List,
	Optional,
	Sequence,
)

from Chart import (
	pick,
	render,
)
from Common import read_measurement

HERE = Path(__file__).resolve().parent
FRAMEWORKS = (
	'juststream',
	'faststream',
)
BROKERS = {
	'rabbitmq': {
		'image': 'rabbitmq:4.4',
		'container': 'juststream-bench-rabbitmq',
		'internal': 5672,
		'external': 35672,
		'ready': 'Server startup complete',
	},
	'redis': {
		'image': 'redis:7.4',
		'container': 'juststream-bench-redis',
		'internal': 6379,
		'external': 36379,
		'ready': 'Ready to accept connections',
	},
}
READY_TIMEOUT = 120
PHASE_TIMEOUT = 3600


def create_parser() -> ArgumentParser:
	parser = ArgumentParser(description='Compare JustStream and FastStream on RabbitMQ and Redis.')
	parser.add_argument(
		'--broker',
		choices=(
			'all',
			*BROKERS,
		),
		default='all',
		help='Broker to benchmark (default: all).',
	)
	parser.add_argument(
		'--count',
		type=int,
		default=100000,
		help='Messages published and then consumed per run (default: 100000).',
	)
	parser.add_argument(
		'--size',
		type=int,
		default=256,
		help='Padding bytes in each message body (default: 256).',
	)
	parser.add_argument(
		'--concurrency',
		type=int,
		default=10,
		help='Worker count and prefetch count (default: 10).',
	)
	parser.add_argument(
		'--repeat',
		type=int,
		default=3,
		help='Runs per framework and broker; medians are reported (default: 3).',
	)
	parser.add_argument(
		'--output',
		type=Path,
		help='Write every run and the environment to this JSON file.',
	)
	parser.add_argument(
		'--chart',
		type=Path,
		help='Write a comparison bar chart to this SVG file.',
	)
	return parser


def docker(
	*arguments: str,
	check: bool = True,
) -> int:
	result = run(
		('docker', *arguments),
		stdout=DEVNULL,
		stderr=DEVNULL,
		check=check,
	)
	return result.returncode


def ready(
	container: str,
	marker: str,
) -> bool:
	logs = run(
		(
			'docker',
			'logs',
			container,
		),
		capture_output=True,
		text=True,
		check=True,
	)
	return marker in logs.stdout + logs.stderr


def start_broker(name: str) -> None:
	spec: Dict[str, Any] = BROKERS[name]
	docker(
		'rm',
		'-f',
		spec['container'],
		check=False,
	)
	docker(
		'run',
		'-d',
		'--name',
		spec['container'],
		'-p',
		'127.0.0.1:{}:{}'.format(
			spec['external'],
			spec['internal'],
		),
		spec['image'],
	)
	deadline: float = monotonic() + READY_TIMEOUT
	while not ready(
		spec['container'],
		spec['ready'],
	):
		if monotonic() > deadline:
			raise TimeoutError('{} did not become ready'.format(name))
		sleep(1)
	return


def stop_broker(name: str) -> None:
	docker(
		'rm',
		'-f',
		BROKERS[name]['container'],
		check=False,
	)
	return


def run_phase(
	framework: str,
	broker: str,
	phase: str,
	queue: str,
	args: Any,
	directory: Path,
) -> Dict[str, Any]:
	result: Path = directory / '{}.json'.format(queue + phase)
	run(
		(
			executable,
			str(HERE / 'Runner.py'),
			'--framework',
			framework,
			'--broker',
			broker,
			'--phase',
			phase,
			'--count',
			str(args.count),
			'--size',
			str(args.size),
			'--concurrency',
			str(args.concurrency),
			'--queue',
			queue,
			'--port',
			str(BROKERS[broker]['external']),
			'--result',
			str(result),
		),
		stdout=DEVNULL,
		check=True,
		timeout=PHASE_TIMEOUT,
	)
	return read_measurement(result)


def run_broker(
	broker: str,
	args: Any,
	directory: Path,
) -> List[Dict[str, Any]]:
	runs: List[Dict[str, Any]] = []
	start_broker(broker)
	try:
		for repeat in range(args.repeat):
			for framework in FRAMEWORKS:
				queue = 'bench.{}.{}'.format(
					framework,
					repeat,
				)
				print(
					'{} {} run {}/{}'.format(
						broker,
						framework,
						repeat + 1,
						args.repeat,
					),
					file=stderr,
					flush=True,
				)
				runs.append({
					'broker': broker,
					'framework': framework,
					'repeat': repeat,
					'publish': run_phase(framework, broker, 'publish', queue, args, directory),
					'consume': run_phase(framework, broker, 'consume', queue, args, directory),
				})
	finally:
		stop_broker(broker)
	return runs


def environment(args: Any) -> Dict[str, Any]:
	cpu: Optional[str] = None
	cpuinfo = Path('/proc/cpuinfo')
	if cpuinfo.exists():
		for line in cpuinfo.read_text(encoding='utf-8').splitlines():
			if line.startswith('model name'):
				cpu = line.split(':', 1)[1].strip()
				break
	return {
		'date': datetime.now().astimezone().isoformat(timespec='seconds'),
		'platform': platform(),
		'cpu': cpu,
		'cores': cpu_count(),
		'python': python_version(),
		'versions': {
			name: version(name)
			for name in (
				'JustStream',
				'faststream',
				'pika',
				'redis',
				'aio-pika',
			)
		},
		'images': {name: spec['image'] for name, spec in BROKERS.items()},
		'conditions': {
			'count': args.count,
			'size': args.size,
			'concurrency': args.concurrency,
			'repeat': args.repeat,
		},
	}


def report(
	runs: List[Dict[str, Any]],
	brokers: Sequence[str],
) -> str:
	lines: List[str] = [
		'| Broker | Framework | Publish (msg/s) | Consume (msg/s) | Publish CPU (%) | Consume CPU (%) | Publish peak RSS (MB) | Consume peak RSS (MB) |',
		'| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |',
	]
	for broker in brokers:
		for framework in FRAMEWORKS:
			lines.append('| {} | {} | {:,.0f} | {:,.0f} | {:.0f} | {:.0f} | {:.0f} | {:.0f} |'.format(
				broker,
				framework,
				pick(runs, broker, framework, 'publish', 'throughput'),
				pick(runs, broker, framework, 'consume', 'throughput'),
				pick(runs, broker, framework, 'publish', 'cpu_percent'),
				pick(runs, broker, framework, 'consume', 'cpu_percent'),
				pick(runs, broker, framework, 'publish', 'peak_rss_mb'),
				pick(runs, broker, framework, 'consume', 'peak_rss_mb'),
			))
	return '\n'.join(lines)


def main() -> None:
	args = create_parser().parse_args()
	brokers: List[str] = list(BROKERS) if args.broker == 'all' else [args.broker]
	runs: List[Dict[str, Any]] = []
	with TemporaryDirectory() as directory:
		for broker in brokers:
			runs.extend(run_broker(
				broker,
				args,
				Path(directory),
			))
	if args.output is not None:
		args.output.write_text(
			dumps(
				{
					'environment': environment(args),
					'runs': runs,
				},
				indent=2,
			),
			encoding='utf-8',
		)
	if args.chart is not None:
		args.chart.write_text(
			render(
				runs,
				brokers,
				args.count,
			),
			encoding='utf-8',
		)
	print(report(
		runs,
		brokers,
	))
	return


if __name__ == '__main__':
	main()
