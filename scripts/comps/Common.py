from dataclasses import (
	asdict,
	dataclass,
)
from json import (
	dumps,
	loads,
)
from pathlib import Path
from resource import (
	RUSAGE_SELF,
	getrusage,
)
from sys import platform
from time import monotonic
from typing import (
	Any,
	Dict,
	Optional,
)

__all__ = (
	'Config',
	'Measurement',
	'Meter',
	'make_body',
	'read_measurement',
	'write_measurement',
)

KILOBYTES_PER_MEGABYTE = 1024
BYTES_PER_MEGABYTE = 1024 * 1024


@dataclass(frozen=True)
class Config:
	"""
	Conditions shared by every framework and broker.
	"""

	broker: str
	count: int
	size: int
	concurrency: int
	queue: str
	port: int
	host: str = '127.0.0.1'


@dataclass(frozen=True)
class Measurement:
	"""
	Result of one phase of one run, measured inside the process under test.
	"""

	count: int
	elapsed: float
	cpu: float
	baseline_rss_mb: float
	peak_rss_mb: float

	@property
	def throughput(self) -> float:
		return self.count / self.elapsed

	@property
	def cpu_percent(self) -> float:
		return self.cpu / self.elapsed * 100

	def to_dict(self) -> Dict[str, Any]:
		result: Dict[str, Any] = asdict(self)
		result['throughput'] = self.throughput
		result['cpu_percent'] = self.cpu_percent
		return result


def peak_rss_mb() -> float:
	"""
	Return the peak resident set size of this process in megabytes.
	"""
	peak: int = getrusage(RUSAGE_SELF).ru_maxrss
	# ru_maxrss is reported in bytes on macOS and in kilobytes on Linux.
	if platform == 'darwin':
		return peak / BYTES_PER_MEGABYTE
	return peak / KILOBYTES_PER_MEGABYTE


def cpu_seconds() -> float:
	"""
	Return the user and system CPU time consumed by all threads of this process.
	"""
	usage = getrusage(RUSAGE_SELF)
	return usage.ru_utime + usage.ru_stime


class Meter:
	"""
	Measures wall time, CPU time and memory between start and stop.
	"""

	def __init__(self) -> None:
		self.started: Optional[float] = None
		self.cpu: float = 0
		self.baseline: float = 0
		return

	def start(self) -> None:
		self.baseline = peak_rss_mb()
		self.cpu = cpu_seconds()
		self.started = monotonic()
		return

	def stop(self, count: int) -> Measurement:
		stopped: float = monotonic()
		cpu: float = cpu_seconds()
		if self.started is None:
			raise RuntimeError('Meter was not started')
		return Measurement(
			count=count,
			elapsed=stopped - self.started,
			cpu=cpu - self.cpu,
			baseline_rss_mb=self.baseline,
			peak_rss_mb=peak_rss_mb(),
		)


def make_body(
	index: int,
	size: int,
) -> Dict[str, Any]:
	"""
	Build a message body whose JSON payload is about ``size`` bytes of padding.
	"""
	return {
		'index': index,
		'data': 'x' * size,
	}


def write_measurement(
	path: Path,
	measurement: Measurement,
) -> None:
	path.write_text(
		dumps(measurement.to_dict()),
		encoding='utf-8',
	)
	return


def read_measurement(path: Path) -> Dict[str, Any]:
	result: Dict[str, Any] = loads(path.read_text(encoding='utf-8'))
	return result
