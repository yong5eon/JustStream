from json import dumps
from os import environ
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from typing import Any, Optional
from unittest import TestCase
from unittest.mock import (
	MagicMock,
	patch,
)

from plan_release import (
	classify_issue,
	higher,
	main,
)


def issue(
	number: int,
	issue_type: Optional[str],
	*labels: str,
) -> dict[str, Any]:
	return {
		'number': number,
		'issueType': None if issue_type is None else {'name': issue_type},
		'labels': {'nodes': [{'name': label} for label in labels]},
	}


class ClassifyIssueTests(TestCase):
	def test_type_and_labels_are_combined(self) -> None:
		cases: list[tuple[dict[str, Any], str]] = [
			(issue(1, 'Feature'), 'minor'),
			(issue(2, 'Bug'), 'patch'),
			(issue(3, 'Fix'), 'patch'),
			(issue(4, 'Task', 'feature'), 'minor'),
			(issue(5, 'Task', 'bug'), 'patch'),
			(issue(6, 'Bug', 'feature'), 'minor'),
			(issue(7, 'Feature', 'fix'), 'minor'),
			(issue(8, 'Task', 'task'), 'keep'),
			(issue(9, 'Epic'), 'keep'),
		]
		for item, expected in cases:
			with self.subTest(number=item['number']):
				self.assertEqual(classify_issue(item), expected)
		return

	def test_labels_classify_without_type(self) -> None:
		cases: list[tuple[dict[str, Any], str]] = [
			(issue(1, None, 'feature'), 'minor'),
			(issue(2, None, 'bug'), 'patch'),
			(issue(3, None, 'fix'), 'patch'),
			(issue(4, None, 'task'), 'keep'),
			(issue(5, None), 'keep'),
			(issue(6, None, 'fix', 'feature'), 'minor'),
		]
		for item, expected in cases:
			with self.subTest(number=item['number']):
				self.assertEqual(classify_issue(item), expected)
		return

	def test_highest_bump_wins(self) -> None:
		self.assertEqual(higher(['keep', 'patch', 'minor']), 'minor')
		self.assertEqual(higher(['keep', 'patch']), 'patch')
		self.assertEqual(higher([]), 'keep')
		return


class PlanReleaseTests(TestCase):
	def setUp(self) -> None:
		self.directory: TemporaryDirectory = TemporaryDirectory()
		self.addCleanup(self.directory.cleanup)
		self.output: Path = Path(self.directory.name) / 'output'
		self.check_output: MagicMock = MagicMock()
		return

	def pull(
		self,
		sha: str = 'pr-head',
		repository: Optional[str] = 'fork/project',
	) -> dict[str, Any]:
		return {
			'number': 12,
			'merged_at': '2026-01-01T00:00:00Z',
			'merge_commit_sha': 'push-head',
			'base': {'ref': 'master', 'repo': {'full_name': 'example/project'}},
			'head': {'sha': sha, 'repo': None if repository is None else {'full_name': repository}},
		}

	def pulls(
		self,
		*pulls: dict[str, Any],
	) -> str:
		return '\n'.join(dumps(pull) for pull in pulls)

	def graphql(
		self,
		*issues: dict[str, Any],
	) -> bytes:
		nodes: dict[str, Any] = {'closingIssuesReferences': {'nodes': list(issues)}}
		return dumps({'data': {'repository': {'pullRequest': nodes}}}).encode()

	def plan(
		self,
		tags: str,
		*responses: Any,
	) -> dict[str, str]:
		self.check_output.side_effect = [tags, *responses]
		env: dict[str, str] = {
			'BEFORE': 'before',
			'GITHUB_REPOSITORY': 'example/project',
			'GITHUB_SHA': 'push-head',
			'GITHUB_RUN_NUMBER': '7',
			'GITHUB_OUTPUT': str(self.output),
		}
		with patch.dict(environ, env), patch('plan_release.check_output', self.check_output):
			main()
		return dict(line.split('=', 1) for line in self.output.read_text(encoding='utf-8').splitlines())

	def test_feature_issue_raises_minor_and_resets_patch(self) -> None:
		result: dict[str, str] = self.plan(
			'0.1.4.12\n0.1.29\nchanges/abc\n',
			self.pulls(self.pull()),
			self.graphql(issue(1, 'Feature')),
		)
		self.assertEqual(result['version'], '0.2.0')
		self.assertEqual(result['tag'], '0.2.0')
		self.assertEqual(result['new_version'], 'true')
		self.assertEqual(result['head_sha'], 'pr-head')
		self.assertEqual(result['head_repository'], 'fork/project')
		self.assertEqual(result['build'], '7')
		self.assertEqual(result['release'], 'true')
		return

	def test_patch_follows_new_minor_series(self) -> None:
		result: dict[str, str] = self.plan(
			'0.1.29\n0.2.0\n',
			self.pulls(self.pull()),
			self.graphql(issue(1, 'Bug')),
		)
		self.assertEqual(result['version'], '0.2.1')
		return

	def test_multiple_issues_use_highest_bump(self) -> None:
		result: dict[str, str] = self.plan(
			'v0.1.29\n',
			self.pulls(self.pull()),
			self.graphql(issue(1, 'Task'), issue(2, None, 'bug'), issue(3, 'Feature')),
		)
		self.assertEqual(result['version'], '0.2.0')
		return

	def test_pr_without_bump_issue_keeps_version(self) -> None:
		for linked in ([], [issue(1, 'Task', 'task')]):
			with self.subTest(linked=len(linked)):
				self.check_output.reset_mock()
				result: dict[str, str] = self.plan(
					'0.1.29\n',
					self.pulls(self.pull()),
					self.graphql(*linked),
				)
				self.assertEqual(result['version'], '0.1.29')
				self.assertEqual(result['new_version'], 'false')
				self.assertEqual(result['tag'], '0.1.29')
				self.assertEqual(result['head_sha'], '')
		return

	def test_direct_push_keeps_version_without_issue_lookup(self) -> None:
		result: dict[str, str] = self.plan(
			'0.1.29\n',
			'',
		)
		self.assertEqual(result['version'], '0.1.29')
		self.assertEqual(result['new_version'], 'false')
		self.assertEqual(result['release'], 'true')
		self.assertEqual(self.check_output.call_count, 2)
		return

	def test_failures_do_not_guess_a_version(self) -> None:
		cases: list[tuple[str, str, list[Any], str]] = [
			('no tag', 'changes/abc\n', [], 'No release version tag'),
			('two prs', '0.1.29\n', [self.pulls(self.pull(), self.pull())], 'Multiple merged PRs'),
			('lookup', '0.1.29\n', [self.pulls(self.pull()), CalledProcessError(1, 'gh')], ''),
			(
				'no head repo',
				'0.1.29\n',
				[self.pulls(self.pull('pr-head', None)), self.graphql(issue(1, 'Bug'))],
				'pr-head',
			),
		]
		for name, tags, responses, message in cases:
			with self.subTest(name=name):
				self.check_output.reset_mock()
				exception: type[Exception] = CalledProcessError if name == 'lookup' else ValueError
				with self.assertRaisesRegex(exception, message):
					self.plan(tags, *responses)
		return
