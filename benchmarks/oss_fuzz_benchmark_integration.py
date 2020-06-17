# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Script for setting up an integration of an OSS-Fuzz benchmark. The script
will create oss-fuzz.yaml as well as copy the files from OSS-Fuzz to build the
benchmark."""
import argparse
import datetime
from distutils import dir_util
from distutils import spawn
import os
import logging
import sys
import subprocess

from common import utils


# pytype: disable=import-error
# pylint: disable=import-error,wrong-import-position,ungrouped-imports,too-many-arguments

# TODO(metzman): Don't rely on OSS-Fuzz code. We don't want to depend on it
# because it can easily break use. Especially because:
# 1. We use private methods
# 2. The OSS-Fuzz code depends on absolute imports.
# 3. The OSS-Fuzz code assumes it is run from the OSS-Fuzz directory and can
# accdidentaly break our repo.
OSS_FUZZ_DIR = os.path.join(utils.ROOT_DIR, 'third_party', 'oss-fuzz')
OSS_FUZZ_REPO_PATH = os.path.join(OSS_FUZZ_DIR, 'infra')
sys.path.append(OSS_FUZZ_REPO_PATH)

from common import benchmark_utils
from common import logs
from common import yaml_utils


class BaseRepoManager:
	"""Base repo manager."""

	def __init__(self, repo_dir):
	    self.repo_dir = repo_dir

	def git(self, cmd, check_result=False):
	    """Run a git command.

	    Args:
	      command: The git command as a list to be run.
	      check_result: Should an exception be thrown on failed command.

	    Returns:
	      stdout, stderr, error code.
	    """
	    return execute(['git'] + cmd,
	                         location=self.repo_dir,
	                         check_result=check_result)


class BaseBuilderRepo:
	"""Repo of base-builder images."""

	def __init__(self):
		self.timestamps = []
		self.digests = []

	def add_digest(self, timestamp, digest):
		"""Add a digest."""
		self.timestamps.append(timestamp)
		self.digests.append(digest)

	def find_digest(self, timestamp):
		"""Find the latest image before the given timestamp."""
		index = bisect.bisect_right(self.timestamps, timestamp)
		if index > 0:
			return self.digests[index - 1]

		raise ValueError('Failed to find suitable base-builder.')


def execute(command, location=None, check_result=False):
	""" Runs a shell command in the specified directory location.

	Args:
	command: The command as a list to be run.
	location: The directory the command is run in.
	check_result: Should an exception be thrown on failed command.

	Returns:
	stdout, stderr, error code.

	Raises:
	RuntimeError: running a command resulted in an error.
	"""

	if not location:
		location = os.getcwd()
	process = subprocess.Popen(command,
	                         stdout=subprocess.PIPE,
	                         stderr=subprocess.PIPE,
	                         cwd=location)
	out, err = process.communicate()
	out = out.decode('utf-8', errors='ignore')
	err = err.decode('utf-8', errors='ignore')
	if err:
		logging.debug('Stderr of command \'%s\' is %s.', ' '.join(command), err)
	if check_result and process.returncode:
		raise RuntimeError(
		    'Executing command \'{0}\' failed with error: {1}.'.format(
		        ' '.join(command), err))
	return out, err, process.returncode


def copy_dir_contents(src_dir, dst_dir):
    """Copy the contents of |src_dir| into |dst_dir|."""
    return dir_util.copy_tree(src_dir, dst_dir)


def copy_oss_fuzz_files(project, commit_date, benchmark_dir):
    """Checkout the right files from OSS-Fuzz to build the benchmark based on
    |project| and |commit_date|. Then copy them to |benchmark_dir|."""
    cwd = os.getcwd()
    oss_fuzz_repo_manager = BaseRepoManager(OSS_FUZZ_DIR)
    projects_dir = os.path.join(OSS_FUZZ_DIR, 'projects', project)
    os.chdir(OSS_FUZZ_DIR)
    try:
        # Find an OSS-Fuzz commit that can be used to build the benchmark.
        oss_fuzz_commit, _, _ = oss_fuzz_repo_manager.git([
            'log', '--before=' + commit_date.isoformat(), '-n1', '--format=%H',
            projects_dir
        ], check_result=True)

        oss_fuzz_commit = oss_fuzz_commit.strip()
        if not oss_fuzz_commit:
            logs.warning('No suitable earlier OSS-Fuzz commit found.')
            return False
        oss_fuzz_repo_manager.git(['checkout', oss_fuzz_commit, projects_dir],
                                  check_result=True)
        copy_dir_contents(projects_dir, benchmark_dir)
        return True
    finally:
        oss_fuzz_repo_manager.git(['reset', '--hard'])
        # This must be done in this order or else we reset our fuzzbench repo.
        os.chdir(cwd)


def get_benchmark_name(project, fuzz_target, benchmark_name=None):
    """Returns the name of the benchmark. Returns |benchmark_name| if is set.
    Otherwise returns a name based on |project| and |fuzz_target|."""
    if benchmark_name is not None:
        return benchmark_name
    return project + '_' + fuzz_target


def _load_base_builder_repo():
	"""Get base-image digests."""
	gcloud_path = spawn.find_executable('gcloud')
	if not gcloud_path:
		logging.warning('gcloud not found in PATH.')
		return None

	result, _, _ = execute([
		gcloud_path,
		'container',
		'images',
		'list-tags',
		'gcr.io/oss-fuzz-base/base-builder',
		'--format=json',
		'--sort-by=timestamp',
	],
	                           check_result=True)
	result = json.loads(result)

	repo = BaseBuilderRepo()
	for image in result:
		timestamp = datetime.datetime.fromisoformat(
	    	image['timestamp']['datetime']).astimezone(datetime.timezone.utc)
	repo.add_digest(timestamp, image['digest'])

	return repo


def _replace_base_builder_digest(dockerfile_path, digest):
  """Replace the base-builder digest in a Dockerfile."""
  with open(dockerfile_path) as handle:
    lines = handle.readlines()

  new_lines = []
  for line in lines:
    if line.strip().startswith('FROM'):
      line = 'FROM gcr.io/oss-fuzz-base/base-builder@' + digest + '\n'

    new_lines.append(line)

  with open(dockerfile_path, 'w') as handle:
    handle.write(''.join(new_lines))


def replace_base_builder(benchmark_dir, commit_date):
    """Replace the parent image of the Dockerfile in |benchmark_dir|,
    base-builder (latest), with a version of base-builder that is likely to
    build the project as it was on |commit_date| without issue."""
    base_builder_repo = _load_base_builder_repo()  # pylint: disable=protected-access
    if base_builder_repo:
        base_builder_digest = base_builder_repo.find_digest(commit_date)
        logs.info('Using base-builder with digest %s.', base_builder_digest)
        _replace_base_builder_digest(  # pylint: disable=protected-access
            os.path.join(benchmark_dir, 'Dockerfile'), base_builder_digest)


def create_oss_fuzz_yaml(project, fuzz_target, commit, commit_date, repo_path,
                         benchmark_dir):
    """Create the oss-fuzz.yaml file in |benchmark_dir| based on the values from
    |project|, |fuzz_target|, |commit| and |commit_date|."""
    yaml_filename = os.path.join(benchmark_dir, 'oss-fuzz.yaml')
    config = {
        'project': project,
        'fuzz_target': fuzz_target,
        'commit': commit,
        'commit_date': commit_date,
        'repo_path': repo_path,
    }
    yaml_utils.write(yaml_filename, config)


def integrate_benchmark(project,
                        fuzz_target,
                        commit,
                        commit_date,
                        repo_path,
                        benchmark_name=None):
    """Copies files needed to integrate an OSS-Fuzz benchmark and creates the
    benchmark's oss-fuzz.yaml file."""
    benchmark_name = get_benchmark_name(project, fuzz_target, benchmark_name)
    benchmark_dir = os.path.join(benchmark_utils.BENCHMARKS_DIR, benchmark_name)
    # TODO(metzman): Replace with dateutil since fromisoformat isn't supposed to
    # work on arbitrary iso format strings. Also figure out if i this timezone
    # replace correct.
    commit_date = datetime.datetime.fromisoformat(commit_date).replace(
        tzinfo=datetime.timezone.utc)
    copy_oss_fuzz_files(project, commit_date, benchmark_dir)
    replace_base_builder(benchmark_dir, commit_date)
    create_oss_fuzz_yaml(project, fuzz_target, commit, commit_date, repo_path,
                         benchmark_dir)


def main():
    """Copies files needed to integrate an OSS-Fuzz benchmark and creates the
    benchmark's oss-fuzz.yaml file."""
    parser = argparse.ArgumentParser(description='Integrate a new benchmark.')
    parser.add_argument('-p',
                        '--project',
                        help='Project for benchmark.',
                        required=True)
    parser.add_argument('-f',
                        '--fuzz-target',
                        help='Fuzz target for benchmark.',
                        required=True)
    parser.add_argument('-r',
                        '--repo-path',
                        help=('Absolute path of the project repo in the '
                              'OSS-Fuzz image (e.g. /src/systemd).'),
                        required=True)
    parser.add_argument('-n',
                        '--benchmark-name',
                        help='Benchmark name.',
                        required=False)
    parser.add_argument('-c', '--commit', help='Project commit hash.')
    parser.add_argument('-d', '--date', help='Date of the commit.')
    args = parser.parse_args()
    integrate_benchmark(args.project, args.fuzz_target, args.commit, args.date,
                        args.repo_path, args.benchmark_name)
    return 0


if __name__ == '__main__':
    main()
