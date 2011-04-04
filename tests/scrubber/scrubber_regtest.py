#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests scrubber for regressions."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import os
import sys

import gflags as flags
from google.apputils import basetest

from moe import base
from moe import codebase_utils
from moe import moe_app
from moe.scrubber import scrubber
import test_util

FLAGS = flags.FLAGS

SCENARIOS_DIR = test_util.TestResourceFilename('regtest_scenarios/')
UNRUN_SCENARIOS = None


def setUp():
  # pylint: disable-msg=W0603
  global UNRUN_SCENARIOS
  UNRUN_SCENARIOS = set(os.listdir(SCENARIOS_DIR))
  moe_app.InitForTest()


def tearDown():
  # TODO(dbentley): I can't call assert in global tear down.
  if UNRUN_SCENARIOS:
    print 'UNRUN_SCENARIOS:', repr(UNRUN_SCENARIOS)
    sys.exit(1)


class ScrubberRegressionTest(basetest.TestCase):

  def testJavaCoalescing(self):
    self.RunScenario('java_coalescing')

  def testExecutableBit(self):
    self.RunScenario('executable_bit')

  def testReplaceStripped(self):
    self.RunScenario('replace_stripped')

  def testUsernames(self):
    self.RunScenario('usernames')

  def testIgnoreFiles(self):
    self.RunScenario('ignore_files')

  def testWhitelist(self):
    self.RunScenario('whitelist')

  def testJsDirectoryRename(self):
    self.RunScenario('js_directory_rename')

  def testJsDirectoryRenames(self):
    self.RunScenario('js_directory_renames')

  def testPhp(self):
    self.RunScenario('php')

  def testPython(self):
    self.RunScenario('python')

  def testGwtInherits(self):
    self.RunScenario('gwt_inherits')

  def testUnicode(self):
    self.RunScenario('unicode')

  def testSensitiveWords(self):
    self.RunScenario('sensitive_words')

  def testStringReplacement(self):
    self.RunScenario('string_replacement')

  def testExtensionMap(self):
    self.RunScenario('extension_map')

  def testJavaModuleRename(self):
    self.RunScenario('java_module_rename')

  def testScrubSensitiveComments(self):
    self.RunScenario('scrub_sensitive_comments')

  def testScrubProtoComments(self):
    self.RunScenario('scrub_proto_comments')

  def testScrubSwigComments(self):
    self.RunScenario('scrub_swig_comments')

  def testScrubHtmlAuthors(self):
    self.RunScenario('scrub_html_authors')

  def testScrubPythonAuthors(self):
    self.RunScenario('scrub_python_authors')

  def testRenaming(self):
    self.RunScenario('rename')

  def testErrorInDeletedFile(self):
    self.RunScenario('error_in_deleted_file')

  # TODO(dborowitz): More tests with inputs that are known to fail scrubbing.

  def RunScenarioWithConfigFile(self, scenario_base, config_file):
    codebase = os.path.join(scenario_base, 'input')
    config_path = os.path.join(scenario_base, config_file)
    (_, input_files) = scrubber.CreateInputFileListFromDir(codebase)
    config = scrubber.ParseConfigFile(config_path, codebase, input_files)
    context = scrubber.ScrubberContext(config)

    context.Scan()

    context.WriteOutput()

    codebase1 = os.path.join(scenario_base, 'expected')
    if not os.path.exists(codebase1):
      self.assertTrue(context.Status(),
                      'Scrubber was expected to fail but did not')
      return

    if context.Status():
      context.Report()
      self.fail('Scrubber returned non-zero status %d' % context.Status())

    codebase2 = os.path.join(context._temp_dir, 'output')

    different = base.AreCodebasesDifferent(
        codebase_utils.Codebase(codebase1),
        codebase_utils.Codebase(codebase2))

    if different:
      # TODO(dbentley): this should describe how they differ.
      self.fail('Codebases %s and %s differ' % (codebase1, codebase2))

  def RunScenario(self, scenario_name):
    UNRUN_SCENARIOS.remove(scenario_name)
    scenario_base = os.path.join(SCENARIOS_DIR, scenario_name)
    self.RunScenarioWithConfigFile(scenario_base, 'config.json')


if __name__ == '__main__':
  basetest.main()
