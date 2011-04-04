#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for moe.init_codebases."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import os

import gflags as flags
from google.apputils import basetest

from moe import init_codebases
from moe import moe_app
import test_util


FLAGS = flags.FLAGS


def setUp():
  FLAGS.Reset()
  moe_app.InitForTest()
  init_codebases.DefineFlags(FLAGS)

def tearDown():
  FLAGS.Reset()

class InitCodebasesTest(basetest.TestCase):

  def testSimple(self):
    FLAGS.internal_revision = '1001'
    test_util.MockOutDatabase()
    test_util.MockOutMakeRepositoryConfig()

    FLAGS.project_config_file = test_util.TestResourceFilename(
        os.path.join('init_codebases', 'project_config.txt'))

    test_util.MockOutPusher(self, ('test_internal', '1001'),
                            ('test_public', 'head'))

    init_codebases.raw_input = lambda s: 'y'
    init_codebases.getpass.getpass = lambda s: 'fake_password'
    init_codebases.main([])

  def testSpecifyAnEquivalence(self):
    test_util.MockOutDatabase()
    test_util.MockOutMakeRepositoryConfig(
        repository_configs={
            'test_internal': (None, test_util.StaticCodebaseCreator(
                {'1001': 'simple_python'})),
            'test_public': (None, test_util.StaticCodebaseCreator(
                {'1': 'simple_python'}))
            })

    FLAGS.internal_revision = '1001'
    FLAGS.public_revision = '1'
    FLAGS.project_config_file = test_util.TestResourceFilename(
        os.path.join('init_codebases', 'project_config.txt'))
    init_codebases.main([])


if __name__ == '__main__':
  basetest.main()
