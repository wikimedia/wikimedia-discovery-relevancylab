#!/usr/bin/env python
# relevancyRunner.py - Run relevance lab queries
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
# http://www.gnu.org/copyleft/gpl.html

import os
import sys
import argparse
import ConfigParser
import pipes
import shutil
import subprocess
import re


def getSafeName(name):
    return re.sub(r'[^a-zA-Z0-9]', '-', name)


def refreshDir(dirname):
    # Delete the dir if it exists to clean out cruft from previous runs
    if os.path.exists(dirname):
        shutil.rmtree(dirname)
    os.makedirs(dirname)


def runSearch(config, section):
    qname = getSafeName(config.get(section, 'name'))
    qdir = config.get('settings', 'workDir') + "/queries/" + qname
    refreshDir(qdir)
    cmdline = config.get('settings', 'searchCommand')
    if config.has_option(section, 'config'):
        cmdline += " --options " + pipes.quote(open(config.get(section, 'config')).read())
        shutil.copyfile(config.get(section, 'config'),
                        qdir + '/config.json')  # archive search config
    runCommand("cat %s | ssh %s %s > %s" % (config.get(section, 'queries'),
                                            config.get('settings', 'labHost'),
                                            pipes.quote(cmdline), qdir + "/results"))
    shutil.copyfile(config.get(section, 'queries'), qdir + '/queries')  # archive queries
    return qdir + "/results"


def checkSettings(config, section, settings):
    for s in settings:
        if not config.has_option(section, s):
            raise ValueError("Section [%s] missing configuration %s" % (section, s))
    pass


def runCommand(cmd):
    print "RUNNING "+cmd
    subprocess.check_call(cmd, shell=True)


parser = argparse.ArgumentParser(description='Run relevance lab queries', prog=sys.argv[0])
parser.add_argument('-c', '--config', dest='config', help='Configuration file name', required=True)
args = parser.parse_args()

config = ConfigParser.ConfigParser()
config.readfp(open(args.config))
checkSettings(config, 'settings', ['labHost', 'workDir', 'jsonDiffTool',
                                   'metricTool', 'searchCommand'])
checkSettings(config, 'test1', ['name', 'queries'])
checkSettings(config, 'test2', ['name', 'queries'])

res1 = runSearch(config, 'test1')
res2 = runSearch(config, 'test2')
comparisonDir = "%s/comparisons/%s_%s" % (config.get('settings', 'workDir'),
                                          getSafeName(config.get('test1', 'name')),
                                          getSafeName(config.get('test2', 'name')))
refreshDir(comparisonDir)
shutil.copyfile(args.config, comparisonDir + "/config.ini")  # archive comparison config

runCommand("%s %s %s %s" % (config.get('settings', 'jsonDiffTool'),
                            comparisonDir + "/diffs", res1, res2))
runCommand("%s %s %s %s" % (config.get('settings', 'metricTool'), comparisonDir, res1, res2))
