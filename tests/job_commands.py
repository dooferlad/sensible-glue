# Copyright 2013 Linaro Ltd.  This software is licensed under the
# GNU General Public License version 3 (see the file COPYING).

import shlex
import shutil
import unittest
import tempfile
import os
import re
from utils import *
from subprocess import check_output, STDOUT

# The TODO list...
#     boot              - command not impl
#     disconnect        - command not impl
#     use               - not a nice generic thing yet. Skipping
#     build             - will need expanding once more magic is done for
#                         build caching
#     set_disk_image    - command not impl
#     publish           - command not impl
#     isdir


class TestJobCommands(unittest.TestCase):
    def setUp(self):
        self.basedir = tempfile.mkdtemp()
        os.chdir(self.basedir)
        self.slave = TestSlave()
        self.call_output = None

    def tearDown(self):
        if os.path.exists(self.basedir):
            shutil.rmtree(self.basedir)

        del self.slave

    def call(self, cmd):
        self.call_output = check_output(shlex.split(cmd), stderr=STDOUT)

    def set_up_git_repo(self):
        self.git_repo_name = "git_repo.git"
        self.file_in_repo = "foo"
        self.git_repo_path = os.path.join(self.basedir, self.git_repo_name)
        os.mkdir(self.git_repo_path)
        os.chdir(self.git_repo_path)
        self.call("touch " + self.file_in_repo)
        self.call("git init")
        self.call("git add foo")
        self.call("git commit -m 'foo'")

    def set_up_manifest_repo(self):
        self.manifest_repo_name = "manifest_repo"
        self.file_in_repo = "foo"
        self.manifest_repo_path = os.path.join(self.basedir,
                                               self.manifest_repo_name)
        os.mkdir(self.manifest_repo_path)
        os.chdir(self.manifest_repo_path)

        foo = ['<?xml version="1.0" encoding="UTF-8"?>',
               '  <manifest>',
               '    <remote name="remote" fetch="%s" />' % self.basedir,
               '    <default revision="master" remote="remote" />',
               '    <project name="git_repo" remote="remote"/>',
               '  </manifest>']

        with open("default.xml", "w") as f:
            f.write("\n".join(foo))

        self.call("git init")
        self.call("git add default.xml")
        self.call("git commit -m 'Add test repo default.xml'")

    def set_up_bzr_repo(self):
        self.bzr_repo_name = "bzr_repo"
        self.file_in_repo = "foo"
        self.bzr_repo_path = os.path.join(self.basedir, self.bzr_repo_name)
        os.mkdir(self.bzr_repo_path)
        os.chdir(self.bzr_repo_path)
        self.call("touch " + self.file_in_repo)
        self.call("bzr init")
        self.call("bzr add foo")
        self.call("bzr commit -m 'add foo'")

    def in_working_dir(self):
        self.working_dir = os.path.join(self.basedir, "checkout")
        os.mkdir(self.working_dir)
        os.chdir(self.working_dir)
        self.slave.chdir(self.working_dir)

    def test_cmd(self):
        self.slave.cmd("ls", "a comment")
        self.assertEqual(self.slave.shell.sent, ["ls"])

    def test_checkout_git(self):
        self.set_up_git_repo()
        self.in_working_dir()

        self.slave.checkout("git",
                            self.git_repo_path,
                            branch=None,
                            filename=None,
                            depth=None,
                            name="")

        if self.git_repo_name[-4:] == ".git":
            self.git_repo_name = self.git_repo_name[:-4]

        self.assertTrue(os.path.isfile(
            os.path.join(self.working_dir,
                         self.git_repo_name,
                         self.file_in_repo)))

    def test_checkout_git_exists(self):
        self.set_up_git_repo()
        self.in_working_dir()

        self.slave.checkout("git",
                            self.git_repo_path,
                            branch=None,
                            filename=None,
                            depth=None,
                            name="")

        self.slave.checkout("git",
                            self.git_repo_path,
                            branch=None,
                            filename=None,
                            depth=None,
                            name="")

        # We expect the second git operation to work out that it has already
        # got that repository checked out and just update it...
        self.assertTrue("git pull" in self.slave.shell.sent)

        if self.git_repo_name[-4:] == ".git":
            self.git_repo_name = self.git_repo_name[:-4]

        self.assertTrue(os.path.isfile(
            os.path.join(self.working_dir,
                         self.git_repo_name,
                         self.file_in_repo)))

    def test_checkout_repo(self):
        self.set_up_git_repo()
        self.set_up_manifest_repo()
        self.in_working_dir()

        self.slave.checkout("repo",
                            self.manifest_repo_path,
                            branch=None,
                            filename=None,
                            depth=None,
                            name="")

        self.assertTrue(os.path.isfile(
            os.path.join(self.working_dir,
                         "git_repo",
                         self.file_in_repo)))

    def test_checkout_bzr_branch(self):
        self.set_up_bzr_repo()
        self.in_working_dir()

        self.slave.checkout("bzr", self.bzr_repo_path)

        self.assertTrue(os.path.isfile(
            os.path.join(self.working_dir,
                         self.bzr_repo_name,
                         self.file_in_repo)))

    def test_checkout_bzr_exists(self):
        self.set_up_bzr_repo()
        self.in_working_dir()

        self.slave.checkout("bzr", self.bzr_repo_path)
        self.slave.checkout("bzr", self.bzr_repo_path)

        # We expect the second git operation to work out that it has already
        # got that repository checked out and just update it...
        self.assertTrue("bzr update" in self.slave.shell.sent)

        self.assertTrue(os.path.isfile(
            os.path.join(self.working_dir,
                         self.bzr_repo_name,
                         self.file_in_repo)))

    def test_in_directory(self):
        target = os.path.join(self.basedir, "target")
        self.assertFalse(os.path.isdir(target))
        self.slave.in_directory(target)
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(self.slave.cwd(), target)

    def test_mkdir(self):
        target = os.path.join(self.basedir, "target")
        self.assertFalse(os.path.isdir(target))
        self.slave.mkdir(target)
        self.assertTrue(os.path.isdir(target))

    def test_chdir(self):
        target = os.path.join(self.basedir, "target")
        self.assertFalse(os.path.isdir(target))
        self.slave.mkdir(target)
        self.assertTrue(os.path.isdir(target))
        self.assertNotEqual(self.slave.cwd(), target)
        self.slave.chdir(target)
        self.assertEqual(self.slave.cwd(), target)

    def test_ls(self):
        self.call("touch " + os.path.join(self.basedir, "a_file"))

        self.slave.chdir(self.basedir)
        self.assertEqual(self.slave.ls(), ["a_file"])

        self.call("mkdir " + os.path.join(self.basedir, "a_dir"))
        self.call("touch " + os.path.join(self.basedir, "a_dir",
                                          "another_file"))

        self.assertEqual(self.slave.ls("a_dir"), ["another_file"])
        self.assertEqual(
            self.slave.ls(os.path.join(self.basedir, "a_dir")),
            ["another_file"])

    def test_copy(self):
        filename = os.path.join(self.basedir, "test_file")
        target = os.path.join(self.basedir, "target")

        with open(filename, "w") as f:
            f.write("hello")

        self.slave.move(filename, target)

        with open(target) as f:
            self.assertEqual(f.read(), "hello")

        self.assertFalse(os.path.isfile(filename))

    def test_move(self):
        filename = os.path.join(self.basedir, "test_file")
        target = os.path.join(self.basedir, "target")

        with open(filename, "w") as f:
            f.write("hello")

        self.slave.move(filename, target)

        with open(target) as f:
            self.assertEqual(f.read(), "hello")

        self.assertFalse(os.path.isfile(filename))

    def test_append_to_file(self):
        filename = os.path.join(self.basedir, "test_file")

        with open(filename, "w") as f:
            f.write("hello")

        self.slave.append_to_file(" there", filename)

        with open(filename) as f:
            self.assertEqual(f.read(), "hello there\n")

    def test_setenv(self):
        self.assertEqual(
            self.slave.cmd("echo $CI_RUNTIME_TEST",
                           "test environment variable not is set"), [""])
        self.slave.set_env("CI_RUNTIME_TEST", "True")
        self.assertEqual(
            self.slave.cmd("echo $CI_RUNTIME_TEST",
                           "test environment variable is set"), ["True"])

    def test_write_file(self):
        path = "some/path"
        contents = "some content"
        self.slave.write_file(path, contents)

        with open(self.slave.sftp.fake_files[path][1]) as f:
            self.assertEqual(f.read(), contents)

    def test_write_put_file(self):
        local_path = "some/path"
        remote_path = "remote/path"

        self.slave.put_file(local_path, remote_path)

        self.assertEqual(len(self.slave.sftp.commands), 1)
        self.assertDictEqual(
            self.slave.sftp.commands[0],
            {
                "cmd": "put",
                "local_path": local_path,
                "remote_path": remote_path,
            })

    def test_isdir(self):
        self.assertTrue(self.slave.isdir(self.basedir))
        self.assertFalse(self.slave.isdir(self.basedir + "rrrr"))


class TestJobCommandsFakeRun(unittest.TestCase):
    def setUp(self):
        self.slave = RecordSlave()
        self.basedir = tempfile.mkdtemp()
        os.chdir(self.basedir)
        self.call_output = None

    def tearDown(self):
        if os.path.exists(self.basedir):
            shutil.rmtree(self.basedir)

    def call(self, cmd):
        self.call_output = check_output(shlex.split(cmd))

    def test_install_deps(self):
        self.slave.set_response("dpkg -l .*", "no packages found matching")
        self.slave.install_deps(["repo", "gcc", "git"])

        self.assertTrue(
            re.search(r"^sudo apt-get -yq install\b", self.slave.shell.sent[-1]))
        self.assertTrue(re.search(r"\brepo\b", self.slave.shell.sent[-1]))
        self.assertTrue(re.search(r"\bgcc\b", self.slave.shell.sent[-1]))
        self.assertTrue(re.search(r"\bgit\b", self.slave.shell.sent[-1]))

    def test_build(self):
        self.slave.build()
        self.assertTrue(re.search(r"\bmake\b", self.slave.shell.sent[-1]))
