#!/usr/bin/python

# Copyright 2013 Linaro Ltd.  This software is licensed under the
# GNU General Public License version 3 (see the file COPYING).
import json
import urllib2
import xmlrpclib
import os
import argparse
import re
import urlparse

from commands.commands import *


def get_latest_lava_nano_image_url():
    url = "http://snapshots.linaro.org/api/ls/raring/images/nano-lava/latest"
    url_parts = list(urlparse.urlsplit(url))
    data = json.load(urllib2.urlopen(url))
    for file_info in data["files"]:
        if re.search(r"linaro-\w+-nano-lava-\d+-\d+.tar.gz",
                     file_info["name"]):
            url_parts[2] = file_info["url"]
            return urlparse.urlunsplit(url_parts)


class KernelBuild(LinaroCIJob):
    """Build a Linux kernel"""

    def __init__(self):
        self.config = {}

    def setup(self):
        """Setup step called before run"""

        # Get a slave machine to run the build on
        self.x86_64 = x86_64(self.config["target machine"])

        # Find the number of CPUs the target machine has
        self.cpus = int(self.x86_64.cmd("nproc",
                                        "Find number of CPUs on system.")[0])

        # Create the working directory (if needed) and change into it
        self.x86_64.in_directory(self.config["working directory"])

        # Record the full path to this directory
        self.base_directory = self.x86_64.cwd()

        # output_dir used to contain kernel version - excluded for this demo
        self.output_dir = os.path.join(self.base_directory, "output_dir")
        self.builddeb_orig_name = None

        # If there is exactly 1 hardware pack and
        # self.config["hwpack_file_path"] isn't set, fill it in.
        if not self.config["hwpack_file_path"]:
            hwpacks = self.x86_64.ls("hwpack*.gz")
            if len(hwpacks) == 1:
                self.config["hwpack_file_path"] = hwpacks[0]

    def install_os_prerequisites(self):
        self.x86_64.install_deps(
            ["curl", "bzr", "gcc", "git", "u-boot-tools", "build-essential",
             "ia32-libs", "python-html2text", "python-beautifulsoup",
             "python-xdgapp"])

    def prepare_environment(self):
        # -- Set up required directories and get dependencies
        self.x86_64.mkdir(self.output_dir)
        self.x86_64.in_directory(self.base_directory)
        self.x86_64.use("linaro-gnu-toolchain", ["2012.10", "v4.7"])

    def checkout(self):
        """Fetch kernel source"""
        self.x86_64.in_directory(self.base_directory)
        self.source = self.x86_64.checkout("git",
                                           self.config["git url"],
                                           depth=1,
                                           branch="linux-linaro-core-tracking")

        # For kernels that aren't from the linux-linaro-tracking repository
        # the make deb-pkg stage will fail unless we use an updated builddeb
        # script. We copy our own over:
        if not re.search("linux-linaro-tracking", self.config["git url"]):
            self.source = self.x86_64.checkout(
                "bzr", "lp:~linaro-infrastructure/linaro-ci/lci-build-tools")
            self.builddeb_path = "linux/scripts/package/builddeb"
            self.builddeb_orig_name = self.builddeb_path + ".orig_kernel_ci"
            self.x86_64.move(self.builddeb_path, self.builddeb_orig_name)
            self.x86_64.copy("lci-build-tools/build-scripts/builddeb",
                             self.builddeb_path)

    def clean(self):
        self.x86_64.chdir(os.path.join(self.base_directory,
                                       "linux-linaro-tracking"))

        # XXX This clean doesn't specify the output directory. Should it?
        # Do we need it after a clean checkout?
        self.x86_64.build("make", build_command="make ARCH=arm clean mrproper")

    def _setup_build(self):
        self.x86_64.chdir(os.path.join(self.base_directory,
                                       "linux-linaro-tracking"))

        self.kernel_config_name = re.sub("_defconfig", "",
                                         self.config["env"]["kernel_config"])

        # -- Create kernel version string
        try:
            self.kernel_version = self.x86_64.cmd("make kernelversion",
                                                  "find kernel version")[0]
        except CommandFailed:
            # Couldn't find a kernel version, try for latest tag
            self.kernel_version = self.x86_64.cmd("git describe --match='v*'",
                                                  "find kernel version")[0]
            self.kernel_version = re.sub("^v", "", self.kernel_version)
            self.kernel_version = "-".join([self.kernel_version,
                                       self.config["env"]["kernel id"],
                                       self.kernel_config_name,
                                       self.config["env"]["kernel_flavour"]])

    def build(self):
        self._setup_build()
        self.x86_64.chdir(os.path.join(self.base_directory,
                                       "linux-linaro-tracking"))
        self.toolchain_prefix = os.path.join(
            self.base_directory, "toolchain/bin/arm-linux-gnueabihf-")

        # hack hack hack LOADADDR below is a nasty hack
        make = ('LOADADDR=0x80008000 make -j%(cpus)d ARCH=arm O=%(out_dir)s '
                'KERNELVERSION="%(k_ver)s" '
                'KERNELRELEASE="%(k_ver)s" '
                'CROSS_COMPILE="%(t_prefix)s" '
                % {"out_dir": self.output_dir,
                   "k_ver": self.kernel_version,
                   "t_prefix": self.toolchain_prefix,
                   "cpus": self.cpus})

        self.x86_64.build("make",
                          make + " " + self.config["env"]["kernel_config"])

        # -- Update configuration
        k_config = "%s/.config" % (self.output_dir)
        self.x86_64.append_to_file("CONFIG_ARCH_OMAP2=n", k_config)
        self.x86_64.append_to_file("CONFIG_THUMB2_KERNEL=y", k_config)

        # -- Build
        self.x86_64.build("make", "yes "" | " + make + " oldconfig")

        multi_platform_check = self.x86_64.cmd(
            "grep 'CONFIG_ARCH_MULTIPLATFORM=y' %s" % os.path.join(
                self.output_dir, ".config"),
            "Check to see if CONFIG_ARCH_MULTIPLATFORM is set")

        if len(multi_platform_check):
            kernel_img_cmd = "zImage"
        else:
            kernel_img_cmd = "uImage"

        self.x86_64.build("make", make + " %s" % kernel_img_cmd)

        self.x86_64.build("make", make + " modules")

        if("make dtbs" in self.config["env"] and
           self.config["env"]["make dtbs"]):
            self.x86_64.build("make", make + " dtbs")

        self.x86_64.build("make", make + " KBUILD_DEBARCH=armhf V=1 deb-pkg")

    def hwpack_replace(self):
        self._setup_build()
        self.x86_64.in_directory(self.base_directory)
        self.x86_64.checkout("bzr", "lp:linaro-ci", name="lci-build-tools")

        self.x86_64.set_env("hwpack_type", self.config["env"]["hwpack_type"])

        hwpack_url = self.x86_64.cmd(
            "lci-build-tools/get_latest_slo_hwpack",
            "get the URL of the latest hardware pack for the target board")[0]

        self.x86_64.cmd("lci-build-tools/download_file " + hwpack_url,
                        "download the hardware pack")

        hwpack_file_name = os.path.basename(hwpack_url)

        self.x86_64.checkout("bzr", "lp:linaro-image-tools")
        new_hwpack_name = self.x86_64.cmd(
            "linaro-image-tools/linaro-hwpack-replace"
            " -t {hwpack_file_name}"
            " -p ./linux-image*{kernel_version}*.deb"
            " -r linux-image"
            " -n {build_number}".format(
            hwpack_file_name=hwpack_file_name,
            kernel_version=self.kernel_version,
            build_number=self.config["env"]["build_number"]),
            "Replace the kernel in the hardware pack with"
            " the one we have just built.")

        self.x86_64.rm(hwpack_file_name)
        self.config["hwpack_file_path"] = new_hwpack_name[1]

    def tidy_up(self):
        """Tidy up after build"""
        self.x86_64.in_directory(self.base_directory)

        if self.builddeb_orig_name:
            self.x86_64.move(self.builddeb_orig_name, self.builddeb_path)

    def publish(self):
        """Push files up to specified server, run listed commands."""
        self.x86_64.in_directory(self.base_directory)

        for to_path, file_globs in self.config["publish files"].iteritems():
            for filename_glob in file_globs:
                filenames = self.x86_64.ls(filename_glob)
                for filename in filenames:
                    # Keep a record of where we uploaded the hwpack to
                    if filename == self.config["hwpack_file_path"]:
                        self.config["hwpack_file_path"] = os.path.join(
                            to_path.format(**self.config["env"]),
                            filename)
                    self.x86_64.publish_file(
                        filename,
                        os.path.join(to_path.format(**self.config["env"]),
                                     filename),
                        self.config["publish to"],
                    )

    def submit_lava_job(self):
        hwpack = "{host}/{path}?key={key}".format(
            host=self.config["publish to"]["hostname"],
            path=self.config["hwpack_file_path"],
            key=self.config["publish to"]["key"],
        )

        if not hwpack.startswith("http"):
            # Bit nasty - won't detect non-http stuff, but can add support
            # if LAVA has it later.
            hwpack = "http://" + hwpack

        actions = [
            {
                "command": "deploy_linaro_image",
                "parameters": {
                    "hwpack": hwpack,
                    "rootfs": self.config["env"]["os image"]
                },
                "metadata": {
                    "distribution": "ubuntu",
                    "hwpack.build": "57",
                    "rootfs.build": "393",
                    "hwpack.type": "panda",
                    "rootfs.type": "nano-lava"
                }
            },
            {
                "command": "boot_linaro_image"
            },
            {
                "command": "lava_test_shell",
                "parameters": {
                    "testdef_repos": [
                        {
                            "git-repo":
                            "git://git.linaro.org/qa/test-definitions.git",
                            "testdef": "ubuntu/device-tree.yaml"
                        },
                        {
                            "git-repo":
                            "git://git.linaro.org/qa/test-definitions.git",
                            "testdef": "ubuntu/gatortests.yaml"
                        },
                        {
                            "git-repo":
                            "git://git.linaro.org/qa/test-definitions.git",
                            "testdef": "ubuntu/perf.yaml"
                        },
                        {
                            "git-repo":
                            "git://git.linaro.org/qa/test-definitions.git",
                            "testdef": "ubuntu/pwrmgmt.yaml"
                        }
                    ],
                    "timeout": 18000
                }
            },
            # {
            #     "command": "submit_results",
            #     "parameters": {
            #         "stream":
            #           "/private/team/linaro/ci-linux-linaro-tracking-llct/",
            #         "server":
            #           "http://validation.linaro.org/lava-server/RPC2/"
            #     }
            # }
        ]
        config = json.dumps(
            {
                'timeout': 18000,
                'actions': actions,
                'job_name': "CI Runtime job",
                'device_type': self.config["env"]["board_type"],
            },
            indent=2
        )

        print "\n" + config + "\n"

        try:
            server_url = '://{lava_user}:{lava_token}@{lava_server}'.format(
                **self.config["env"])

            if self.config["env"].get("lava_https") is False:
                server_url = "http" + server_url
            else:
                server_url = "https" + server_url

            server = xmlrpclib.ServerProxy(server_url)
            lava_job_id = server.scheduler.submit_job(config)
        except xmlrpclib.ProtocolError, e:
            print 'Error making a LAVA request:', str(e)
            sys.exit(1)

    def run(self):
        self.install_os_prerequisites()
        self.prepare_environment()
        self.checkout()
        self.clean()
        self.build()
        self.hwpack_replace()
        self.tidy_up()
        self.publish()
        self.submit_lava_job()

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
        parser.add_argument(
            "--publish-to",
            help="Address of server to publish to.")
        parser.add_argument(
            "--key",
            help="API key for publishing server.")
        parser.add_argument(
            "--hwpack-file-path",
            help="File name/path of hardware pack. "
                 "If you don't run hwpack_replace but do run submit_lava_job "
                 "this is required to be a full path on the publishing "
                 "server. If you run the publish and submit_lava_job just "
                 "provide the file name")

        return parser.parse_args(parameters)


