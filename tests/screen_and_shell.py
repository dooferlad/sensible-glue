# Copyright 2013 Linaro Ltd.  This software is licensed under the
# GNU General Public License version 3 (see the file COPYING).

import unittest
import tempfile
import os
import re
from utils import *


class TestGnuScreenWrapper(unittest.TestCase):
    def setUp(self):
        self.shell = LocalScreenShell("TestShellPrompt \#: ")

    def tearDown(self):
        self.shell.terminate()

    def rx_until_prompt(self, tries=1000):
        all_rx = ""
        tries_remaining = tries
        while tries_remaining > 0:
            tries_remaining -= 1
            rx = self.shell.recv()
            all_rx += rx

            if self.shell.match_prompt(rx):
                return all_rx

    def test_start_wait_for_prompt(self):
        # Simply running setUp does this.
        pass

    def test_run_command_wait_for_prompt(self):
        """ Run a command that will succeed.
        """

        # A command that will always succeed
        self.shell.send("echo Hello\n")
        # We shouldn't get a prompt match until the command has passed
        # because we have set the prompt up to contain the command
        # number.
        rx = self.rx_until_prompt()
        self.assertTrue(re.search("\nHello\r?\n", rx))

    def test_long_lines(self):
        """Expect unbroken lines, no matter what length"""

        for length in [70, 80, 81, 300]:
            message = "a" * length
            self.shell.send("echo %s\n" % message)

            rx = self.rx_until_prompt()
            self.assertTrue(re.search("\n%s\b?\r?\n" % message, rx))

    def test_strip_colour_codes(self):
        """ls --color will colour directories. Check that we clean this"""
        directory = tempfile.mkdtemp()
        os.mkdir(os.path.join(directory, "a"))
        self.shell.send("ls --color %s\n" % directory)
        rx = self.rx_until_prompt()
        self.assertTrue(re.search("\na\b?\r?\n", rx))

    def test_unwrap(self):
        dirname = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(dirname, "unwrap.txt")) as f:
            rx = f.read()
            clean = self.shell._strip_excape_sequences(rx).rstrip()

            self.assertEqual(clean,
                             "ci_lava_target_machine 10: cd /home/ubuntu/"
                             "_not_backed_up_/ci-runtime/kernel/"
                             "linux-linaro-tracking")

    def test_clean_ctrl_h(self):
        dirname = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(dirname, "in_esc_h.txt")) as f:
            rx = f.read()
            clean = self.shell._strip_excape_sequences(rx).rstrip()

            self.assertEqual(clean,
                             "echo Hello\n"
                             "Hello\n"
                             "ci_lava_target_machine 3: echo $?\n"
                             "0\n"
                             "ci_lava_target_machine 4:")
