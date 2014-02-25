# Copyright 2013 Linaro Ltd.  This software is licensed under the
# GNU General Public License version 3 (see the file COPYING).

import logging
import sys
import paramiko
import time
import re
import getpass
import socket
import pexpect
import os
import random
import string
import atexit
import importlib
import telnetlib


class Checkout():
    """Placeholder. In the future this may be used to store information about
    checkouts.
    """
    uid = 0


class CommandFailed(Exception):
    """Exception: A command run on a slave device failed"""
    def __init__(self, cmd, return_code, command_output):
        self.return_code = return_code
        self.command_output = command_output
        self.cmd = cmd

    def __str__(self):
        return repr(self.cmd + "\n" +
                    self.return_code + "\n" +
                    "\n".join(self.command_output))


class BashShell(object):
    """Base class to encapsulate interacting with a bash shell
    """
    def __init__(self, prompt):
        self.set_prompt(prompt)

    def set_prompt(self, prompt, no_eol=False):
        # Process the prompt to generate a regexp to match it. Currently the
        # only escape sequence we can match is \#, which translates to the
        # current command number.

        self.prompt = prompt
        if re.search(r"\\#", prompt):
            self.cmd_count = -1
            prompt_re = re.sub(r"\\#", "(\d+)", prompt)
        else:
            self.cmd_count = None
            prompt_re = prompt

        self.prompt_match_no_line_start = re.compile(prompt_re)

        if not no_eol:
            # Most of the time we want to see a prompt on a line by itself, but
            # for interacting with some processes, with a countdown, we want
            # to just match the beginning of the line.
            prompt_re += "\s*$"

        prompt_re = "^" + prompt_re
        self.prompt_match = re.compile(prompt_re)
        self.match_prompt_last_line = None

    def match_prompt(self, rx):
        if not rx:
            # Early exit on empty strings
            return False

        if rx == self.match_prompt_last_line:
            # Early exit if we have already tested this line
            return
        self.match_prompt_last_line = rx

        # If we have set the prompt to something with a command counter in
        # it (recommended for SSH so screen re-connections don't pick up old
        # prompts), we only return True if we have found a new command prompt.
        # For prompts without the counter, we just return true if we match
        # the fixed string.
        search = self.prompt_match.search(rx)
        if search:
            if self.cmd_count is not None:
                if int(search.group(1)) > int(self.cmd_count):
                    self.cmd_count = search.group(1)
                    return True
            else:
                return True

        search = self.prompt_match_no_line_start.search(rx)
        if search:
            # Found something prompt-like with possible garbage at the start
            # of the line. Send a sneeky newline.
            self.send("\n")

        return False

    def _set_up_shell(self):
        # Wait for terminal to settle. We set the prompt and wait for it to
        # be presented on a line with nothing after it, showing it has been
        # set.

        self._raw_send('TERM="vt100"\n')
        self.set_prompt(self.prompt)
        self._raw_send('PS1="%s"\n' % self.prompt)
        rx = ""
        while(1):
            try:
                rx += self._raw_recv(1000)
                lines = rx.splitlines()
                for line in lines:
                    if self.match_prompt(line):
                        return
                time.sleep(0.01)
            except socket.timeout:
                pass

    def _strip_excape_sequences(self, rx):
        # Process the recieved text and strip it of non-loggable text. This
        # logic handles both terminal colour codes as well as ANSI escape
        # codes as defined in
        # http://en.wikipedia.org/wiki/ANSI_escape_code#Sequence_elements.
        # It also strips most ASCII control codes, jut keeping tab and newline.
        # Note that carriage returns are just ignored because they need to be
        # handled when complete lines are available. Here we are just getting
        # string fragments, which may be part of a line or multiple lines.
        state = None
        out = ""

        rx = bytearray(rx)
        next_index = 0
        last_escape = None
        unwrap_state = None

        while next_index < len(rx):

            index = next_index
            next_index += 1
            c = rx[index]

            if c == 27:
                state = "escape_start"
                continue
            elif c == 155:  # Single character escape start
                state = "escape"

            if state == "escape_start":
                if c == 91:  # ^[ found
                    state = "escape"
                    continue

                elif c >= 64 and c <= 95:
                    state = None  # 2 char escape. Done.
                    continue

                else:
                    state = None

            elif state == "escape":
                if c >= 64 and c <= 126:
                    if last_escape == ord("C") and c == ord("A"):
                        if index >= 8:
                            seq = rx[index - 8:index]
                            if seq == bytearray(
                                    ["\n", 27, "[", "7", "9", "C", 27, "["]
                            ):
                                # This is the sequence for going back to the
                                # start of the line, then going up 1 line,
                                # after a newline (assuming the terminal is
                                # 80 chars wide).
                                # TODO: "tput cols" returns thw real width.
                                unwrap_state = "unwrap"

                    last_escape = c
                    state = None
                continue

            if c == 8 and len(out) and next_index < len(rx):
                # Handle backspace
                # Only delete a character that is really deleted. We see \b\n
                # as an equivalent for \r\n when there is only one character
                # on the line.
                if rx[next_index] != ord("\n"):
                    out = out[:-1]

            if c < 32 and c != 9 and c != 10:
                continue

            if unwrap_state == "unwrap":
                out = out[:-1]
                unwrap_state = None
                continue

            c = unichr(c)
            out += c

        return out

    def terminate(self):
        pass


