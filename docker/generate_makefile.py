# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Simple generator for local Makefile rules."""

import os
import shlex
import yaml

BASE_TAG = 'gcr.io/fuzzbench'
BENCHMARKS_DIR = os.path.join(os.path.dirname(__file__), os.pardir,
                              'benchmarks')
FUZZERS_DIR = os.path.join(os.path.dirname(__file__), os.pardir, 'fuzzers')

BOILERPLATE = """
cache_from = $(if ${RUNNING_ON_CI},--cache-from {fuzzer},)
"""

FUZZER_TEMPLATE = """
.{fuzzer}-builder: base-builder
	docker build \\
    --tag {base_tag}/builders/{fuzzer} \\
    --file fuzzers/{fuzzer}/builder.Dockerfile \\
    $(call cache_from,{base_tag}/builders/{fuzzer}) \\
    fuzzers/{fuzzer}

.pull-{fuzzer}-builder: pull-base-builder
	docker pull {base_tag}/builders/{fuzzer}
"""

FUZZER_BENCHMARK_RUN_TARGETS_TEMPLATE = """
build-{fuzzer_variant_name}-{benchmark}: .{fuzzer}-{benchmark}-runner

pull-{fuzzer_variant_name}-{benchmark}: .pull-{fuzzer}-{benchmark}-runner

run-{fuzzer_variant_name}-{benchmark}: .{fuzzer}-{benchmark}-runner
	docker run \\
    --cpus=1 \\
    --cap-add SYS_NICE \\
    --cap-add SYS_PTRACE \\
    -e FUZZ_OUTSIDE_EXPERIMENT=1 \\
    -e TRIAL_ID=1 \\
    -e FUZZER={fuzzer} \\
    -e BENCHMARK={benchmark} \\
    {fuzzer_variant_env} \\
    -it {base_tag}/runners/{fuzzer}/{benchmark}

test-run-{fuzzer_variant_name}-{benchmark}: .{fuzzer}-{benchmark}-runner
	docker run \\
    --cap-add SYS_NICE \\
    --cap-add SYS_PTRACE \\
    -e FUZZ_OUTSIDE_EXPERIMENT=1 \\
    -e TRIAL_ID=1 \\
    -e FUZZER={fuzzer} \\
    -e BENCHMARK={benchmark} \\
    -e MAX_TOTAL_TIME=20 \\
    -e SNAPSHOT_PERIOD=10 \\
    {fuzzer_variant_env} \\
    {base_tag}/runners/{fuzzer}/{benchmark}

debug-{fuzzer_variant_name}-{benchmark}: .{fuzzer}-{benchmark}-runner
	docker run \\
    --cpus=1 \\
    --cap-add SYS_NICE \\
    --cap-add SYS_PTRACE \\
    -e FUZZ_OUTSIDE_EXPERIMENT=1 \\
    -e TRIAL_ID=1 \\
    -e FUZZER={fuzzer} \\
    -e BENCHMARK={benchmark} \\
    {fuzzer_variant_env} \\
    --entrypoint "/bin/bash" \\
    -it {base_tag}/runners/{fuzzer}/{benchmark}
"""

