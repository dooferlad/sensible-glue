# Copyright 2013 Linaro Ltd.  This software is licensed under the
# GNU General Public License version 3 (see the file COPYING).
import re
import tempfile

import commands.commands
import pexpect
import socket
import os


class LocalScreenShell(commands.BashShell):
    """Local shell used for unit testing. Very similar to LocalShell"""
    def __init__(self, prompt):
        os.environ["TERM"] = "xterm"
        super(LocalScreenShell, self).__init__(prompt)
        self.screen_name = "CIRuntimeTestScreen"
        self.proc = pexpect.spawn("/usr/bin/screen -q -S %s" %
                                  self.screen_name)
        self.proc.delaybeforesend = 0
        self.sent = []
        self._set_up_shell()

    def _raw_recv(self, size):
        try:
            return self.proc.read_nonblocking(size, timeout=0.01)
        except pexpect.TIMEOUT:
            raise socket.timeout
        except pexpect.EOF:
            raise socket.timeout

    def recv(self, size=1000):
        rx = self._raw_recv(size)
        return self._strip_excape_sequences(rx)

    def _raw_send(self, value):
        return self.proc.sendline(value.rstrip())

    def send(self, value):
        if not re.search("echo \$\?", value):
            self.sent.append(value.rstrip())
        self._raw_send(value)

    def terminate(self):
        if self.proc:
            self._raw_send("exit\n")
            self.proc.expect("$")
            self.proc = None


class TestSlave(commands.CISlave):
    """Used to run commands for unit testing"""

    def __init__(self, config={}):
        super(TestSlave, self).__init__()
        self.config = config
        self.get_machine()

    def cmd(self, command, comment, sudo=False):
        return super(TestSlave, self).cmd(command, comment, sudo)

    def get_machine(self):
        self.prompt = r"ci_lava_target_machine \#: "
        self.shell = LocalScreenShell(self.prompt)
        self.sftp = TestSFTP()

    def terminate(self):
        self.shell.terminate()


class TestSFTP():
    """Fake SFTP class"""
    def __init__(self):
        self.commands = []
        self.fake_files = {}
        self.fake_file_content = {}

    def set_fake_file_content(self, path, content):
        self.fake_file_content[path] = content

    def open(self, path, mode):
        if path not in self.fake_file_content:
            self.fake_file_content[path] = ""

        self.fake_files[path] = tempfile.mkstemp()
        return os.fdopen(self.fake_files[path][0], mode)

    def put(self, local_path, remote_path):
        self.commands.append({
            "cmd": "put",
            "local_path": local_path,
            "remote_path": remote_path,
        })

    def __del__(self):
        for path in self.fake_files:
            os.remove(self.fake_files[path][1])


class RecordShell(object):
    """BashShell like object. Doesn't execute commands, it just records them"""
    def __init__(self, prompt):
        self.sent = []
        self.last_sent = None
        self.prompt = prompt
        self.responses = [("echo \$\?", "0")]

    def recv(self, size=1000):
        for match, response in self.responses:
            if re.search(match, self.last_sent):
                return self.last_sent + response + "\n" + self.prompt

        # If didn't find a preset response, just echo the command and return
        # a prompt.
        return self.last_sent + self.prompt

    def send(self, value):
        if not re.search("echo \$\?", value):
            self.sent.append(value.rstrip())
        self.last_sent = value

    def match_prompt(self, _ignore):
        return True

    def set_response(self, match, response):
        self.responses.append((match, response))


class RecordSlave(commands.CISlave):
    """Used to record commands sent from unit tests. Nothing is run."""

    def __init__(self, config={}):
        super(RecordSlave, self).__init__()
        self.config = config
        self.get_machine()

    def cmd(self, command, comment, sudo=False):
        return super(RecordSlave, self).cmd(command, comment, sudo)

    def get_machine(self):
        self.prompt = r"ci_lava_target_machine: "
        self.shell = RecordShell(self.prompt)
        self.sftp = None

    def set_response(self, match, response):
        self.shell.set_response(match, response)


class ReplayShell(commands.BashShell):
    """Doesn't run commands. Responds to commands with pre-defined output."""
    def __init__(self, prompt):
        super(ReplayShell, self).__init__(prompt)
        self.responses = []
        self.response_index = 0

    def recv(self, size=1000):
        if self.response_index < len(self.responses):
            rx = self.responses[self.response_index]
        else:
            raise socket.timeout
        self.response_index += 1
        return rx

    def send(self, value):
        pass

    def set_response(self, response):
        self.responses = response


class ReplaySlave(commands.CISlave):
    """Doesn't run commands. Responds to commands with pre-defined output."""
    def __init__(self, config={}):
        super(ReplaySlave, self).__init__()
        self.config = config
        self.get_machine()

    def cmd(self, command, comment, sudo=False):
        return super(ReplaySlave, self).cmd(command, comment, sudo)

    def get_machine(self):
        self.prompt = r"ci_lava_target_machine \#: "
        self.shell = ReplayShell(self.prompt)
        self.sftp = None

    def set_response(self, response):
        self.shell.set_response(response)
