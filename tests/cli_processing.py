# Copyright 2013 Linaro Ltd.  This software is licensed under the
# GNU General Public License version 3 (see the file COPYING).


import sys
from commands.commands import CIJobRuntime
import unittest


class TestArgParse(unittest.TestCase):
    def setUp(self):
        self.test_job_path = "tests/test_jobs"
        if not self.test_job_path in sys.path:
            sys.path.append(self.test_job_path)
            self.added_path = True
        else:
            self.added_path = False

    def tearDown(self):
        if self.added_path:
            sys.path.remove(self.test_job_path)

    def test_defaults(self):
        runtime = CIJobRuntime([])
        self.assertEqual(runtime.file_name, "CIJob")
        self.assertEqual(runtime.job_name, "DefaultJob")
        self.assertEqual(runtime.job.parameters, [])
        self.assertEqual(runtime.job.__class__.__name__, "DefaultJob")
        self.assertTrue(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)

    def test_file_name_arg(self):
        runtime = CIJobRuntime(["CIJob2"])
        self.assertEqual(runtime.file_name, "CIJob2")
        self.assertEqual(runtime.job_name, "DefaultJob")
        self.assertEqual(runtime.job.parameters, [])
        self.assertEqual(runtime.job.__class__.__name__, "DefaultJob")
        self.assertTrue(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)

    def test_job_name_arg(self):
        runtime = CIJobRuntime(["SomeJob"])
        self.assertEqual(runtime.file_name, "CIJob")
        self.assertEqual(runtime.job_name, "SomeJob")
        self.assertEqual(runtime.job.parameters, [])
        self.assertEqual(runtime.job.__class__.__name__, "SomeJob")
        self.assertTrue(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)

    def test_job_arguments(self):
        runtime = CIJobRuntime(["--thing"])
        self.assertEqual(runtime.file_name, "CIJob")
        self.assertEqual(runtime.job_name, "DefaultJob")
        self.assertEqual(runtime.job.parameters, ["--thing"])
        self.assertEqual(runtime.job.__class__.__name__, "DefaultJob")
        self.assertTrue(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)

    def test_file_name_job_arguments(self):
        runtime = CIJobRuntime(["CIJob2", "--thing"])
        self.assertEqual(runtime.file_name, "CIJob2")
        self.assertEqual(runtime.job_name, "DefaultJob")
        self.assertEqual(runtime.job.parameters, ["--thing"])
        self.assertEqual(runtime.job.__class__.__name__, "DefaultJob")
        self.assertTrue(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)

    def test_file_name_and_job_name(self):
        runtime = CIJobRuntime(["CIJob2", "AnotherJob"])
        self.assertEqual(runtime.file_name, "CIJob2")
        self.assertEqual(runtime.job_name, "AnotherJob")
        self.assertEqual(runtime.job.parameters, [])
        self.assertEqual(runtime.job.__class__.__name__, "AnotherJob")
        self.assertTrue(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)

    def test_job_name_job_arguments(self):
        runtime = CIJobRuntime(["SomeJob", "--an", "argument"])
        self.assertEqual(runtime.file_name, "CIJob")
        self.assertEqual(runtime.job_name, "SomeJob")
        self.assertEqual(runtime.job.parameters, ["--an", "argument"])
        self.assertEqual(runtime.job.__class__.__name__, "SomeJob")
        self.assertTrue(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)

    def test_file_name_job_name_job_arguments(self):
        runtime = CIJobRuntime(["CIJob2", "AnotherJob", "--an", "argument"])
        self.assertEqual(runtime.file_name, "CIJob2")
        self.assertEqual(runtime.job_name, "AnotherJob")
        self.assertEqual(runtime.job.parameters, ["--an", "argument"])
        self.assertEqual(runtime.job.__class__.__name__, "AnotherJob")
        self.assertTrue(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)

    # Now test calling individual functions
    def test_defaults_some_function(self):
        runtime = CIJobRuntime(["some_function"])
        self.assertEqual(runtime.file_name, "CIJob")
        self.assertEqual(runtime.job_name, "DefaultJob")
        self.assertEqual(runtime.job.parameters, [])
        self.assertEqual(runtime.job.__class__.__name__, "DefaultJob")
        self.assertFalse(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)
        self.assertTrue(runtime.job.some_function_called)

    def test_file_name_arg(self):
        runtime = CIJobRuntime(["CIJob2", "some_function"])
        self.assertEqual(runtime.file_name, "CIJob2")
        self.assertEqual(runtime.job_name, "DefaultJob")
        self.assertEqual(runtime.job.parameters, [])
        self.assertEqual(runtime.job.__class__.__name__, "DefaultJob")
        self.assertFalse(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)
        self.assertTrue(runtime.job.some_function_called)

    def test_job_name_arg(self):
        runtime = CIJobRuntime(["SomeJob", "some_function"])
        self.assertEqual(runtime.file_name, "CIJob")
        self.assertEqual(runtime.job_name, "SomeJob")
        self.assertEqual(runtime.job.parameters, [])
        self.assertEqual(runtime.job.__class__.__name__, "SomeJob")
        self.assertFalse(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)
        self.assertTrue(runtime.job.some_function_called)

    def test_job_arguments(self):
        runtime = CIJobRuntime(["some_function", "--thing"])
        self.assertEqual(runtime.file_name, "CIJob")
        self.assertEqual(runtime.job_name, "DefaultJob")
        self.assertEqual(runtime.job.parameters, ["--thing"])
        self.assertEqual(runtime.job.__class__.__name__, "DefaultJob")
        self.assertFalse(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)
        self.assertTrue(runtime.job.some_function_called)

    def test_file_name_job_arguments(self):
        runtime = CIJobRuntime(["CIJob2", "some_function", "--thing"])
        self.assertEqual(runtime.file_name, "CIJob2")
        self.assertEqual(runtime.job_name, "DefaultJob")
        self.assertEqual(runtime.job.parameters, ["--thing"])
        self.assertEqual(runtime.job.__class__.__name__, "DefaultJob")
        self.assertFalse(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)
        self.assertTrue(runtime.job.some_function_called)

    def test_file_name_and_job_name(self):
        runtime = CIJobRuntime(["CIJob2", "AnotherJob", "some_function"])
        self.assertEqual(runtime.file_name, "CIJob2")
        self.assertEqual(runtime.job_name, "AnotherJob")
        self.assertEqual(runtime.job.parameters, [])
        self.assertEqual(runtime.job.__class__.__name__, "AnotherJob")
        self.assertFalse(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)
        self.assertTrue(runtime.job.some_function_called)

    def test_job_name_job_arguments(self):
        runtime = CIJobRuntime(["SomeJob", "some_function", "--an",
                                "argument"])
        self.assertEqual(runtime.file_name, "CIJob")
        self.assertEqual(runtime.job_name, "SomeJob")
        self.assertEqual(runtime.job.parameters, ["--an", "argument"])
        self.assertEqual(runtime.job.__class__.__name__, "SomeJob")
        self.assertFalse(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)
        self.assertTrue(runtime.job.some_function_called)

    def test_file_name_job_name_job_arguments(self):
        runtime = CIJobRuntime(["CIJob2", "AnotherJob", "some_function",
                                "--an", "argument"])
        self.assertEqual(runtime.file_name, "CIJob2")
        self.assertEqual(runtime.job_name, "AnotherJob")
        self.assertEqual(runtime.job.parameters, ["--an", "argument"])
        self.assertEqual(runtime.job.__class__.__name__, "AnotherJob")
        self.assertFalse(runtime.job.run_called)
        self.assertTrue(runtime.job.setup_called)
        self.assertTrue(runtime.job.some_function_called)