FUZZER_BENCHMARK_TEMPLATE = """
.{fuzzer}-{benchmark}-builder: .{fuzzer}-builder
	docker build \\
    --tag {base_tag}/builders/{fuzzer}/{benchmark} \\
    --build-arg fuzzer={fuzzer} \\
    --build-arg benchmark={benchmark} \\
    $(call cache_from,{base_tag}/builders/{fuzzer}/{benchmark}) \\
    --file docker/benchmark-builder/Dockerfile \\
    .

.pull-{fuzzer}-{benchmark}-builder: .pull-{fuzzer}-builder
	docker pull {base_tag}/builders/{fuzzer}/{benchmark}

ifeq (,$(filter {fuzzer},coverage coverage_source_based))

.{fuzzer}-{benchmark}-intermediate-runner: base-runner
	docker build \\
    --tag {base_tag}/runners/{fuzzer}/{benchmark}-intermediate \\
    --file fuzzers/{fuzzer}/runner.Dockerfile \\
    $(call cache_from,{base_tag}/runners/{fuzzer}/{benchmark}-intermediate) \\
    fuzzers/{fuzzer}

.pull-{fuzzer}-{benchmark}-intermediate-runner: pull-base-runner
	docker pull {base_tag}/runners/{fuzzer}/{benchmark}-intermediate

.{fuzzer}-{benchmark}-runner: .{fuzzer}-{benchmark}-builder .{fuzzer}-{benchmark}-intermediate-runner
	docker build \\
    --tag {base_tag}/runners/{fuzzer}/{benchmark} \\
    --build-arg fuzzer={fuzzer} \\
    --build-arg benchmark={benchmark} \\
    $(call cache_from,{base_tag}/runners/{fuzzer}/{benchmark}) \\
    --file docker/benchmark-runner/Dockerfile \\
    .

.pull-{fuzzer}-{benchmark}-runner: .pull-{fuzzer}-{benchmark}-builder .pull-{fuzzer}-{benchmark}-intermediate-runner
	docker pull {base_tag}/runners/{fuzzer}/{benchmark}

""" + FUZZER_BENCHMARK_RUN_TARGETS_TEMPLATE + """

else
# Coverage builds don't need runners.
build-{fuzzer}-{benchmark}: .{fuzzer}-{benchmark}-builder
pull-{fuzzer}-{benchmark}: .pull-{fuzzer}-{benchmark}-builder

endif
"""

OSS_FUZZER_BENCHMARK_RUN_TARGETS_TEMPLATE = """
build-{fuzzer_variant_name}-{benchmark}: .{fuzzer}-{benchmark}-oss-fuzz-runner

pull-{fuzzer_variant_name}-{benchmark}: .pull-{fuzzer}-{benchmark}-oss-fuzz-runner

run-{fuzzer_variant_name}-{benchmark}: .{fuzzer}-{benchmark}-oss-fuzz-runner
	docker run \\
    --cpus=1 \\
    --cap-add SYS_NICE \\
    --cap-add SYS_PTRACE \\
    -e FUZZ_OUTSIDE_EXPERIMENT=1 \\
    -e FORCE_LOCAL=1 \\
    -e TRIAL_ID=1 \\
    -e FUZZER={fuzzer} \\
    -e BENCHMARK={benchmark} \\
    -e FUZZ_TARGET=$({benchmark}-fuzz-target) \\
    {fuzzer_variant_env} \\
    -it {base_tag}/runners/{fuzzer}/{benchmark}

test-run-{fuzzer_variant_name}-{benchmark}: .{fuzzer}-{benchmark}-oss-fuzz-runner
	docker run \\
    --cap-add SYS_NICE \\
    --cap-add SYS_PTRACE \\
    -e FUZZ_OUTSIDE_EXPERIMENT=1 \\
    -e FORCE_LOCAL=1 \\
    -e TRIAL_ID=1 \\
    -e FUZZER={fuzzer} \\
    -e BENCHMARK={benchmark} \\
    -e FUZZ_TARGET=$({benchmark}-fuzz-target) \\
    -e MAX_TOTAL_TIME=20 \\
    -e SNAPSHOT_PERIOD=10 \\
    {fuzzer_variant_env} \\
    {base_tag}/runners/{fuzzer}/{benchmark}

debug-{fuzzer_variant_name}-{benchmark}: .{fuzzer}-{benchmark}-oss-fuzz-runner
	docker run \\
    --cpus=1 \\
    --cap-add SYS_NICE \\
    --cap-add SYS_PTRACE \\
    -e FUZZ_OUTSIDE_EXPERIMENT=1 \\
    -e FORCE_LOCAL=1 \\
    -e TRIAL_ID=1 \\
    -e FUZZER={fuzzer} \\
    -e BENCHMARK={benchmark} \\
    -e FUZZ_TARGET=$({benchmark}-fuzz-target) \\
    {fuzzer_variant_env} \\
    --entrypoint "/bin/bash" \\
    -it {base_tag}/runners/{fuzzer}/{benchmark}
"""

