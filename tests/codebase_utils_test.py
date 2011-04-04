#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for moe.codebase_utils."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import gflags as flags

from google.apputils import basetest

from moe import base
from moe import codebase_utils
from moe import moe_app
import test_util

FLAGS = flags.FLAGS

def setUp():
  moe_app.InitForTest()


class CodebaseUtilsTest(basetest.TestCase):

  def testWalk(self):
    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python'})

    codebase = internal_creator.Create('1001')
    self.assertEqual(codebase.Walk(), ['foo.py'])

    codebase2 = codebase_utils.Codebase(
        codebase.ExpandedPath(), additional_files_re='foo.py')
    self.assertEqual(codebase2.Walk(), [])

  def testCreateModifiableCopy(self):
    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python'})

    codebase = internal_creator.Create('1001')
    copy = codebase_utils.CreateModifiableCopy(codebase)
    self.assertFalse(base.AreCodebasesDifferent(codebase, copy))
    self.assertFalse(codebase.Path() == copy.Path())


if __name__ == '__main__':
  basetest.main()
