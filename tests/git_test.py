#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for moe.git."""



import os
import sys

from google.apputils import file_util
import gflags as flags

from google.apputils import basetest
from moe import git
import test_util


FLAGS = flags.FLAGS

SCENARIOS_DIR = ''
UNRUN_SCENARIOS = None


def setUp():
  global SCENARIOS_DIR
  SCENARIOS_DIR = test_util.TestResourceFilename('git_scenarios/')
  global UNRUN_SCENARIOS
  UNRUN_SCENARIOS = set(os.listdir(SCENARIOS_DIR))


def tearDown():
  if UNRUN_SCENARIOS:
    print 'UNRUN_SCENARIOS:', repr(UNRUN_SCENARIOS)
    sys.exit(1)


class GitTest(basetest.TestCase):

  def testShortLog(self):
    self.RunScenario('short_log', FilterLog)

  def testLongLog(self):
    self.RunScenario('long_log', FilterLog)

  def testHeadRevisionError(self):
    client = git.GitClient(
        os.path.join(FLAGS.test_tmpdir, 'testHeadRevisionError'),
        'http://localhost:8080/')
    result = client.GetHeadRevision('1')
    self.assertFalse(result)

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


def FilterLog(text):
  return '\n'.join([str(rev) for rev in git.ParseRevisions(text, '')])


if __name__ == '__main__':
  basetest.main()