class LocalShell(BashShell):
    """Execute commands on the local machine.

    Behaves in exactly the same way as SSHShell so scripts developed locally
    can be executed over SSH with the expectation that they will behave
    identically.
    """
    def __init__(self, prompt):
        super(LocalShell, self).__init__(prompt)
        self.proc = pexpect.spawn('/bin/bash -li')
        self._raw_send('TERM="vt100"\n')
        self._set_up_shell()

    def _raw_recv(self, size):
        try:
            return self.proc.read_nonblocking(size, timeout=0.1)
        except pexpect.TIMEOUT:
            raise socket.timeout
        except pexpect.EOF:
            raise socket.timeout

    def recv(self, size):
        return self._raw_recv(size)

    def _raw_send(self, value):
        return self.proc.sendline(value.rstrip())

    def send(self, value):
        self._raw_send(value)


class LocalFiles(object):
    pass


class SSHShell(BashShell):
    """Execute commands on a remote machine.

    Invoke Bash inside GNU Screen on a remote machine. If the connection drops,
    we do our best to detect this and reconnect to both the machine and the
    Screen session.
    """

    def __init__(self, config, prompt):
        super(SSHShell, self).__init__(prompt)
        self.config = config
        self.rnd_chars = string.ascii_uppercase + string.digits
        self._connect()
        atexit.register(self.terminate)

    def _start_ssh_shell_and_sftp(self):
        if "reserved" in self.config:
            config = self.config["reserved"]
            self.ssh.connect(config["hostname"], username=config["username"])
        else:
            # TODO: Exception rather than print & exit
            print "Machine request not implemented, please provide reserved."
            sys.exit(1)

        self.sftp = self.ssh.open_sftp()
        self.shell = self.ssh.invoke_shell()
        self.shell.setblocking(0)
        self.ssh_transport = self.ssh.get_transport()
        self.agent_chan = self.ssh_transport.open_session()

    def _connect(self):
        """Connect to remote machine"""
        self.screen_name = "ci-runtime"
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._start_ssh_shell_and_sftp()
        self._raw_send('TERM="vt100"\n')
        self.send("screen -qL -S %s bash\n" % self.screen_name)
        self._set_up_shell()

    def _raw_recv(self, size):
        return self.shell.recv(size)

    def recv(self, size):
        """Receive data (reconnect if connection has dropped)"""
        if not self.shell.transport.is_active():
            self._reconnect()

        rx = self._raw_recv(size)
        return self._strip_excape_sequences(rx)

    def _raw_send(self, value):
        return self.shell.send(value)

    def send(self, value):
        """Send data (reconnect if connection has dropped)"""
        self._reconnect_if_dropped()
        return self._raw_send(value)

    def _reconnect(self):
        retries = 0
        while retries < 100:
            retries += 1
            try:
                self._start_ssh_shell_and_sftp()
                self.shell.send("screen -r %s\n" % self.screen_name)
                return
            except socket.error as e:
                print "Unable to reconnect. Trying again in 15 seconds."
                print e
                time.sleep(15)

        logging.error("Unable to reconnect. Giving up and aborting job.")
        exit(1)

    def _recv_or_empty(self, size):
        try:
            return self.recv(size)
        except socket.timeout:
            return ""

    def _reconnect_if_dropped(self):
        if not self.shell.transport.is_active():
            self._reconnect()

        # Write something to the shell. Assume echo is on. Must not be a
        # command so it won't modify the return code of the previous command.
        rnd = ''.join(random.choice(self.rnd_chars) for x in range(30))
        message = "#ack %s\n" % rnd
        self.shell.send(message)

        rx = self._recv_or_empty(1000)
        tries = 0
        while not re.search(message, rx) and tries < 10:
            time.sleep(0.25)
            rx = self._recv_or_empty(1000)
            tries += 1

        if tries == 10:
            self._reconnect()

    def terminate(self):
        if self.shell:
            self.shell.send("exit\n")
            self.ssh.close()
            self.ssh = None
            self.shell = None


