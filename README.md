# threadbare

A partial replacement for the slice of Fabric 1.x and Paramiko used in [Builder](https://github.com/elifesciences/builder)

See [TODO.md](./TODO.md) for what remains to be implemented for the first stable release.

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
