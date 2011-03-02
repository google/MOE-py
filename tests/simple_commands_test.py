#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Tests for moe.simple_commands."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import os

import gflags as flags
from google.apputils import basetest

from moe import moe_app
from moe import simple_commands
import test_util


FLAGS = flags.FLAGS


class SimpleCommandsTest(basetest.TestCase):

  def setUp(self):
    FLAGS.Reset()
    moe_app.InitForTest()

  def testCheckConfig(self):
    test_util.MockOutDatabase()
    test_util.MockOutMakeRepositoryConfig()
    FLAGS.project_config_file = test_util.TestResourceFilename(
        # We use the same project config as push_codebase_smoke_test
        os.path.join('push_codebase_smoke_test', 'project_config.txt'))

    check_config_cmd = simple_commands.CheckConfigCmd('check_config', FLAGS)
    check_config_cmd.Run([])


if __name__ == '__main__':
  basetest.main()
