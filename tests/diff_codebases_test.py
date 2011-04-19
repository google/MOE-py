#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Tests file and codebase differences w/ full diff output."""



import os

import gflags as flags
from google.apputils import basetest

from moe import base
from moe import codebase_utils
from moe import moe_app
import test_util

FLAGS = flags.FLAGS


def setUp():
  moe_app.InitForTest()


def tearDown():
  pass


class DiffCodebasesTest(basetest.TestCase):

  def testMissingLine(self):
    self._CheckFileDifference('missingline')

  def testDifferentLines(self):
    self._CheckFileDifference('differentlines')

  def testCodebaseDifference(self):
    codebase_internal = test_util.TestResourceFilename(
        os.path.join('diff_codebases', 'codebase_internal/'))
    codebase_public = test_util.TestResourceFilename(
        os.path.join('diff_codebases', 'codebase_public/'))

    codebase_diff_obj = base.AreCodebasesDifferent(
        codebase_utils.Codebase(codebase_internal),
        codebase_utils.Codebase(codebase_public),
        record_full_diffs=True)
    print 'codebase_diff_obj:', codebase_diff_obj

    expected_diff = open(test_util.TestResourceFilename(
        os.path.join('diff_codebases', 'codebase_diff'))).read()

    self.assertEquals(expected_diff.strip(), str(codebase_diff_obj).strip())

  def _CheckFileDifference(self, scenario_name):
    file_internal = test_util.TestResourceFilename(
        os.path.join('diff_codebases', 'codebase_internal', scenario_name))
    file_public = test_util.TestResourceFilename(
        os.path.join('diff_codebases', 'codebase_public', scenario_name))

    file_diff_obj = base.AreFilesDifferent(
        file_internal, file_public,
        relative_filename=scenario_name, record_full_diffs=True)
    print 'file_diff_obj for scenario %s: %s' % (scenario_name, file_diff_obj)

    expected_diff = open(test_util.TestResourceFilename(
        os.path.join('diff_codebases', scenario_name + '_diff'))).read()

    self.assertEquals(expected_diff.strip(), file_diff_obj.reason.strip())


if __name__ == '__main__':
  basetest.main()
