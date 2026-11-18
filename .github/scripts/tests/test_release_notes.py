from json import dumps
from os import environ
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from textwrap import dedent
from typing import Optional
from unittest import TestCase
from unittest.mock import (
	MagicMock,
	patch,
)


class ReleaseNotesTests(TestCase):
	def setUp(self) -> None:
		self.directory: TemporaryDirectory = TemporaryDirectory()
		self.addCleanup(self.directory.cleanup)
		self.notes: Path = Path(self.directory.name) / 'release-notes' / 'README.md'
		workflow: str = (Path(__file__).resolve().parents[3] / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
		step: str = workflow.split('      - name: Collect branch changelog for release\n', 1)[1]
		script: str = step.split("          python - <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
		self.script: str = dedent(script)
		self.check_output: MagicMock = MagicMock()
		return

	def pull(self, sha: str = 'pr-head', repository: Optional[str] = 'example/project') -> dict[str, object]:
		return {
			'merged_at': '2026-01-01T00:00:00Z',
			'merge_commit_sha': 'test-head',
			'base': {'ref': 'master', 'repo': {'full_name': 'example/project'}},
			'head': {'ref': 'task/12', 'sha': sha, 'repo': None if repository is None else {'full_name': repository}},
		}

	def tag_calls(self, ref_type: str = 'tag', message: str = 'tag notes') -> list[bytes]:
		results: list[bytes] = [dumps({'object': {'type': ref_type, 'sha': 'tag-object'}}).encode()]
		if ref_type == 'tag':
			results.append(dumps({'message': message}).encode())
		return results

	def run_collector(self, version: str = 'true') -> bytes:
		env: dict[str, str] = {
			'GITHUB_SHA': 'test-head',
			'GITHUB_REPOSITORY': 'example/project',
			'NEW_VERSION': version,
			'RELEASE_TAG': 'v1',
			'RUNNER_TEMP': self.directory.name,
		}
		with patch.dict(environ, env), patch('subprocess.check_output', self.check_output):
			exec(self.script, {})
		return self.notes.read_bytes()

	def api_paths(self) -> list[str]:
		return [call.args[0][-1] for call in self.check_output.call_args_list]

	def test_direct_push_reads_tag_of_pushed_commit(self) -> None:
		self.check_output.side_effect = [dumps([[]]).encode()] + self.tag_calls()
		self.assertEqual(self.run_collector(), b'tag notes')
		self.assertEqual(
			self.api_paths()[1:],
			['repos/example/project/git/ref/tags/changes/test-head', 'repos/example/project/git/tags/tag-object'],
		)
		return

	def test_merged_pr_reads_tag_of_head_sha_in_head_repository(self) -> None:
		for repository in ('example/project', 'fork/project'):
			with self.subTest(repository=repository):
				self.check_output.reset_mock()
				self.check_output.side_effect = [dumps([[self.pull('pr-head', repository)]]).encode()] + self.tag_calls()
				self.assertEqual(self.run_collector(), b'tag notes')
				self.assertEqual(
					self.api_paths()[1:],
					[f'repos/{repository}/git/ref/tags/changes/pr-head', f'repos/{repository}/git/tags/tag-object'],
				)
		return

	def test_unusable_tag_fails_with_repository_and_name(self) -> None:
		cases: list[tuple[str, list[object]]] = [
			('missing', [CalledProcessError(1, 'gh')]),
			('lightweight', self.tag_calls('commit')),
			('empty', self.tag_calls('tag', ' \n')),
		]
		for name, results in cases:
			with self.subTest(name=name):
				self.check_output.reset_mock()
				self.check_output.side_effect = [dumps([[self.pull('pr-head', 'fork/project')]]).encode()] + results
				with self.assertRaisesRegex(ValueError, 'changes/pr-head in fork/project'):
					self.run_collector()
		return

	def test_missing_head_repository_fails(self) -> None:
		self.check_output.side_effect = [dumps([[self.pull('pr-head', None)]]).encode()]
		with self.assertRaisesRegex(ValueError, 'pr-head'):
			self.run_collector()
		return

	def test_existing_release_notes_are_reused_without_tag(self) -> None:
		self.check_output.side_effect = [dumps({'tag_name': 'v1', 'body': 'existing notes'}).encode()]
		self.assertEqual(self.run_collector('false'), b'existing notes')
		self.assertEqual(self.check_output.call_count, 1)
		return
