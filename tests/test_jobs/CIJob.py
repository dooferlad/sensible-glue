#!/usr/bin/python

# Copyright 2013 Linaro Ltd.  This software is licensed under the
# GNU General Public License version 3 (see the file COPYING).

from commands.commands import *


class DefaultJob(LinaroCIJob):
    def __init__(self):
        super(DefaultJob, self).__init__()
        self.run_called = False
        self.setup_called = False
        self.some_function_called = False

    def configure(self, parameters):
        self.parameters = parameters

    def run(self):
        self.run_called = True

    def setup(self):
        self.setup_called = True

    def some_function(self):
        self.some_function_called = True


class SomeJob(DefaultJob):
    pass