class TelnetShell(BashShell):
    """Execute commands on a remote machine."""

    def __init__(self, config, prompt, booted=False):
        super(TelnetShell, self).__init__(prompt)
        self.config = config
        self.rnd_chars = string.ascii_uppercase + string.digits
        self.booted = booted
        self._connect()
        atexit.register(self.terminate)

    def _connect(self):
        """Connect to remote machine"""
        self.screen_name = "ci-runtime"

        if "reserved" in self.config:
            config = self.config["reserved"]
            if "port" in config:
                port = config["port"]
            else:
                port = 23
            self.shell = telnetlib.Telnet(config["hostname"], port)
        else:
            # TODO: Exception rather than print & exit
            print "Machine request not implemented, please provide reserved."
            sys.exit(1)

        if self.booted:
            self._raw_send('TERM="vt100"\n')
            self._set_up_shell()

    def _raw_recv(self, size):
        return self.shell.read_eager()

    def recv(self, size):
        return self._raw_recv(size)

    def _raw_send(self, value):
        return self.shell.write(value)

    def send(self, value):
        self._raw_send(value)

    def terminate(self):
        if self.shell:
            self.send("exit\n")
            self.shell.close()
            self.shell = None

class CISlave(object):
    """Generic CI slave base class"""
    def __init__(self, tags=""):
        self.got_machine = False
        self.tags = tags
        self.shell = None
        self.sudo_password = None
        self.return_code_search = re.compile("(\d+)$")
        self.disk_image = None
        self.kernel = None
        # Have a few pre-defined classes

    def _test_return_code(self, cmd, command_output):
        """Check return code of previous command"""
        rx = self._in_shell_cmd("echo $?\n", quiet=True)

        return_code = None
        for line in rx:
            return_code_search = self.return_code_search.search(line)
            if return_code_search:
                return_code = return_code_search.group(1)

        if return_code != "0":
            raise CommandFailed(cmd, return_code, command_output)

    def _terminate_unresponsive_commands(self, line):
        """Send Ctrl-C if command looks like it has hung"""
        if re.search("^fatal: The remote end hung up unexpectedly$", line):
            self.shell.send(chr(3))  # Send "ctrl-c"
            return True

    def _in_shell_cmd(self, cmd, quiet=False, sudo=False,
                      expect_response={}):
        """Run command in shell. Handles sudo with and without password

        The specified command is run, with optional pre-defined interaction,
        and the output of the command is returned. If expect_response is
        specified, the output of the command is monitored for a line that
        matches a given regular expression (key) and the mapped text (value)
        is sent.

        cmd             -- The command to run
        quiet           -- If True, don't log command output
        sudo            -- run command as root using sudo
        expect_response -- dict of {<regexp>: <text to send>}
        """

        if sudo:
            # Test to see if we need a password for sudo. We do this by
            # forcing non-interactive mode for sudo. In this case, if a
            # password is required an error is raised rather than a password
            # prompt being given.
            cmd = "sudo " + cmd

            if self.sudo_password is None:
                self._in_shell_cmd("sudo -n ls")

                try:
                    self._test_return_code("", "")
                    self.sudo_password = ""
                except CommandFailed:
                    if not self.sudo_password:
                        self.sudo_password = getpass.getpass(
                            "Please enter sudo password: ")

        sent_sudo_password = False
        sleep_seconds_reset = 0.0001
        send_newline_timeout = 200
        got_chunk_time = time.time()
        sleep_seconds = sleep_seconds_reset

        if cmd is not None:
            self.shell.send(cmd + "\n")
            time.sleep(sleep_seconds)

        self.lines = []

        saved_chunk = ""
        self.lines = []
        rx = ""

        expect_responses = [
            (["The authenticity of host 'bazaar.launchpad.net \(\S+\)' "
              "can't be established.",
              "RSA key fingerprint is \S+",
              "Are you sure you want to continue connecting \(yes/no\)\?"],
             "yes")]

        expect_responses += expect_response

        while True:
            try:
                chunk = self.shell.recv(1024)
                sleep_seconds = sleep_seconds_reset
                got_chunk_time = time.time()
                rx = ''.join([rx, chunk])  # faster than += string?
                self.lines = rx.splitlines()
                chunk = saved_chunk + chunk
                saved_chunk = ""

                if len(chunk) and chunk[-1] != "\n":
                    chunk_lines = chunk.splitlines()
                    saved_chunk = chunk_lines[-1]  # Save unfinished line
                    if not quiet:
                        for l in chunk_lines[0:-1]:
                            logging.info(l)

                elif len(chunk) and not quiet:
                    # rstrip: Avoid extra newlines (logging adds one)
                    chunk = chunk.rstrip()
                    logging.info(chunk)

                if len(self.lines):
                    last_line = self.lines[-1]
                    if(self.shell.match_prompt(last_line) or
                       self._terminate_unresponsive_commands(last_line)):
                        break

                    # It is likely that the prompt doesn't have a newline on
                    # the end, so check what we think is a partial line
                    # (saved_chunk) is a prompt. If so, add it back into
                    # self.lines so self.lines contains all the data we have
                    # received before we return to the calling function.
                    if(self.shell.match_prompt(saved_chunk) or
                       self._terminate_unresponsive_commands(saved_chunk)):
                        self.lines.append(saved_chunk)
                        break

            except socket.timeout:
                if not len(self.lines) and len(saved_chunk):
                    self.lines[0] = saved_chunk
                if len(self.lines):
                    # Wait for output to settle before interacting
                    last_line = self.lines[-1]
                    if(self.shell.match_prompt(last_line) or
                       self._terminate_unresponsive_commands(last_line)):
                        break

                    # XXX HACK!!! (for android build)
                    # Probably need to have a expect/response simple set up
                    if last_line.rstrip() == "Enable color display in " \
                                             "this user account (y/N)?":
                        print "[Linaro CI]...Answering no"
                        self.shell.send("N\n")

                    elif(sudo and
                         not sent_sudo_password and
                         re.search("^\[sudo\] password for ", last_line)):
                        self.shell._raw_send(self.sudo_password + "\n")
                        sent_sudo_password = True

                    else:
                        # Respond to regexp matched input
                        for test, response in expect_responses:
                            test_lines = len(test)
                            if test_lines > len(self.lines):
                                continue

                            r_index = 1
                            got_match = True

                            while r_index <= test_lines and got_match is True:
                                if not re.search(test[0 - r_index],
                                                 self.lines[0 - r_index]):
                                    got_match = False
                                r_index += 1

                            if got_match:
                                self.shell._raw_send(response + "\n")
                                break

                if time.time() - got_chunk_time > send_newline_timeout:
                    # If we don't get anything back after a while, try sending
                    # a newline.
                    self.shell._raw_send("\n")

                    # Reset the timer, or we will do this a lot from now on!
                    got_chunk_time = time.time()

                time.sleep(sleep_seconds)
                sleep_seconds *= 1.3

        if not quiet:
            logging.info(saved_chunk)

        # excludes the first line, which is always the command
        # and the last line which is always a prompt, when returning output of
        # an SSH command.
        return self.lines[1:-1]

    def _cmd(self, cmd, sudo=False, expect_response={}):
        rx = self._in_shell_cmd(cmd, sudo=sudo,
                                expect_response=expect_response)
        self._test_return_code(cmd, rx)
        return rx

    def wait_for_prompt(self, expect_response={}):
        """Don't run a command, just wait for a prompt"""
        return self._in_shell_cmd(None, sudo=False,
                                  expect_response=expect_response)

    def cmd(self, command, comment, sudo=False):
        """Run an arbitrary command on the target machine

        The command is run and a comment is required (though it can just be
        empty). This little irritation / documentation is requested because
        frequently used commands really should have their own function and
        tests, but this shortcut exists so users don't have to wait for that
        change to happen before they can continue.
        """
        logging.info("cmd: %s #%s" % (command, comment))

        return self._cmd(command, sudo=sudo)

    def boot(self):
        # TODO: Command not implemented
        logging.info("boot")

    def disconnect(self):
        # TODO: Command not implemented
        logging.info("disconnect")

    def checkout(self, vcs_type, url, branch=None, filename=None, depth=None,
                 name=""):
        """Check out from VCS. Update if checkout already exists.

        Check out from the given URL. If a directory with the same name
        as the target already exists, try to update it instead. Before
        updating we check that the directory really is a checkout of the
        same repository. This seems to work apart from Bazaar branches where
        the repo URL is translated on-server.
        """
        logging.info("checkout: %s, %s, %s, %s" %
                     (vcs_type, url, branch, filename))

        if vcs_type == "repo":
            self._cmd("pwd")
            try:
                self._cmd("git config --global -l")
            except CommandFailed, e:
                for line in e.command_output:
                    if re.search("^fatal: unable to read config file", line):
                        # Set up git as Linaro Infrastructure Robot user
                        self._cmd("git config --global user.email "
                                  "'infrastructure@linaro.org'")
                        self._cmd("git config --global user.name  "
                                  "'Infrastructure Robot'")
                        break
                else:
                    raise

            # Check if repo has already been init'd
            is_branch_of_url = False
            if self.isdir(".repo/manifests"):
                self.chdir(".repo/manifests")

                out = self._cmd("git remote show origin")
                for line in out:
                    if re.search("Fetch URL: " + url, line):
                        is_branch_of_url = True
                        break

            # If repo doesn't exist, init it.
            if not is_branch_of_url:
                cmd_string = "~/bin/repo init -u %s " % url
                if branch:
                    cmd_string += "-b %s " % branch
                if filename:
                    cmd_string += "-m %s " % filename
                self._cmd(cmd_string)

            # Pull files from git repositories that repo points to.
            self._cmd("~/bin/repo sync")

        elif vcs_type == "git":
            arg_string = ""

            if depth:
                arg_string += " --depth %d " % (depth)

            if branch:
                arg_string += " --branch %s " % branch

            # If already checked out, update, else, clone
            dirname = os.path.basename(url)
            if dirname.endswith(".git"):
                dirname = dirname[0:-4]

            is_branch_of_url = False
            if self.isdir(dirname):
                self.chdir(dirname)
                out = self._cmd("git remote show origin")
                for line in out:
                    if re.search("Fetch URL: " + url, line):
                        is_branch_of_url = True
                        break

                if is_branch_of_url:
                    self._cmd("git stash")
                    self._cmd("git reset --hard")
                    self._cmd("git pull")

                self.chdir("..")

            if not is_branch_of_url:
                self._cmd("git clone %s %s" % (arg_string, url))

        elif vcs_type == "bzr":
            # If already checked out, update, else, clone
            if name == "":
                dirname = os.path.basename(url.rstrip("/"))
                dirname = re.sub("^lp:", "", dirname)
            else:
                dirname = name

            is_branch_of_url = False
            if self.isdir(dirname):
                self.chdir(dirname)
                out = self._cmd("bzr info")
                for line in out:
                    if(re.search("parent branch: ", line) or
                       re.search("checkout of branch: ", line)):

                        lp_clean = re.compile("\S+://bazaar.launchpad.net/")
                        line = lp_clean.sub("lp:", line).rstrip("/")
                        test_url = lp_clean.sub("lp:", url).rstrip("/")

                        if re.search(test_url, line):
                            is_branch_of_url = True
                            break

                if is_branch_of_url:
                    self._cmd("bzr update")

                self.chdir("..")

                if not is_branch_of_url:
                    # Something is in the way - delete it
                    self._cmd("rm -rf " + dirname)

            if not is_branch_of_url:
                self._cmd("bzr checkout --quiet %s %s" % (url, name))

        return Checkout()

    def install_deps(self, packages):
        """Generic interface to the system package manager.

        Currently only understands Debian based systems. Should be simple to
        add other package managers and some detection code.
        """
        logging.info("install_deps: %s" % (" ".join(packages)))

        install_packages = []
        for package in packages:
            rx = self._in_shell_cmd("dpkg -l %s" % package)
            for line in rx:
                if re.search("no packages found matching", line,
                             re.IGNORECASE):
                    install_packages.append(package)
        if len(install_packages):
            self._cmd("apt-get update --fix-missing", sudo=True)
            self._cmd("apt-get -yq install %s" % " ".join(install_packages),
                      sudo=True)

    def use(self, name, tags):
        """Use the output of another job as an input to this job

        TODO: Currently this is quite the hack and it should use a database
        rather than fixed paths. Suggest JSON in a known web accessible
        location. Should also support user supplied data.
        """
        logging.info("use: %s, %s" % (name, " ".join(tags)))

        # This is a massive hack and really doesn't work for anything other
        # than the intial investigation phase
        if name == "android-toolchain":
            self._cmd(
                "wget -nc -nv --no-check-certificate "
                "http://android-build.linaro.org/download/"
                "linaro-android_toolchain-4.7-bzr/lastSuccessful/archive/"
                "build/out/"
                "android-toolchain-eabi-4.7-daily-linux-x86.tar.bz2")
            self._cmd("tar -jxvf android-toolchain-eabi-*")

        if name == "linaro-gnu-toolchain":
            rx = self._cmd("find -type d -name toolchain")
            if "./toolchain" not in rx:
                # Don't bother re-downloading the toolchain
                self._cmd("wget -nc -nv --no-check-certificate "
                          "https://releases.linaro.org/13.03/components/"
                          "toolchain/binaries/gcc-linaro-arm-linux-gnueabihf-"
                          "4.7-2013.03-20130313_linux.tar.bz2")
                self.mkdir("toolchain")
                self._cmd("tar -C \"toolchain\"  --strip-components 1 -xf "
                          "gcc-linaro-arm-linux-gnueabihf-*")

    def build(self,
              target="make",
              build_command="make",
              jobs=1,
              cached=False,
              source_uid=None,
              env="",
              expect_response={}):
        """Call a build command, such as "make"
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
        """
        logging.info("build:\n %s\n %s\n jobs=%s\n cached=%s\n"
                     " source_uuid=%s\n env=%s" %
                     (build_command,
                      target,
                      jobs,
                      cached,
                      source_uid,
                      env))

        self._cmd(build_command, expect_response=expect_response)

    def in_directory(self, directory, sudo=False):
        self._cmd("mkdir -p " + directory, sudo=sudo)
        self._cmd("cd " + directory)

    def mkdir(self, directory, sudo=False):
        self._cmd("mkdir -p " + directory, sudo=sudo)

    def chdir(self, directory):
        self._cmd("cd " + directory)

    def copy(self, source, dest, sudo=False):
        self._cmd("cp %s %s" % (source, dest), sudo=sudo)

    def move(self, source, dest, sudo=False):
        self._cmd("mv %s %s" % (source, dest), sudo=sudo)

    def ls(self, target="", sudo=False):
        return self._cmd("ls %s" % (target), sudo=sudo)

    def set_disk_image(self, image):
        self.disk_image = image

    def set_kernel(self, kernel):
        self.kernel = kernel

    def append_to_file(self, string, file_name):
        self._cmd('echo "%s" >> %s' % (string, file_name))

    def cwd(self):
        return self._cmd("pwd")[0]

    def set_env(self, name, value):
        self._cmd("export %s='%s'" % (name, value))

    def publish(self, base_dir, glob_list, destination, license_name):
        # TODO: Command not implemented
        pass

    def write_file(self, path, contents):
        f = self.sftp.open(path, "w")
        f.write(contents)
        f.close()

    def file_open(self, path, mode="r"):
        return self.sftp.open(path, mode)

    def put_file(self, local_path, remote_path):
        self.sftp.put(local_path, remote_path)

    def publish_file(self, local_path, remote_path, server_config):
        """Publish a file from the current slave to the specified server"""
        self._cmd(" ".join([
            "curl -F",
            "file=@{local_path}",
            "-F key={key}",
            "{host}/{path}",]).format(
                local_path=local_path,
                host=server_config["hostname"],
                path=remote_path,
                key=server_config["key"],
            )
        )

    def isdir(self, path):
        try:
            self._cmd("test -d " + path)
        except CommandFailed:
            return False
        return True

    def rm(self, path):
        return self._cmd("rm " + path)


