Linaro Runtime
==============

This project is intended to provide a comprehensive API for the automation of
tasks performed in a shell. The initial target is Bash and the intended use is
writing CI jobs. That said, the API is useful for more than just testing and
can already deploy a [linaro-license-protection][1] server.

Jobs are written as Python scripts, calling commands in a persistent shell on
either a local or a remote machine - you won't have any surprises because of
vanishing environment variables.

By example... build a kernel
-------------------------------

Below is part of the included kernel build job. The whole file is included in
this source as kernel-ci.py. I will run through it in some detail. First
though, how do you run it?

    lci-run kernel-ci KernelBuild_linux_origen_exynos4\
     <IP address/name of slave machine>\
     --username ubuntu\
     --publish-to <IP address/name of publishing server>\
     --key <publishing key>

The lci-run executable takes a file to execute the job from, the job name and
then a list of parameters that are passed to the job. These first two
parameters are optional and default to CIJob.py for the file name and
DefaultJob for the job name. You can exclude one or both - lci-run is smart
enough to work out what is missing.

In this example we have specified both the file name (kernel-ci.py) and the
job name (KernelBuild_linux_origen_exynos4).

lci-run always runs the member function called setup first, then the member
function called run. In this example run then calls a sequence of other
functions. If we wanted we could just run a single member function (after
setup) by specifying it on the command line after the class name:

    lci-run kernel-ci KernelBuild_linux_origen_exynos4 checkout ...

This would just run setup and then checkout.

Here is the partial source to the kernel build job:

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

None of the above should be particularly surprising. Below though we have
install_deps being called. This currently will use dpkg and apt to work out
which, if any, packages need to be installed on the system and install
them. In the future it could easily be updated to use other package managers.

        def install_os_prerequisites(self):
            self.x86_64.install_deps(
                ["curl", "bzr", "gcc", "git", "u-boot-tools", "build-essential",
                 "ia32-libs", "python-html2text", "python-beautifulsoup",
                 "python-xdgapp"])

In the following we have a call to "use". The intention is that this
replaces the download binary, unpack, put in known location recipe that is
often repeated in CI jobs. It knows (or should know) where commonly used
software lives and takes care of these steps in a more readable way.

        def prepare_environment(self):
            # -- Set up required directories and get dependencies
            self.x86_64.mkdir(self.output_dir)
            self.x86_64.in_directory(self.base_directory)
            self.x86_64.use("linaro-gnu-toolchain", ["2012.10", "v4.7"])

In checkout we call... checkout. This wraps up git, bzr and repo so we
have a common interface. It also tries to update existing checkouts
instead of deleting and re-downloading them to save time and bandwidth.

        def checkout(self):
            """Fetch kernel source"""
            self.x86_64.in_directory(self.base_directory)
            self.source = self.x86_64.checkout("git",
                                               self.config["git url"],
                                               depth=1,
                                               branch="linux-linaro-core-tracking")

        ...

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

The parameters that weren't used by lci-run to find this job are passed to
it to enable the jobs to take command line parameters.

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

Here we take a generic kernel build job and add a target specific
configuration and also show how, in the future, we could take the image
we have built, boot it on appropriate hardware and then take control of
that machine. At the moment only the x86 target is supported and lci-run
expects that machine to be running a Debian based linux distro.

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
...
    
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

Not all of the API is used above. A complete list of functions that CI Slaves can run is below.

##### append_to_file(self, string, file_name)

##### boot(self)

##### build(self, target='make', build_command='make', jobs=1, cached=False, source_uid=None, env='', expect_response={})
Call a build command, such as "make"
Theory of wrapping builds is to make them more easily shared - if the
same source is used, the same output will be produced, so if we
publish a build, this command should be able to skip a lengthy make
step with a shorter download. (TODO)
 * build_command: Command to run
 * target: target to pass to build command
 * jobs: How many CPUs wide to run the make job
 * cached: If we have already run this build on this source, use
           cached result if available.
 * source_uid: UID of source checkout (for example VCS URL+rev)
 * env: environment string for command (?? do we need this or just make
        it part of build command??)

##### chdir(self, directory)

##### checkout(self, vcs_type, url, branch=None, filename=None, depth=None, name='')
Check out from VCS. Update if checkout already exists.
Check out from the given URL. If a directory with the same name
as the target already exists, try to update it instead. Before
updating we check that the directory really is a checkout of the
same repository. This seems to work apart from Bazaar branches where
the repo URL is translated on-server.

##### copy(self, source, dest, sudo=False)

##### cwd(self)

##### disconnect(self)

##### in_directory(self, directory, sudo=False)

##### install_deps(self, packages)
Generic interface to the system package manager.
Currently only understands Debian based systems. Should be simple to
add other package managers and some detection code.

##### isdir(self, path)

##### ls(self, target='', sudo=False)

##### mkdir(self, directory, sudo=False)

##### move(self, source, dest, sudo=False)

##### publish(self, base_dir, glob_list, destination, license_name)

##### publish_file(self, local_path, remote_path, server_config)
Publish a file from the current slave to the specified server

##### put_file(self, local_path, remote_path)

##### rm(self, path)

##### set_disk_image(self, image)

##### set_env(self, name, value)

##### use(self, name, tags)
Use the output of another job as an input to this job
TODO: Currently this is quite the hack and it should use a database
rather than fixed paths. Suggest JSON in a known web accessible
location. Should also support user supplied data.

##### write_file(self, path, contents)

  [1]: https://launchpad.net/linaro-license-protection
