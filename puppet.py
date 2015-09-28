#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible module to run Puppet
(c) 2015, Red Hat, Inc
Written by Jonathan Mainguy <jon at soh.re>

This file is part of Ansible

Ansible is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Ansible is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
"""

DOCUMENTATION = '''
---
module: puppet
short_description: Run/enable/disable puppet agent
description:
     - Run the puppet agent, or enable it, or disable it, and optionally add a rpmdiff to the stdout
version_added: "2.0"
options:
  state:
    description:
      - Desired state of puppet agent
      - if state=run, it also enables the puppet agent beforehand to ensure it runs.
    required: true
    default: null
    choices: [ "run", "enable", "disable" ]
  packagediff:
    description:
      - Add a diff of packges installed by puppet (Currently only rpm systems)
    required: false
    default: yes
    choices: ["yes", "no"]
author: "Jonathan Mainguy (@jmainguy)"

'''

EXAMPLES = '''
# Disable puppet agent, so that puppet agent -t no longer works
- puppet: state=disable

# Run puppet, but do not add rpmdiff to output
- puppet: state=run packagediff=no

# Run puppet, and allow pretty rpmdiff to be added to output. Also print it to screen with debug module
- name: run puppet
  puppet: state=run
  register: puppet

- name: Print puppet output
  debug: var={{ item }}
  with_items:
    - puppet.stdout_lines
'''

import os
import re
import rpm
import difflib

class Puppet(object):
    """
    This module was written to run puppet for redhat IT.
    """

    def __init__(self, module):
        self.module            = module
        self.state             = module.params['state']

    def puppet_status(self, module, state):
        if state == 'run':
            module.run_command("puppet agent --enable")
            rc, stdout, stderr = module.run_command("puppet agent --test --color 0")
            # Remove pointless lines nobody cares about
            stdout = re.sub('(?i)Info:.*\n', '', stdout)
            stdout = re.sub('(?i)Notice: Ignoring --listen on onetime run\n', '', stdout)
            # Filter out passwords
            stdout = re.sub('.*default_db.*', '************Password filtered out************', stdout)
            stdout = re.sub('.*password.*', '************Password filtered out************', stdout)
            # In puppet, 2 means changed, 4 means errors, 6 means changed and errors
        else:
            cmd = "puppet agent --%s" % state
            rc, stdout, stderr = module.run_command(cmd)
        return (rc, stdout, stderr)

class Rpmdatabase(object):
    """
    This is to capture rpm -qa
    """

    def __init__(self, module):
        self.module            = module

    def rpm(self):
        rpmlist = []
        ts = rpm.TransactionSet()
        mi = ts.dbMatch()
        for h in mi:
            rpmlist.append("%s-%s-%s" % (h['name'], h['version'], h['release']))
        return rpmlist

    def formatdiff(self, rpmdiff):
        text = ''
        seperator = '================================================================================\n'
        diffheader = 'This is the RPM delta\n'
        # Only add lines begining with - or + immediately followed by a letter
        for line in rpmdiff:
            found = re.search("^[-|+][a-zA-Z].*", line)
            if found:
                text += line + '\n'
        rpmdiff = seperator + diffheader + text + seperator
        return rpmdiff
    

def main():
    module = AnsibleModule(
        argument_spec = dict(
            state = dict(required=False, default=None),
            packagediff = dict(type='bool', default=True, required=False),
        ),
    )

    state = module.params['state']
    packagediff = module.params['packagediff']
    puppet = Puppet(module)
    rpmdata = Rpmdatabase(module)
    rpmdiff = ''


    if state not in ['run', 'enable', 'enabled', 'disable', 'disabled']:
        module.fail_json(msg="value of state must be one of: enabled, disabled, run, got: %s" % state)
    elif state is 'disabled':
        state = 'disable'
    elif state is 'enabled':
        state = 'enable'

    if packagediff is True and state == 'run':
        prelist = rpmdata.rpm()
        rc, stdout, stderr = puppet.puppet_status(module, state)
        postlist = rpmdata.rpm()
        rpmdiff = difflib.unified_diff(prelist, postlist, n=0, lineterm="")
        rpmdiff = rpmdata.formatdiff(rpmdiff)
        stdout = stdout + rpmdiff
    else:
        rc, stdout, stderr = puppet.puppet_status(module, state)
        module.exit_json(changed=True, rc=rc, stdout=stdout, stderr=stderr)

    # 2 means stuff changed, 4 means errors, 6 means stuff changed and errors
    if rc != 2:
        module.fail_json(msg='Puppet encountered errors. %s %s' % (stdout, stderr) )
    else:
        rc = 0

    # If you got this far, then stuff worked
    module.exit_json(changed=True, rc=rc, stdout=stdout, stderr=stderr)

from ansible.module_utils.basic import *
main()