OSS_FUZZER_BENCHMARK_TEMPLATE = """
.{fuzzer}-{benchmark}-oss-fuzz-builder-intermediate:
	docker build \\
    --tag {base_tag}/builders/{fuzzer}/{benchmark}-intermediate \\
    --file=fuzzers/{fuzzer}/builder.Dockerfile \\
    --build-arg parent_image=gcr.io/fuzzbench/oss-fuzz/$({benchmark}-project-name)@sha256:$({benchmark}-oss-fuzz-builder-hash) \\
    $(call cache_from,{base_tag}/builders/{fuzzer}/{benchmark}-intermediate) \\
    fuzzers/{fuzzer}

.pull-{fuzzer}-{benchmark}-oss-fuzz-builder-intermediate:
	docker pull {base_tag}/builders/{fuzzer}/{benchmark}-intermediate

.{fuzzer}-{benchmark}-oss-fuzz-builder: .{fuzzer}-{benchmark}-oss-fuzz-builder-intermediate
	docker build \\
    --tag {base_tag}/builders/{fuzzer}/{benchmark} \\
    --file=docker/oss-fuzz-builder/Dockerfile \\
    --build-arg parent_image={base_tag}/builders/{fuzzer}/{benchmark}-intermediate \\
    --build-arg fuzzer={fuzzer} \\
    --build-arg benchmark={benchmark} \\
    $(call cache_from,{base_tag}/builders/{fuzzer}/{benchmark}) \\
    .

.pull-{fuzzer}-{benchmark}-oss-fuzz-builder: .pull-{fuzzer}-{benchmark}-oss-fuzz-builder-intermediate
	docker pull {base_tag}/builders/{fuzzer}/{benchmark}

ifeq (,$(filter {fuzzer},coverage coverage_source_based))

.{fuzzer}-{benchmark}-oss-fuzz-intermediate-runner: base-runner
	docker build \\
    --tag {base_tag}/runners/{fuzzer}/{benchmark}-intermediate \\
    --file fuzzers/{fuzzer}/runner.Dockerfile \\
    $(call cache_from,{base_tag}/runners/{fuzzer}/{benchmark}-intermediate) \\
    fuzzers/{fuzzer}

.pull-{fuzzer}-{benchmark}-oss-fuzz-intermediate-runner: pull-base-runner
	docker pull {base_tag}/runners/{fuzzer}/{benchmark}-intermediate

.{fuzzer}-{benchmark}-oss-fuzz-runner: .{fuzzer}-{benchmark}-oss-fuzz-builder .{fuzzer}-{benchmark}-oss-fuzz-intermediate-runner
	docker build \\
    --tag {base_tag}/runners/{fuzzer}/{benchmark} \\
    --build-arg fuzzer={fuzzer} \\
    --build-arg benchmark={benchmark} \\
    $(call cache_from,{base_tag}/runners/{fuzzer}/{benchmark}) \\
    --file docker/oss-fuzz-runner/Dockerfile \\
    .

.pull-{fuzzer}-{benchmark}-oss-fuzz-runner: .pull-{fuzzer}-{benchmark}-oss-fuzz-builder .pull-{fuzzer}-{benchmark}-oss-fuzz-intermediate-runner
	docker pull {base_tag}/runners/{fuzzer}/{benchmark}

""" + OSS_FUZZER_BENCHMARK_RUN_TARGETS_TEMPLATE + """

else

build-{fuzzer}-{benchmark}: .{fuzzer}-{benchmark}-oss-fuzz-builder
pull-{fuzzer}-{benchmark}: .pull-{fuzzer}-{benchmark}-oss-fuzz-builder

endif
"""