class KernelBuild_linux_origen_exynos4(KernelBuild):
    """Standard Kernel build, boot it on an Origen"""
    def configure(self, parameters):
        self.set_triggers(["daily 22:00", "on merge request"])
        args = self._command_line_args(parameters)

        self.config = {
            "target machine": {
                "reserved": {
                    "hostname": args.host,
                    "username": args.username,
                }
            },
            "publish to": {
                "hostname": args.publish_to,
                "key": args.key,
            },
            "publish files": {
                "kernel-hwpack/{job_name}/{build_number}":
                ["hwpack*.tar.gz", "*.txt"]
            },
            "run on publishing target": [
                " ".join(
                    "reshuffle-files"
                    "-t kernel-hwpack"
                    "-j {job_name}"
                    "-n {build_number}"
                ),
            ],
            "env": {
                "hwpack_type": "origen",
                "board_type": "origen",
                "kernel_flavour": "origen",
                "kernel_config": "exynos4_defconfig",
                "kernel id": "linaro",
                "job_name": "linux-pm-qa_origen-exynos4",
                "build_number": 1,  # TODO: Get from CLI

                "lava_token":
                "el0lj3ns5thwra9rx4d0iwsdeegkwngdpny1rsjfxpxk5qt67efh8qwsy100"
                "xry9xax361u0suww7n8uo8nuhtapuj97o6nqin0g55h0jupda7egd1oupxjd"
                "20kh0nan",

                "lava_user": "dooferlad",
                "lava_server": "lavaserver/RPC2/",
                "lava_https": False,
                "os image": get_latest_lava_nano_image_url(),
            },
            "git url":
            "git://git.linaro.org/kernel/linux-linaro-tracking.git",

            "hwpack_file_path": args.hwpack_file_path,
            "working directory": "~/_not_backed_up_/ci-runtime/kernel",
        }

    def run(self):
        super(KernelBuild_linux_origen_exynos4, self).run()

        self.origen = Origen()
        self.origen.set_disk_image(None)  # Clearly None is a placeholder...

        # Maybe specify how we know it has booted here? Some serial output?
        self.origen.boot()
        self.origen.disconnect()

    def post_process(self):
        """Do magic here to post-process snowball.logs"""

    def exit_status(self):
        return "pass"


