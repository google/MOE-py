#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests merge_codebases."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import os
import sys

import gflags as flags
from google.apputils import basetest

from moe import base
from moe import codebase_utils
from moe import merge_codebases
from moe import moe_app
import test_util

FLAGS = flags.FLAGS

SCENARIOS_DIR = ''
UNRUN_SCENARIOS = None
EXPANDER = None

def setUp():
  global SCENARIOS_DIR
  SCENARIOS_DIR = test_util.TestResourceFilename('merge_codebases_scenarios/')
  global UNRUN_SCENARIOS
  UNRUN_SCENARIOS = set(os.listdir(SCENARIOS_DIR))
  moe_app.InitForTest()


def tearDown():
  # TODO(dbentley): I can't call assert in global tear down.
  if UNRUN_SCENARIOS:
    print 'UNRUN_SCENARIOS:', repr(UNRUN_SCENARIOS)
    sys.exit(1)


class MergeCodebasesTest(basetest.TestCase):

  def testOneFile(self):
    self.RunScenario('one_file')

  def testAddOneFile(self):
    self.RunScenario('add_one_file')

  def testDeleteOneFile(self):
    self.RunScenario('delete_one_file')

  def testDeleteOneFileFromInternal(self):
    self.RunScenario('delete_one_file_from_internal')

  def testEditOneFile(self):
    self.RunScenario('edit_one_file')

  def testMergeOneFile(self):
    self.RunScenario('merge_one_file')

  def testAddFileSimultaneously(self):
    self.RunScenario('add_file_simultaneously')

  def testExecutableBit(self):
    self.RunScenario('executable')

  def _MakeCodebase(self, path):
    return codebase_utils.Codebase(path)

  def RunScenario(self, scenario_name):
    UNRUN_SCENARIOS.remove(scenario_name)
    scenario_base = os.path.join(SCENARIOS_DIR, scenario_name)

    args = dict(
        generated_codebase=self._MakeCodebase(
            os.path.join(scenario_base, 'generated')),
        public_codebase=self._MakeCodebase(
            os.path.join(scenario_base, 'public')),
        previous_codebase=self._MakeCodebase(
            os.path.join(scenario_base, 'previous')),
        )

    config = merge_codebases.MergeCodebasesConfig(
        **args)

    context = merge_codebases.MergeCodebasesContext(
        config)

    context.Update()

    codebase1 = config.merged_codebase
    codebase2 = os.path.join(scenario_base, 'expected')

    different = base.AreCodebasesDifferent(codebase1, codebase2)

    if different:
      # TODO(dbentley): this should describe how they differ.
      print 'DIFFERENT:', different
      self.fail("Codebases %s and %s differ" % (codebase1, codebase2))


if __name__ == '__main__':
  basetest.main()
