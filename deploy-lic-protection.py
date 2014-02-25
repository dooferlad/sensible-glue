#!/usr/bin/python

from commands.commands import *
import os
import socket
from tempfile import mkdtemp
from subprocess import call
import shutil
import inspect
import argparse


class DeployLicenseProtection(LinaroCIJob):

    def __init__(self):
        self.set_triggers(["daily 22:00", "on merge request"])

    def run(self):
        config = self.config
        srv_path = os.path.join("/srv", config["service"]["url"])
        self.x86_64 = x86_64(config["target machine"])

        target = self.x86_64

        target.install_deps(["bzr",
                             "apache2",
                             "python-django",
                             "libapache2-mod-python",
                             "libapache2-mod-xsendfile",
                             "python-django-openid-auth",
                             "libapache2-mod-wsgi",
                             "python-beautifulsoup",
                             "python-requests",
                             "python-textile"])

        target.in_directory(srv_path, sudo=True)
        target.cmd("chmod a+rx %s" % (srv_path),
                   "Make %s usable by non-root" % (srv_path), sudo=True)
        target.cmd("chmod ug+w %s" % (srv_path),
                   "Make %s usable by non-root" % (srv_path), sudo=True)

        target.cmd("chown -R www-data.www-data %s" % (srv_path),
                   "Give ownership of %s to www-data." % (srv_path), sudo=True)

        target.checkout("bzr", "lp:linaro-license-protection")
        target.checkout("bzr", "lp:linaro-license-protection/configs",
                        name="configs")

        target.cmd("a2enmod xsendfile",
                   "Make sure the Apache xsendfile module is enabled",
                   sudo=True)
        target.cmd("a2enmod python",
                   "Make sure the Apache xsendfile module is enabled",
                   sudo=True)

        target.cmd("cp %s/configs/apache/%s /etc/apache2/sites-available" %
                   (srv_path, config["service"]["url"]),
                   "Copy Apache2 config from configuration branch to etc.",
                   sudo=True)

        target.cmd("cp -r %s/configs/apache/security /etc/apache2/"
                   % (srv_path), "Copy Apache security settings.",
                   sudo=True)

        target.cmd("a2ensite %s" % config["service"]["url"],
                   "Enable %s" % config["service"]["url"], sudo=True)

        # TODO: SSL certificate required...

        python_path = "{0}:{0}/linaro-license-protection:" \
                      "{0}/configs/django".format(srv_path)
        target.cmd("export PYTHONPATH=%s" % python_path,
                   "Set PYTHONPATH to %s" % python_path)
        target.cmd("export DJANGO_SETTINGS_MODULE=%s" %
                   config["service"]["django settings module"],
                   "Set Django settings module")

        target.mkdir(os.path.join(srv_path, "db"))
        target.mkdir(os.path.join(srv_path, "www"))
        target.chdir(srv_path)

        # Create local_settings with random SECRET_KEY and MASTER_API_KEY
        secret_char_selection = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFG' \
                                'HIJKLMNOPQRSTUVWXYZ'
        secret_key = ''.join(random.sample(secret_char_selection, 30))
        local_settings = "SECRET_KEY = '%s'\n" % secret_key
        master_api_key = ''.join(random.sample(secret_char_selection, 30))
        local_settings += "MASTER_API_KEY = '%s'\n" % master_api_key
        target.write_file(os.path.join(srv_path,
                                       "configs/django/local_settings.py"),
                          local_settings)

        target.cmd("django-admin syncdb --noinput", "Set up Django database")
        target.cmd("django-admin collectstatic --noinput",
                   "Set up Django static files")

        android_build_ip = socket.gethostbyname("android-build.linaro.org")
        validation_ip = socket.gethostbyname("validation.linaro.org")

        temp_dir = mkdtemp()
        os.chdir(temp_dir)
        call("bzr branch --quiet lp:linaro-license-protection", shell=True)

        new_config = []
        with open(os.path.join(temp_dir,
                               "linaro-license-protection",
                               "license_protected_downloads",
                               "config.py")) as f:
            for line in f.readlines():
                if re.search("# android-build.linaro.org", line):
                    new_config.append(
                        "    '%s',  # android-build.linaro.org" %
                        android_build_ip)
                elif re.search("# validation.linaro.org", line):
                    new_config.append("    '%s',  # validation.linaro.org" %
                                      validation_ip)
                else:
                    new_config.append(line.rstrip())
        shutil.rmtree(temp_dir)

        target.write_file(os.path.join(srv_path,
                                       "linaro-license-protection",
                                       "license_protected_downloads",
                                       "config.py"), "\n".join(new_config))

        # In order to make this work we need to disable the default apache2
        # site and make ours respond to *:80 (or the correct site IP address).
        # For now we just update the config to be for *:80.
        out = target.cmd("apache2ctl -S", "list active virtual servers")
        for line in out:
            if re.search("sites-enabled/000-default", line):
                target.cmd("a2dissite 000-default",
                           "Disable default apache site",
                           sudo=True)

        # Now to update the config. We have a script to do this locally. Push
        # it to the server then run it as root.
        script_dir = os.path.dirname(
            os.path.abspath(
                inspect.getfile(inspect.currentframe())))
        mod_script = "set_apache_ip_address.py"

        target.put_file(os.path.join(script_dir, mod_script),
                        os.path.join(srv_path, mod_script))

        target.cmd("python %s /etc/apache2/sites-available/%s" %
                   (os.path.join(srv_path, mod_script),
                    config["service"]["url"]),
                   "Modify apache configuration to make port 80 respond with"
                   "linaro-license-protection", sudo=True)

        # Everything is ready. Provided /srv/$url/www exists we will now
        # serve files from it.
        target.cmd("service apache2 restart",
                   "Activate new Apache 2 configuration.", sudo=True)

    def _command_line_args(self, parameters):
        parser = argparse.ArgumentParser(
            description="Deploy linaro-license-protection to a server. "
            "Target server should already be running an SSH server with key"
            "based login working for the user. User needs sudo access.")

        parser.add_argument(
            "host",
            help="The host name or IP address of the machine to deploy to.")
        parser.add_argument(
            "--username",
            help="User name of user to SSH as. We expect a key based login.")

        args = parser.parse_args(parameters)

        return args


class Releases(DeployLicenseProtection):
    """Deploy a linaro-license-protection server"""
    def configure(self, parameters):
        args = self._command_line_args(parameters)

        self.config = {
            "target machine": {
                "reserved": {
                    "hostname": args.host,
                    "username": args.username,
                }
            },
            "service": {
                "url": "releases.linaro.org",
                "django settings module": "settings_releases",
            },
        }


class Snapshots(DeployLicenseProtection):
    """Deploy a linaro-license-protection server"""
    def configure(self, parameters):
        args = self._command_line_args(parameters)

        self.config = {
            "target machine": {
                "reserved": {
                    "hostname": args.host,
                    "username": args.username,
                }
            },
            "service": {
                "url": "snapshots.linaro.org",
                "django settings module": "settings_snapshots",
            },
        }
