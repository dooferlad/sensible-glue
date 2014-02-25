# Copyright 2013 Linaro Ltd.  This software is licensed under the
# GNU General Public License version 3 (see the file COPYING).

import unittest
import tempfile
import os
import re
from utils import *


class TestSlaveGenerics(unittest.TestCase):
    def setUp(self):
        self.slave = TestSlave("TestShellPrompt \#: ")

    def tearDown(self):
        self.slave.terminate()

    def test_start_wait_for_prompt(self):
        # Simply running setUp does this.
        pass

    def test_command_success(self):
        self.slave.cmd("echo Hello", "echo a message")

    def test_command_failed(self):
        self.assertRaises(
            commands.CommandFailed,
            self.slave.cmd,
            "notacommandthatIknowof", "command fails")

    def test_shell_chunks(self):
        slave = ReplaySlave()
        slave.set_response([u'echo $?\n0',
                            u'\nci_lava_target_machine 10034: '])
        rx = slave._in_shell_cmd("", quiet=True)
        self.assertEqual(["0"], rx)
