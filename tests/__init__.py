import os
import unittest
import subprocess


def test_suite():
    module_names = [
        'tests.ci_slave',
        'tests.cli_processing',
        'tests.screen_and_shell',
        'tests.job_commands',
    ]
    # if pyflakes is installed and we're running from a bzr checkout...
    if(subprocess.call('which pyflakes', shell=True) and
       not os.path.isabs(__file__)):
        # ...also run the pyflakes tests
        module_names.append('linaro_image_tools.tests.test_pyflakes')
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(module_names)
    return suite
