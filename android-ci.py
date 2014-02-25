#!/usr/bin/python

# Copyright 2013 Linaro Ltd.  This software is licensed under the
# GNU General Public License version 3 (see the file COPYING).


from commands.commands import *
import os


class AndroidBuild(LinaroCIJob):
    """Build android"""

    def __init__(self):
        self.set_triggers(["daily 22:00", "on merge request"])

    def run(self, config):
        cpus = 4

        self.x86_64 = x86_64(
            ["machine type x86_64",
             "memory 8GB",
             "cpus %d" % (cpus),
             "OS Ubuntu 12.04"]
        )

        self.x86_64.chdir("dev")
        self.x86_64.in_directory("android")
        base_directory = self.x86_64.cwd()

        self.x86_64.install_deps(["repo", "gcc", "git"])
        self.source = self.x86_64.checkout("repo",
                                           config["check out"]["repo"],
                                           config["check out"]["branch"],
                                           config["check out"]["file name"])

        # If any of the above commands fails (return code != 0), we throw an
        # exception, which will terminate execution, though you could catch it
        # if you wanted to try something else.

        # Use the software bundle GCC, identified by tags
        self.x86_64.use("android-toolchain", config["toolchain tags"])

        toolchain_dir = os.path.join(base_directory,
                                     "android-toolchain-eabi/bin/"
                                     "arm-linux-androideabi-")
        # Run the build
        # This fails because of
        # https://bugs.launchpad.net/linaro-android/+bug/1013114
        # and, well, I can't be bothered to patch it up as we develop the API.
        # Close enough.
        self.android_build = self.x86_64.build(
            # Until self.x86_64.build is refined and correctly implemented,
            # just specify the full command
            build_command="make"
            " -j4 "
            "TARGET_PRODUCT=%s TARGET_SIMULATOR=false " % (config["target"]) +
            "TARGET_TOOLS_PREFIX=" + toolchain_dir +
            " boottarball systemtarball userdatatarball showcommands",
            jobs=cpus, target=config["target"],
            # If this code has been checked out and built before, use cached
            # build
            cached=True,
            # UID to work out if this has already been built
            source_uid=self.source.uid)


class AndroidBuildBootSnowball(AndroidBuild):
    """Use standard Android build, boot it on snowball"""

    def run(self):
        config = {
            "check out": {
                "repo": "git://android.git.linaro.org/platform/manifest.git",
                "branch": "linaro_android_4.0.4",
                "file name": "tracking-snowball.xml"
            },

            "toolchain tags": ["eabi-4.7", "daily", "linux", "x86"],

            "target": "snowball"
        }
        super(AndroidBuildBootSnowball, self).run(config)

        self.snowball = Snowball()
        self.snowball.set_disk_image(self.android_build)

        # Maybe specify how we know it has booted here? Some serial output?
        self.snowball.boot()
        self.snowball.disconnect()

    def post_process(self):
        """Do magic here to post-process snowball.logs"""

    def exit_status(self):
        return "pass"


class AndroidBuildBootAll(AndroidBuild):
    """Use standard Android build, boot it on snowball"""

    def run(self):
        self.slaves = []
        for board in self.filter_slaves("AArch32"):
            parent.run(board)

            slave = CISlave(board)
            slave.set_disk_image(self.android_build)
            slave.boot()

            self.slaves.append(slave)

            slave.disconnect()  # Need to disconnect to free board up. Keeping
                                # reference to board to process logs.

    def post_process(self):
        """Do magic here to post-process board.logs"""

        for slave in self.slaves:
            # self.output_data will be presented in results page
            # All keys in hash used as titles
            self.output_data["2. Logs"] = {}
            logs = self.output_data["2. Logs"]
            logs[slave.name] = slave.log

            # If you want to specify an alternate format appropriate for your
            # data, you can...
            self.output_data["1. Summary"] = {
                "data": {},
                "type": "table"
            }
            summary = self.output_data["1. Summary"]

            # TODO some magic to work out if compile and boot happened OK
            summary[slave.name]["compile"] = compile_ok
            summary[slave.name]["compile"] = boot_ok
