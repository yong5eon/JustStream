from json import loads
from os import environ
from pathlib import Path
from re import fullmatch
from subprocess import check_output
from typing import Any, Optional

BUMP_ORDER: dict[str, int] = {
	'keep': 0,
	'patch': 1,
	'minor': 2,
}
NAME_BUMPS: dict[str, str] = {
	'feature': 'minor',
	'bug': 'patch',
	'fix': 'patch',
}
CLOSING_ISSUES_QUERY: str = """
query($owner: String!, $name: String!, $number: Int!) {
	repository(owner: $owner, name: $name) {
		pullRequest(number: $number) {
			closingIssuesReferences(first: 100) {
				nodes {
					number
					issueType { name }
				}
			}
		}
	}
}
"""


def higher(
	bumps: list[str],
) -> str:
	"""
	Return the highest version increase in bumps, or keep when empty.
	"""
	return max(
		bumps,
		key=BUMP_ORDER.__getitem__,
		default='keep',
	)


def classify_issue(
	issue: dict[str, Any],
) -> str:
	"""
	Classify one issue by its type only; labels never affect the version.
	"""
	issue_type: Optional[dict[str, str]] = issue['issueType']
	if issue_type is None:
		return 'keep'
	return NAME_BUMPS.get(
		issue_type['name'].lower(),
		'keep',
	)


def latest_release(
	tags: list[str],
) -> tuple[tuple[int, int, int], str]:
	"""
	Return the highest MAJOR.MINOR.PATCH version and its tag name.
	"""
	releases: dict[tuple[int, int, int], str] = {}
	for tag in tags:
		match = fullmatch(
			r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',
			tag,
		)
		if match is not None:
			releases[(int(match[1]), int(match[2]), int(match[3]))] = tag
	if not releases:
		raise ValueError('No release version tag found')
	version: tuple[int, int, int] = max(releases)
	return version, releases[version]


def next_version(
	version: tuple[int, int, int],
	bump: str,
) -> tuple[int, int, int]:
	"""
	Apply a minor, patch or keep increase to a version.
	"""
	major, minor, patch = version
	if bump == 'minor':
		return major, minor + 1, 0
	if bump == 'patch':
		return major, minor, patch + 1
	return version


def find_merged_pull(
	repository: str,
	sha: str,
) -> Optional[dict[str, Any]]:
	"""
	Return the pull request merged into master as sha, or None for a direct push.
	"""
	output: str = check_output([
		'gh',
		'api',
		'--paginate',
		'--jq',
		'.[]',
		f'repos/{repository}/commits/{sha}/pulls?per_page=100',
	], text=True)
	pulls: list[dict[str, Any]] = [
		pull
		for pull in map(loads, output.splitlines())
		if pull['merged_at'] is not None
		and pull['merge_commit_sha'] == sha
		and pull['base']['ref'] == 'master'
		and pull['base']['repo']['full_name'] == repository
	]
	if len(pulls) > 1:
		raise ValueError('Multiple merged PRs found for the release commit')
	return pulls[0] if pulls else None


def closing_issues(
	repository: str,
	number: int,
) -> list[dict[str, Any]]:
	"""
	Return the issues GitHub links to close with the pull request.
	"""
	owner, name = repository.split('/')
	data: dict[str, Any] = loads(check_output([
		'gh',
		'api',
		'graphql',
		'-f',
		f'query={CLOSING_ISSUES_QUERY}',
		'-f',
		f'owner={owner}',
		'-f',
		f'name={name}',
		'-F',
		f'number={number}',
	]))
	return data['data']['repository']['pullRequest']['closingIssuesReferences']['nodes']


def main() -> None:
	before: str = environ['BEFORE']
	if not before or set(before) == {'0'}:
		raise ValueError('Missing push base commit')
	repository: str = environ['GITHUB_REPOSITORY']
	sha: str = environ['GITHUB_SHA']
	build: int = int(environ['GITHUB_RUN_NUMBER'])
	if build < 1:
		raise ValueError('Build number must be positive')
	tags: list[str] = check_output(
		['git', 'tag', '--merged', before],
		text=True,
	).splitlines()
	version, tag = latest_release(tags)
	pull: Optional[dict[str, Any]] = find_merged_pull(
		repository,
		sha,
	)
	issues: list[dict[str, Any]] = [] if pull is None else closing_issues(
		repository,
		pull['number'],
	)
	bump: str = higher([classify_issue(issue) for issue in issues])
	new_version: bool = bump != 'keep'
	major, minor, patch = next_version(
		version,
		bump,
	)
	planned: str = f'{major}.{minor}.{patch}'
	head_sha: str = ''
	head_repository: str = ''
	if new_version:
		source: dict[str, Any] = pull['head']
		if source.get('repo') is None:
			raise ValueError(f'PR head repository is unavailable for tag {source["sha"]}')
		head_sha = source['sha']
		head_repository = source['repo']['full_name']
		tag = planned
		print(f'New public version ({bump}) from issues: {[issue["number"] for issue in issues]}')
	else:
		print('Keeping MAJOR.MINOR.PATCH; publishing a new wheel build')
	print(f'Planned version: {planned}, wheel build: {build}')
	with Path(environ['GITHUB_OUTPUT']).open(
		'a',
		encoding='utf-8',
	) as output:
		output.write(f'release=true\nversion={planned}\n')
		output.write(f'build={build}\nnew_version={str(new_version).lower()}\n')
		output.write(f'tag={tag}\n')
		output.write(f'head_sha={head_sha}\nhead_repository={head_repository}\n')
	return


if __name__ == '__main__':
	main()