class x86_64(CISlave):
    """Used to run commands on an x86_64 machine"""

    def __init__(self, config={}):
        super(x86_64, self).__init__()
        self.config = config
        self.get_machine()

    def cmd(self, command, comment, sudo=False):
        return super(x86_64, self).cmd(command, comment, sudo)

    def get_machine(self):
        self.prompt = r"ci_lava_target_machine \#: "
        if "reserved" in self.config:
            if self.config["reserved"]["hostname"] == "localhost":
                # Special case: We don't get an SSH connection to localhost,
                # we just run the commands. To do this we invoke a shell that
                # looks like the SSH shell.
                self.shell = LocalShell(self.prompt)
                self.sftp = LocalFiles()
            else:
                self.shell = SSHShell(self.config, self.prompt)
                self.sftp = self.shell.sftp  # Yea, ugly hack for now.


class Snowball(CISlave):
    """Used to run commands on a snowball"""
    # TODO
    pass


class Origen(CISlave):
    """Used to run commands on a origen"""
    # TODO
    pass


class Panda(CISlave):
    """Used to run commands on a panda"""
    # TODO
    pass


class LinaroCIJob(object):
    """All you need to run commands on a slave"""
    def setup(self):
        pass

    def configure(self, parameters):
        pass

    def run(self):
        pass

    def cmd(self):
        pass

    def use(self, job_name, tags=None):
        """Used to provide commands that can be found in the artifacts of other
        builds, for example, use a built GCC."""
        pass

    def post_process(self):
        """Do stuff with logs to produce data that web UI can display and
        CLI can download"""

    def set_triggers(self, triggers):
        self.triggers = triggers