class KernelBuild_linux_panda(KernelBuild):
    """Standard Kernel build, boot it on an Panda"""

    def configure(self, parameters):
        self.set_triggers(["daily 22:00", "on merge request"])
        args = self._command_line_args(parameters)

        self.config = {
            "target machine": {
                "reserved": {
                    "hostname": args.host,
                    "username": args.username,
                }
            },
            "publish to": {
                "hostname": args.publish_to,
                "key": args.key,
            },
            "publish files": {
                "kernel-hwpack/{job_name}/{build_number}":
                ["hwpack*.tar.gz", "*.txt"]
            },
            "run on publishing target": [
                " ".join(
                    "reshuffle-files -t kernel-hwpack"
                    "-j {job_name}"
                    "-n {build_number}"
                ),
            ],
            "env": {
                "hwpack_type": "panda",
                "board_type": "panda",
                "kernel_flavour": "panda",
                "kernel_config": "omap2plus_defconfig",
                "conf_filenames": ["linaro/configs/linaro-base.conf",
                                   "linaro/configs/distribution.conf",
                                   "linaro/configs/omap4.conf"],
                "kernel id": "linaro",
                "job_name": "linux-pm-qa_panda-omap",
                "build_number": 1,  # TODO: Get from CLI

                "lava_token":
                "el0lj3ns5thwra9rx4d0iwsdeegkwngdpny1rsjfxpxk5qt67efh8qwsy100"
                "xry9xax361u0suww7n8uo8nuhtapuj97o6nqin0g55h0jupda7egd1oupxjd"
                "20kh0nan",

                "lava_user": "dooferlad",
                "lava_server": "lavaserver/RPC2/",
                "lava_https": False,
                "os image": get_latest_lava_nano_image_url(),
            },
            "git url":
            "git://git.linaro.org/kernel/linux-linaro-tracking.git",
            "hwpack_file_path": args.hwpack_file_path,
             "working directory": "~/_not_backed_up_/ci-runtime/kernel",
        }

    def run(self):
        super(KernelBuild_linux_panda, self).run()

        self.panda = Panda()
        self.panda.set_disk_image(None)  # Clearly None is a placeholder...

        # Maybe specify how we know it has booted here? Some serial output?
        self.panda.boot()
        self.panda.disconnect()

    def post_process(self):
        """Do magic here to post-process snowball.logs"""

    def exit_status(self):
        return "pass"
