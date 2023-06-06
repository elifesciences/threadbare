# Change Log
All notable changes to this project will be documented in this file. This change log follows the conventions of [keepachangelog.com](http://keepachangelog.com/).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 3.1.0 - 2023-06-06

### Added

* added a poll for `sshd` in `project_tests.sh` rather than a sleep timer
* added test coverage for `common.isint`
* added v9 `sshd` config with support for RSA algorithims
    - reduced `sshd` timeouts and retries in v9 config

### Changed

* bumps `parallel-ssh` from 1.x to 2.x
* changes in `operations.py` to support `parallel-ssh` 2.x
* unpinned `gevent` dependencies
* replaced running tests individually with `-k` in favour of the `example.py::foo::bar` syntax

### Fixed

* fixed issue with `test_settings` context manager in `example.py` being picked up by pytest
* fixed issue with a drop in test coverage introduced with updated `gevent`
* fixed support for RSA algorithims in newer versions of `sshd`

### Removed

* removed support for running tests under `tox`
* removed `coverage` options for ad-hoc test runs in `test.sh`

## 3.0.0 - 2022-08-33

### Removed

* drops support for Python 2.7

## 2.0.1 - 2022-08-03

### Added

* adds Pipenv by @lsh-0 in https://github.com/elifesciences/threadbare/pull/39
* adds rsync by @lsh-0 in https://github.com/elifesciences/threadbare/pull/40
* adds update-dependencies-py2.sh script and bumps cryptography for py2 by @lsh-0 in https://github.com/elifesciences/threadbare/pull/43

### Changed

* changes default transfer protocol to SCP (vs SFTP) by @lsh-0 in https://github.com/elifesciences/threadbare/pull/34
* execute.execute now re-raises unhandled exceptions in parallel operations by @lsh-0 in https://github.com/elifesciences/threadbare/pull/44
* operations, adds 'display_prefix' option by @lsh-0 in https://github.com/elifesciences/threadbare/pull/45
* bumps parallel-ssh to 1.10.* for python3.8 support. by @lsh-0 in https://github.com/elifesciences/threadbare/pull/49

### Fixed

* fixes case where a fork()ed process never exits by @lsh-0 in https://github.com/elifesciences/threadbare/pull/37

## [Unreleased]

### Added

### Changed

### Fixed

### Removed

