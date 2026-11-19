from asyncio import (
	Event,
	run,
	wait_for,
)
from typing import (
	Any,
	Dict,
	Optional,
)

from Common import (
	Config,
	Measurement,
	Meter,
	make_body,
)

from faststream.rabbit import (
	Channel,
	RabbitBroker,
	RabbitQueue,
)
from faststream.redis import (
	RedisBroker,
	StreamSub,
)

__all__ = (
	'consume',
	'publish',
)

GROUP = 'stream'
CONSUMER = 'benchmark'
TIMEOUT = 3600


class Progress:
	"""
	Counts handled messages and signals once all of them were handled.
	"""

	def __init__(self) -> None:
		self.count = 0
		self.expected = 0
		self.done = Event()
		self.meter = Meter()
		self.measurement: Optional[Measurement] = None
		return

	async def handle(
		self,
		body: Dict[str, Any],
	) -> None:
		self.count += 1
		if self.count == self.expected:
			self.measurement = self.meter.stop(self.count)
			self.done.set()
		return


PROGRESS = Progress()


def create_broker(config: Config) -> Any:
	if config.broker == 'rabbitmq':
		return RabbitBroker(
			'amqp://guest:guest@{}:{}/'.format(
				config.host,
				config.port,
			),
			logger=None,
		)
	return RedisBroker(
		'redis://{}:{}'.format(
			config.host,
			config.port,
		),
		logger=None,
	)


async def publish_messages(config: Config) -> Measurement:
	broker = create_broker(config)
	meter = Meter()
	await broker.connect()
	try:
		if config.broker == 'rabbitmq':
			queue = RabbitQueue(
				config.queue,
				durable=True,
			)
			await broker.declare_queue(queue)
			meter.start()
			for index in range(config.count):
				await broker.publish(
					make_body(
						index,
						config.size,
					),
					queue=queue,
					persist=True,
				)
		else:
			meter.start()
			for index in range(config.count):
				await broker.publish(
					make_body(
						index,
						config.size,
					),
					stream=config.queue,
				)
		return meter.stop(config.count)
	finally:
		await broker.stop()


async def consume_messages(config: Config) -> Measurement:
	PROGRESS.expected = config.count
	broker = create_broker(config)
	if config.broker == 'rabbitmq':
		broker.subscriber(
			RabbitQueue(
				config.queue,
				durable=True,
			),
			channel=Channel(prefetch_count=config.concurrency),
		)(PROGRESS.handle)
	else:
		broker.subscriber(
			stream=StreamSub(
				config.queue,
				group=GROUP,
				consumer=CONSUMER,
				last_id='0',
				max_records=config.concurrency,
			),
			max_workers=config.concurrency,
		)(PROGRESS.handle)
	await broker.connect()
	try:
		PROGRESS.meter.start()
		await broker.start()
		await wait_for(
			PROGRESS.done.wait(),
			TIMEOUT,
		)
	finally:
		await broker.stop()
	if PROGRESS.measurement is None:
		raise RuntimeError('Broker stopped before every message was handled')
	return PROGRESS.measurement


def publish(config: Config) -> Measurement:
	return run(publish_messages(config))


def consume(config: Config) -> Measurement:
	return run(consume_messages(config))