def filter_None_out(a_list):
    result = []
    for item in a_list:
        if item is not None:
            result.append(item)
    return result


class CIJobRuntime(object):
    def __init__(self, args):
        """ Do the first thing that works...

        Try to import parameter 1 as a module.
        Else:
            does current working directory contain <default_script>?
                import it.

        Try to find the next parameter as a class in that module. If the first
        parameter wasn't used as the module import, use it, else use
        parameter 2.
            Else:
                Try the default name - DefaultJob

        While <class> has a function named <next parameter>:
            Push function name onto the "functions to run" stack
        else:
            run function "run"

        All other parameters are passed to <class> __init__.

        Run each function on stack/"run" in turn.
        """
        logging.basicConfig(format='%(message)s', level=logging.INFO)
        self.parameters = []
        self.functions = []
        self.file_name = "CIJob"
        self.job_name = "DefaultJob"

        state = "file_name"
        module = None
        self.job = None

        index = 0
        while state != "params" or index < len(args):
            # If there is an argument to process, use it, else wait for state
            # machine to get into the final state
            if index < len(args):
                arg = args[index]
            else:
                arg = None

            if state == "file_name":
                to_try = filter_None_out([arg, self.file_name])

                for name in to_try:
                    try:
                        module = importlib.import_module(name)
                        self.file_name = name
                        state = "job_name"
                        break
                    except ImportError:
                        pass

                if module is None:
                    logging.error(
                        "ERROR: Command not found, tried importing %s.",
                        to_try)
                    exit(1)
                elif arg == self.file_name:
                    # If we used the argument, move on to the next one
                    index += 1
                    continue

            if state == "job_name":
                to_try = filter_None_out([arg, self.job_name])
                for name in to_try:
                    try:
                        self.job = getattr(module, name)()
                        self.job_name = name
                        state = "functions"
                        break
                    except AttributeError:
                        pass

                if self.job is None:
                    logging.error("ERROR: Job not found. Tried %s", to_try)
                    exit(1)
                elif arg == self.job_name:
                    # If we used the argument, move on to the next one
                    index += 1
                    continue

            if state == "functions":
                if len(self.functions) == 0:
                    # Always have setup first
                    self.functions.append(getattr(self.job, "setup"))

                if arg == "setup":
                    # Setup is always run, so we don't put it in the list.
                    index += 1

                try:
                    self.functions.append(getattr(self.job, arg))
                    index += 1
                    continue
                except (AttributeError, TypeError):
                    if len(self.functions) == 1:  # Just got setup function.
                        self.functions.append(getattr(self.job, "run"))
                    state = "params"

            if state == "params":
                if arg is not None:
                    self.parameters.append(arg)
                index += 1

        if len(self.functions) == 0:
            logging.error("ERROR: Job not found.")
            exit(1)

        getattr(self.job, "configure")(self.parameters)
        for function in self.functions:
            function()
