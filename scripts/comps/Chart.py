from statistics import median
from typing import (
	Any,
	Dict,
	List,
	Sequence,
	Tuple,
)

FRAMEWORKS: Tuple[str, ...] = (
	'juststream',
	'faststream',
)
LABELS: Dict[str, str] = {
	'juststream': 'JustStream',
	'faststream': 'FastStream',
	'rabbitmq': 'RabbitMQ',
	'redis': 'Redis',
}
COLORS: Dict[str, str] = {
	'juststream': '#2563eb',
	'faststream': '#f97316',
}
METRICS: Tuple[Tuple[str, str, str, str], ...] = (
	# title, phase, key, number format
	('Publish throughput (msg/s)', 'publish', 'throughput', '{:,.0f}'),
	('Consume throughput (msg/s)', 'consume', 'throughput', '{:,.0f}'),
	('Consume CPU usage (%)', 'consume', 'cpu_percent', '{:.0f}'),
	('Consume peak RSS (MB)', 'consume', 'peak_rss_mb', '{:.0f}'),
)
PANEL_WIDTH = 440
PANEL_HEIGHT = 260
PLOT_TOP = 56
PLOT_HEIGHT = 140
BAR_WIDTH = 56
BAR_GAP = 12
FONT = 'font-family="sans-serif"'


def pick(
	runs: List[Dict[str, Any]],
	broker: str,
	framework: str,
	phase: str,
	key: str,
) -> float:
	"""
	Return the median of one metric over the repeated runs.
	"""
	return median(
		item[phase][key]
		for item in runs
		if item['broker'] == broker and item['framework'] == framework
	)


def panel(
	runs: List[Dict[str, Any]],
	brokers: Sequence[str],
	metric: Tuple[str, str, str, str],
	left: int,
	top: int,
) -> str:
	"""
	Render one grouped bar chart panel for a metric.
	"""
	title, phase, key, template = metric
	values: Dict[Tuple[str, str], float] = {
		(broker, framework): pick(runs, broker, framework, phase, key)
		for broker in brokers
		for framework in FRAMEWORKS
	}
	peak = max(values.values()) or 1.0
	group_width = PANEL_WIDTH // len(brokers)
	baseline = top + PLOT_TOP + PLOT_HEIGHT
	parts: List[str] = [
		'<text x="{}" y="{}" font-size="15" font-weight="bold" {}>{}</text>'.format(
			left + 10,
			top + 24,
			FONT,
			title,
		),
		'<line x1="{0}" y1="{1}" x2="{2}" y2="{1}" stroke="#9ca3af"/>'.format(
			left + 10,
			baseline,
			left + PANEL_WIDTH - 10,
		),
	]
	for index, broker in enumerate(brokers):
		center = left + group_width * index + group_width // 2
		for position, framework in enumerate(FRAMEWORKS):
			value = values[(broker, framework)]
			height = value / peak * PLOT_HEIGHT
			x = center - BAR_WIDTH - BAR_GAP // 2 + position * (BAR_WIDTH + BAR_GAP)
			parts.append('<rect x="{}" y="{:.1f}" width="{}" height="{:.1f}" fill="{}"/>'.format(
				x,
				baseline - height,
				BAR_WIDTH,
				height,
				COLORS[framework],
			))
			parts.append('<text x="{}" y="{:.1f}" font-size="12" text-anchor="middle" {}>{}</text>'.format(
				x + BAR_WIDTH // 2,
				baseline - height - 5,
				FONT,
				template.format(value),
			))
		parts.append('<text x="{}" y="{}" font-size="13" text-anchor="middle" {}>{}</text>'.format(
			center,
			baseline + 20,
			FONT,
			LABELS[broker],
		))
	return '\n'.join(parts)


def render(
	runs: List[Dict[str, Any]],
	brokers: Sequence[str],
	count: int,
) -> str:
	"""
	Render the comparison of all metrics as a standalone SVG document.
	"""
	width = PANEL_WIDTH * 2
	height = PANEL_HEIGHT * 2 + 40
	parts: List[str] = [
		'<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{1}" viewBox="0 0 {0} {1}">'.format(
			width,
			height,
		),
		'<rect width="100%" height="100%" fill="#ffffff"/>',
	]
	for index, metric in enumerate(METRICS):
		parts.append(panel(
			runs,
			brokers,
			metric,
			(index % 2) * PANEL_WIDTH,
			(index // 2) * PANEL_HEIGHT,
		))
	for position, framework in enumerate(FRAMEWORKS):
		x = 10 + position * 130
		parts.append('<rect x="{}" y="{}" width="14" height="14" fill="{}"/>'.format(
			x,
			height - 30,
			COLORS[framework],
		))
		parts.append('<text x="{}" y="{}" font-size="13" {}>{}</text>'.format(
			x + 20,
			height - 18,
			FONT,
			LABELS[framework],
		))
	parts.append('<text x="{}" y="{}" font-size="12" fill="#6b7280" text-anchor="end" {}>Median of repeated runs, {:,} messages</text>'.format(
		width - 10,
		height - 18,
		FONT,
		count,
	))
	parts.append('</svg>')
	return '\n'.join(parts) + '\n'
