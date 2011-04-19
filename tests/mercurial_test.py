#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for moe.mercurial."""



import os
import sys

import mox

from google.apputils import file_util
import gflags as flags

from google.apputils import basetest
from moe import mercurial
from moe import moe_app
import test_util


FLAGS = flags.FLAGS

SCENARIOS_DIR = ''
UNRUN_SCENARIOS = None

SUPPORTED_VERSION = """
Mercurial Distributed SCM (version 1.6)

Copyright (C) 2005-2010 Matt Mackall <mpm@selenic.com> and others
This is free software; see the source for copying conditions. There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
"""

SUPPORTED_VERSION_2 = """
Mercurial Distributed SCM (version 1.8.1+84-3be7ba94baaf)
(see http://mercurial.selenic.com for more information)

Copyright (C) 2005-2011 Matt Mackall and others
This is free software; see the source for copying conditions. There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
"""

UNSUPPORTED_VERSION = """
Mercurial Distributed SCM (version 1.4.3)

Copyright (C) 2005-2010 Matt Mackall <mpm@selenic.com> and others
This is free software; see the source for copying conditions. There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
"""


def setUp():
  global SCENARIOS_DIR
  SCENARIOS_DIR = test_util.TestResourceFilename('mercurial_scenarios/')
  global UNRUN_SCENARIOS
  UNRUN_SCENARIOS = set(os.listdir(SCENARIOS_DIR))


def tearDown():
  if UNRUN_SCENARIOS:
    print 'UNRUN_SCENARIOS:', repr(UNRUN_SCENARIOS)
    sys.exit(1)


class MercurialTest(basetest.TestCase):
  def setUp(self):
    self.mox = mox.Mox()

  def tearDown(self):
    self.mox.UnsetStubs()
    self.mox.ResetAll()

  def testVersionRegex(self):
    self.assertTrue(mercurial.IsSupportedVersion(SUPPORTED_VERSION))
    self.assertTrue(mercurial.IsSupportedVersion(SUPPORTED_VERSION_2))
    self.assertFalse(mercurial.IsSupportedVersion(UNSUPPORTED_VERSION))
    self.assertFalse(mercurial.IsSupportedVersion(''))

  def testShortLog(self):
    self.RunScenario('short_log', FilterLog)

  def testLongLog(self):
    self.RunScenario('long_log', FilterLog)

  def RunScenario(self, scenario_name, filter_to_test):
    UNRUN_SCENARIOS.remove(scenario_name)
    scenario_base = os.path.join(SCENARIOS_DIR, scenario_name)
    in_file = os.path.join(scenario_base, 'input')
    input_txt = file_util.Read(in_file)
    output = filter_to_test(input_txt)
    expected = os.path.join(scenario_base, 'expected')
    out_file = os.path.join(FLAGS.test_tmpdir, scenario_name + '.out.txt')
    file_util.Write(out_file, output)
    basetest.DiffTestFiles(expected, out_file)

  def testRecurUntilMatchingRevision(self):
    self.mox.StubOutWithMock(mercurial, 'RunHg')
    mercurial.RunHg(['version'], need_stdout=True).AndReturn('(version 1.8)')
    self.mox.ReplayAll()

    repos = mercurial.MercurialRepository(
        'http://not_a_url', 'Dummy mercurial repository')
    self.mox.UnsetStubs()

    log_file = os.path.join(SCENARIOS_DIR, 'long_log', 'input')
    log_text = file_util.Read(log_file)
    def Revisionb05847911039(r):
      return r.rev_id == 'b05847911039'

    self.mox.StubOutWithMock(repos._client, 'RunHg')
    repos._client.RunHg(['pull']).AndReturn(None)
    repos._client.RunHg(['log', '--style', 'default', '-v', '-l',
                         '400', '-r', 'dummy:0'],
                        need_stdout=True).AndReturn(log_text)
    self.mox.ReplayAll()

    result = repos.RecurUntilMatchingRevision('dummy', Revisionb05847911039)
    self.assertEqual(3, len(result))
    self.assertEqual('b05847911039', result[-1].rev_id)
    self.mox.UnsetStubs()


def FilterLog(text):
  return '\n'.join([str(rev) for rev in mercurial.ParseRevisions(text, '')])


if __name__ == '__main__':
  moe_app.InitForTest()
  basetest.main()
