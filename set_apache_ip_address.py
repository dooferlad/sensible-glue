#!/usr/bin/python

# Copyright 2013 Linaro Ltd.  This software is licensed under the
# GNU General Public License version 3 (see the file COPYING).

"""
Extremely hacky script that assumes that the first line in the file it is
modifying is <VirtualHost {{something}}> and just replaces it. Doesn't even
check that this is the case. Just replaces line 1 of the file.
"""

import sys

file_name = sys.argv[1]

with open(file_name) as f:
    lines = f.readlines()

with open(file_name, "w") as f:
    f.write("<VirtualHost *:80>\n")
    f.write("".join(lines[1:]))
