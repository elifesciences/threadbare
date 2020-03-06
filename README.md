# Threadbare

A partial replacement for the slice of Fabric 1.x and Paramiko used in 
[elifesciences/builder](https://github.com/elifesciences/builder).

[Documentation](https://elifesciences.github.io/threadbare).

## installation

    pip install threadbare

## usage

Threadbare can be used like this:

```python
import threadbare
threadbare.operations.remote("echo 'hello world!'", host_string='my.server', warn_only=True)
```

or like this:

```python
from threadbare.state import settings
from threadbare.operations import remote
with settings(host_string='my.server', warn_only=True):
    remote("echo 'hello world!'")
```

## local tests

Run the [test suite](./test.sh) with `./test.sh`

Individual tests can be run with `./test.sh -k test_fn_name`

## remote tests

A set of tests that also serve as working examples of threadbare's functionality can be executed by starting a dummy SSH 
server:

    ./tests-remote/sshd-server.sh

And then, in another terminal, run [example.py](./example.py) with:

    ./test-examples.sh

While the examples are harmless they do involve uploading and downloading files to `/tmp`, testing permissions and 
invoking `sudo`. Individual tests can be run with `./test-examples.sh -k test_fn_name`.

The dummy ssh server creates the temporary directory `/tmp/sshd-dummy` and writes the host and user certificates there.

The only user that may connect to this dummy SSH server is the current user using the certificate generated for them.

See `./tests-remote/ssh-client.sh` for a working example on connecting to the dummy SSH server.

## local+remote tests

This runs a dummy ssh server and runs both the local unit tests as well as the remote
tests. It's used in CI and generates a set of temporary credentials with deliberately 
insecure ssh configuration. Be cautious.

    ./project_tests.sh

# a guide to Threadbare for developers

Threadbare is comprised of just three modules:

1. `state`
2. `operations`
3. `execute`

## state

([source](https://github.com/elifesciences/threadbare/blob/develop/threadbare/state.py))

Underpinning all of Fabric is it's manipulation of a global state dictionary called the 'environment'.

For the most part this manipulation is sane, *single threaded* and predictable.

It has many defaults and functions will dip into the environment dictionary and pull out settings as they need them.

Global state can be built up by nesting context managers like `settings` or `hide` or `lcd`, pushing new state into the
environment dictionary, and then popping it off as execution leaves the context manager.

The `state` module replicates this mechanism but with no initial defaults. Default values are pushed back into the 
functions and may be overridden globally in a general way or overridden specifically by passing in a keyword argument to
the function.

This change:

* improves locality of reference. All options that a function operates on are defined right there with the function.
* keeps the `state` module small and dumb and predictable

## operations

([source](https://github.com/elifesciences/threadbare/blob/develop/threadbare/operations.py))

Fabric provides a set of very useful commands, like `local` or `sudo` or `cd`.

The `operations` module re-implements these commands and they make heavy use of the `state` module.

Not all commands have been re-implemented, just those in use by Builder.

A big part of the `operations` module is running commands on a remote host. Where Fabric uses it's sister project 
Paramiko, Threadbare uses a library called PSSH, or ParallelSSH. ParallelSSH itself wraps another project of theirs 
called `ssh-python`, an interface between `libssh` and Python. ParallelSSH does a little more than just wrap 
`ssh-python`, it also provides a higher level (and more convenient) interface to basic network operations and ensures
thread safety.

Threadbare does *not* use the parallel capabilities of ParallelSSH. See `execute`.

## execute

([source](https://github.com/elifesciences/threadbare/blob/develop/threadbare/execute.py))

Fabric provides an interface for running commands in parallel using their global state manipulation mechanism and set of
operations. It uses Python's `multiprocessing` module.

Threadbare re-implements this mechanism in `execute`, also using `multiprocessing`.

In Fabric the parallelism is used primarily to execute commands on multiple hosts simultaneously, so the interfaces are
skewed towards that. Threadbare is more general purpose but provides the function `execute_with_hosts` that behaves as 
Fabric's `execute` does.

Both Threadbare and Fabric share the same caveats of running code in different processes using `multiprocessing` with a
mechanism for manipulating global state. 

* changes to global state within the worker function does not propagate back to the parent
* SSH connections cannot be passed to child processes so new connections are made within the child process if necessary
* child processes cannot prompt for input. They have no access to stdin.
* child processes may die or throw exceptions that can't be properly handled in the parent