def generate_fuzzer(fuzzer,
                    benchmarks,
                    oss_fuzz_benchmarks,
                    fuzzer_variant=None):
    """Output make rules for a single fuzzer."""
    if fuzzer_variant:
        fuzzer_variant_name = fuzzer_variant['name']
        fuzzer_variant_env = ' '.join([
            '-e {k}={v}'.format(k=k, v=shlex.quote(str(v)))
            for k, v in fuzzer_variant['env'].items()
        ])

        # Generate run targets for the fuzzer variant-benchmark pairs.
        for benchmark in benchmarks:
            print(
                FUZZER_BENCHMARK_RUN_TARGETS_TEMPLATE.format(
                    fuzzer=fuzzer,
                    fuzzer_variant_name=fuzzer_variant_name,
                    fuzzer_variant_env=fuzzer_variant_env,
                    benchmark=benchmark,
                    base_tag=BASE_TAG))
        for benchmark in oss_fuzz_benchmarks:
            print(
                OSS_FUZZER_BENCHMARK_RUN_TARGETS_TEMPLATE.format(
                    fuzzer=fuzzer,
                    fuzzer_variant_name=fuzzer_variant_name,
                    fuzzer_variant_env=fuzzer_variant_env,
                    benchmark=benchmark,
                    base_tag=BASE_TAG))

    else:
        fuzzer_variant_name = fuzzer

        # Generate build rules for the fuzzer itself.
        print(FUZZER_TEMPLATE.format(fuzzer=fuzzer, base_tag=BASE_TAG))

        # Generate rules for fuzzer-benchmark pairs.
        for benchmark in benchmarks:
            print(
                FUZZER_BENCHMARK_TEMPLATE.format(
                    fuzzer=fuzzer,
                    fuzzer_variant_name=fuzzer_variant_name,
                    fuzzer_variant_env='',
                    benchmark=benchmark,
                    base_tag=BASE_TAG))
        for benchmark in oss_fuzz_benchmarks:
            print(
                OSS_FUZZER_BENCHMARK_TEMPLATE.format(
                    fuzzer=fuzzer,
                    fuzzer_variant_name=fuzzer_variant_name,
                    fuzzer_variant_env='',
                    benchmark=benchmark,
                    base_tag=BASE_TAG))

    # Generate rules for building/pulling all target/benchmark pairs.
    all_benchmarks = benchmarks + oss_fuzz_benchmarks
    all_build_targets = ' '.join([
        'build-{0}-{1}'.format(fuzzer_variant_name, benchmark)
        for benchmark in all_benchmarks
    ])
    all_pull_targets = ' '.join([
        'pull-{0}-{1}'.format(fuzzer_variant_name, benchmark)
        for benchmark in all_benchmarks
    ])
    print('build-{fuzzer}-all: {all_targets}'.format(
        fuzzer=fuzzer_variant_name, all_targets=all_build_targets))
    print('pull-{fuzzer}-all: {all_targets}'.format(
        fuzzer=fuzzer_variant_name, all_targets=all_pull_targets))


def main():
    """Main entry point."""
    # Output boilerplate used by other templates and generated rules.
    print(BOILERPLATE)

    # Compute the list of benchmarks. OSS-Fuzz benchmarks are built
    # differently from standard benchmarks.
    benchmarks = []
    oss_fuzz_benchmarks = []
    for benchmark in os.listdir(BENCHMARKS_DIR):
        benchmark_path = os.path.join(BENCHMARKS_DIR, benchmark)
        if not os.path.isdir(benchmark_path):
            continue
        if os.path.exists(os.path.join(benchmark_path, 'build.sh')):
            benchmarks.append(benchmark)
        if os.path.exists(os.path.join(benchmark_path, 'oss-fuzz.yaml')):
            oss_fuzz_benchmarks.append(benchmark)

    # Generate the build rules for fuzzer/benchmark pairs.
    fuzzers_and_variants = []
    for fuzzer in os.listdir(FUZZERS_DIR):
        # Skip non-directory files. These do not represent fuzzers.
        fuzzer_dir = os.path.join(FUZZERS_DIR, fuzzer)
        if not os.path.isdir(fuzzer_dir):
            continue

        # The default fuzzer does not contain any special build arguments.
        generate_fuzzer(fuzzer, benchmarks, oss_fuzz_benchmarks)
        fuzzers_and_variants.append(fuzzer)

        # If there are variants, generate rules for them as well.
        variants_path = os.path.join(fuzzer_dir, 'variants.yaml')
        if not os.path.exists(variants_path):
            continue

        with open(variants_path) as file_handle:
            config = yaml.load(file_handle, yaml.SafeLoader)
            assert 'variants' in config

        for fuzzer_variant in config['variants']:
            assert 'name' in fuzzer_variant
            fuzzer_variant_name = fuzzer_variant['name']
            generate_fuzzer(fuzzer,
                            benchmarks,
                            oss_fuzz_benchmarks,
                            fuzzer_variant=fuzzer_variant)
            fuzzers_and_variants.append(fuzzer_variant_name)

    # Generate rules to build all known targets.
    all_build_targets = ' '.join(
        ['build-{0}-all'.format(name) for name in fuzzers_and_variants])
    all_pull_targets = ' '.join(
        ['pull-{0}-all'.format(name) for name in fuzzers_and_variants])
    print('build-all: {all_targets}'.format(all_targets=all_build_targets))
    print('pull-all: {all_targets}'.format(all_targets=all_pull_targets))


if __name__ == '__main__':
    main()
