from threading import Lock
from typing import (
	Any,
	Optional,
	Type,
)

from Common import (
	Config,
	Measurement,
	Meter,
	make_body,
)

from JustStream.Broker.Implements.RabbitMQ import (
	Configuration as RabbitMQConfiguration,
	Connection as RabbitMQConnection,
	Subscription as RabbitMQSubscription,
)
from JustStream.Broker.Implements.Redis import (
	Configuration as RedisConfiguration,
	Connection as RedisConnection,
	Subscription as RedisSubscription,
)
from JustStream import (
	ThreadPool,
	Run,
	Worker,
	WorkerSetup,
	declare,
	emit,
)

__all__ = (
	'consume',
	'publish',
)


class SizedRedisConnection(RedisConnection):
	"""
	Redis connection whose consumer prefetches ``qos`` messages, since Worker uses the default.
	"""

	def __init__(
		self,
		conf: RedisConfiguration,
		qos: int,
	) -> None:
		super().__init__(conf)
		self.qos = qos
		return

	def consumer(
		self,
		handler: Any = None,
		qos: int = 1,
		reclaim_idle: Optional[int] = 60000,
	) -> Any:
		return super().consumer(
			handler,
			self.qos,
			reclaim_idle,
		)


class Progress:
	"""
	Counts handled messages and stops the worker once all of them were handled.
	"""

	def __init__(self) -> None:
		self.lock = Lock()
		self.count = 0
		self.expected = 0
		self.worker: Optional[Worker] = None
		self.meter = Meter()
		self.measurement: Optional[Measurement] = None
		return

	def handled(self) -> None:
		with self.lock:
			self.count += 1
			if self.count != self.expected:
				return
			self.measurement = self.meter.stop(self.count)
		if self.worker is None:
			raise RuntimeError('Worker was not registered')
		self.worker.stop()
		return


PROGRESS = Progress()


class StartMeter(WorkerSetup):
	"""
	Starts measuring once the broker is connected and just before consumption begins.
	"""

	def __call__(
		self,
		worker: Worker,
	) -> None:
		PROGRESS.worker = worker
		PROGRESS.meter.start()
		return


def create_connection(config: Config) -> Any:
	if config.broker == 'rabbitmq':
		return RabbitMQConnection(RabbitMQConfiguration(
			host=config.host,
			port=config.port,
			username='guest',
			password='guest',
		))
	return SizedRedisConnection(
		RedisConfiguration(
			host=config.host,
			port=config.port,
		),
		config.concurrency,
	)


def create_task(config: Config) -> Type[Run]:
	if config.broker == 'rabbitmq':
		parameters = RabbitMQSubscription(
			queue=config.queue,
			qos=config.concurrency,
		)
	else:
		parameters = RedisSubscription(config.queue)

	class Noop(
		Run,
		parameters=parameters,
		name='noop',
		description='Handler that does nothing',
	):
		def run(
			self,
			index: int,
			data: str,
		) -> None:
			PROGRESS.handled()
			return

	return Noop


def publish(config: Config) -> Measurement:
	task: Type[Run] = create_task(config)
	broker = create_connection(config)
	meter = Meter()
	broker.connect()
	try:
		declare(
			task=task,
			broker=broker,
		)
		meter.start()
		for index in range(config.count):
			emit(
				make_body(
					index,
					config.size,
				),
				task=task,
				broker=broker,
			)
		return meter.stop(config.count)
	finally:
		broker.close()


def consume(config: Config) -> Measurement:
	task: Type[Run] = create_task(config)
	PROGRESS.expected = config.count
	worker = Worker(
		create_connection(config),
		ThreadPool(config.concurrency),
		setups=StartMeter(),
	)
	worker.add(task)
	worker.run()
	if PROGRESS.measurement is None:
		raise RuntimeError('Worker stopped before every message was handled')
	return PROGRESS.measurement
