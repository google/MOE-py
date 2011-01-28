#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Tests for moe.moe_ui."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

from google.apputils import basetest

from moe import moe_ui
import test_util


class MoeUiTest(basetest.TestCase):
  def setUp(self):
    self._ui = moe_ui.MoeUI()

  def testImmediateTask(self):
    basetest.CaptureTestStdout()
    t = self._ui.BeginImmediateTask('foo', 'Fooing')
    with t:
      pass
    basetest.DiffTestStdout(
        test_util.TestResourceFilename('moe_ui/immediate.txt'))

  def testIntermediateTask(self):
    basetest.CaptureTestStdout()
    t = self._ui.BeginIntermediateTask('foo', 'Fooing')
    with t:
      self._ui.Info('Bar')
    basetest.DiffTestStdout(
        test_util.TestResourceFilename('moe_ui/intermediate.txt'))

  def testNestedTasks(self):
    basetest.CaptureTestStdout()
    t = self._ui.BeginIntermediateTask('foo', 'Fooing')
    with t:
      self._ui.Info('Bar')
      t2 = self._ui.BeginImmediateTask('baz', 'Bazing')
      with t2:
        pass
    basetest.DiffTestStdout(
        test_util.TestResourceFilename('moe_ui/nested.txt'))



if __name__ == '__main__':
  basetest.main()
