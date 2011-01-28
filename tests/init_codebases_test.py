#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for moe.init_codebases."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import os

import gflags as flags
from google.apputils import basetest

from moe import init_codebases
import test_util


FLAGS = flags.FLAGS


def setUp():
  FLAGS.Reset()
  init_codebases.DefineFlags(FLAGS)

def tearDown():
  FLAGS.Reset()

class InitCodebasesTest(basetest.TestCase):

  def RunScenario(self, project_config_name, codebase_expectations,
                  editor_expectations):
    # Mock out
    test_util.MockOutDatabase()
    test_util.MockOutMakeRepositoryConfig()

    # the config file
    FLAGS.project_config_file = test_util.TestResourceFilename(
        os.path.join('init_codebases', project_config_name))

    test_util.MockOutPusher(self, codebase_expectations, editor_expectations)

    init_codebases.raw_input = lambda s: 'y'
    init_codebases.getpass.getpass = lambda s: 'fake_password'
    init_codebases.main([])

  def testSimple(self):
    FLAGS.internal_revision = '1001'
    self.RunScenario('project_config.txt',
                     ('test_internal', '1001'),
                     ('test_public', 'head'))

  def testSpecifyAnEquivalence(self):
    # TODO(dbentley): we need a way to mock out equivalence check
    pass


if __name__ == '__main__':
  basetest.main()
