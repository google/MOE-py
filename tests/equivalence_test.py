#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for moe.actions.EquivalenceCheck."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import gflags as flags
from google.apputils import basetest

from moe import actions
from moe import base
from moe import codebase_utils
from moe import moe_app
import test_util

FLAGS = flags.FLAGS


def setUp():
  moe_app.InitForTest()


class EquivalenceTest(basetest.TestCase):

  def testEquivalent(self):
    project = test_util.EmptyMoeProjectConfig()
    ec = actions.EquivalenceCheck(
        '1001', '1', project, actions.EquivalenceCheck.ErrorIfDifferent)

    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python'})
    public_creator = test_util.StaticCodebaseCreator(
        {'1': 'simple_python'})

    result = ec.Perform(internal_creator, public_creator, None, None,
                        FLAGS.test_tmpdir, [])
    self.assertEqual(result, None)

  def testEquivalentIfDifferentButHaveManualDeltas(self):
    project = test_util.EmptyMoeProjectConfig()
    project.manual_equivalence_deltas = True
    ec = actions.EquivalenceCheck(
        '1001', '1', project, actions.EquivalenceCheck.ErrorIfDifferent)

    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python'})
    public_creator = test_util.StaticCodebaseCreator(
        {'1': 'modified_python'})

    result = ec.Perform(internal_creator, public_creator, None, None,
                        FLAGS.test_tmpdir, [])
    self.assertEqual(result, None)

  def testDifferent(self):
    project = test_util.EmptyMoeProjectConfig()
    ec = actions.EquivalenceCheck(
        '1001', '1', project, actions.EquivalenceCheck.ErrorIfDifferent)

    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python'})
    public_creator = test_util.StaticCodebaseCreator(
        {'1': 'modified_python'})

    self.assertRaises(base.Error, ec.Perform,
                      internal_creator, public_creator, None, None,
                      FLAGS.test_tmpdir, [])


if __name__ == '__main__':
  basetest.main()
