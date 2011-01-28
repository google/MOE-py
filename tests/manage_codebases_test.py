#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for MOE's manage_codebases tool."""

__author__ = 'dborowitz@google.com (Dave Borowitz)'

import os

import gflags as flags
from google.apputils import basetest

from moe import actions
from moe import base
from moe import manage_codebases
import test_util

FLAGS = flags.FLAGS


def setUp():
  FLAGS.Reset()
  manage_codebases.DefineFlags(FLAGS)


def tearDown():
  FLAGS.Reset()


class ActionExpectation(object):
  def __init__(self, cls, attrs, test):
    self._cls = cls
    self._attrs = attrs
    self._test = test

  def Check(self, action):
    if not isinstance(action, self._cls):
      self._test.fail("Object is not an instance of %s (it's a %s)" %
                      (str(self._cls), type(action)))
    for attr, expected_value in self._attrs.items():
      self._test.assertEqual(expected_value, getattr(action, attr))


class DeleteOthersAction(object):
  def Perform(self, *args, **kwargs):
    return actions.StateUpdate(actions=[])


ORIGINAL_CHOOSE_ACTIONS = manage_codebases.ManageCodebasesContext._ChooseActions


class ManageCodebasesTestCase(basetest.TestCase):
  def _ECs(self, internal_revision, public_revision):
    # NB(dbentley): right now, manage_codebases generates some bad
    # actions initially. This could probably be done better, but that's
    # for another day.
    return [ActionExpectation(
        actions.EquivalenceCheck,
        {'internal_revision':'1001',
         'public_revision': '1',
         }, self)] * 2

  def RunScenario(self, db, repository_configs, expected_action_checkers,
                  project_config_name='project_config.txt'):
    test_util.MockOutDatabase(db=db)
    test_util.MockOutMakeRepositoryConfig(repository_configs)

    test = self
    def OverridingChooseActions(self, book):
      actions = ORIGINAL_CHOOSE_ACTIONS(self, book)
      test.assertEqual(len(expected_action_checkers), len(actions))
      for expected, actual in zip(expected_action_checkers, actions):
        expected.Check(actual)

      # We want to test that Action.Perform() is called and the value
      # treated appropriately. But we don't want to actually perform
      # the later actions, so we return a result that is run once and
      # then stops the loop.
      return [DeleteOthersAction()] + actions

    manage_codebases.ManageCodebasesContext._ChooseActions = (
        OverridingChooseActions)

    FLAGS.project_config_file = test_util.TestResourceFilename(
        os.path.join('manage_codebases', project_config_name))

    manage_codebases.main([])

  def testSimple(self):
    db = test_util.MockDbClient()
    equiv = base.Correspondence('1001', '1')
    db.NoteEquivalence(equiv)

    internal_repos = test_util.MockRepository(
        'test_internal', '1001',
        revisions_since_equivalence_results=([], [equiv]))
    public_repos = test_util.MockRepository(
        'test_public', '1',
        revisions_since_equivalence_results=([], [equiv]))
    repository_configs = {
        'test_internal': (internal_repos, None),
        'test_public': (public_repos, None),
        }

    # NB(dbentley): right now, manage_codebases generates often-redundant
    # equivalence checks. We should clean it up at some point, but that's
    # for another day.
    self.RunScenario(
        db, repository_configs,
        self._ECs('1001', '1'))

  def testOneExport(self):
    db = test_util.MockDbClient()
    equiv = base.Correspondence('1001', '1')
    db.NoteEquivalence(equiv)

    revisions = [base.Revision('1003'), base.Revision('1002')]
    internal_repos = test_util.MockRepository(
        'test_internal', '1001',
        revisions_since_equivalence_results=(revisions, [equiv]))
    public_repos = test_util.MockRepository(
        'test_public', '1',
        revisions_since_equivalence_results=([], [equiv]))
    repository_configs = {
        'test_internal': (internal_repos, None),
        'test_public': (public_repos, None),
        }

    self.RunScenario(
        db, repository_configs,
        self._ECs('1001', '1') + [
            ActionExpectation(
                actions.Migration,
                {'revisions': list(reversed(revisions)),
                 'num_revisions_to_migrate': -1,
                 }, self)
            ]
        )

  def testOneImport(self):
    db = test_util.MockDbClient()
    equiv = base.Correspondence('1001', '1')
    db.NoteEquivalence(equiv)

    internal_repos = test_util.MockRepository(
        'test_internal', '1001',
        revisions_since_equivalence_results=([], [equiv]))
    revisions = [base.Revision('3'), base.Revision('2')]
    public_repos = test_util.MockRepository(
        'test_public', '1',
        revisions_since_equivalence_results=(revisions, [equiv]))
    repository_configs = {
        'test_internal': (internal_repos, None),
        'test_public': (public_repos, None),
        }

    self.RunScenario(
        db, repository_configs,
        self._ECs('1001', '1') + [
            ActionExpectation(
                actions.Migration,
                {'revisions': list(reversed(revisions)),
                 'num_revisions_to_migrate': -1,
                 }, self)
            ]
        )

  def testMultipleExports(self):
    db = test_util.MockDbClient()
    equiv = base.Correspondence('1001', '1')
    db.NoteEquivalence(equiv)

    revisions = [base.Revision('1003'), base.Revision('1002')]
    internal_repos = test_util.MockRepository(
        'test_internal', '1001',
        revisions_since_equivalence_results=(revisions, [equiv]))
    public_repos = test_util.MockRepository(
        'test_public', '1',
        revisions_since_equivalence_results=([], [equiv]))
    repository_configs = {
        'test_internal': (internal_repos, None),
        'test_public': (public_repos, None),
        }

    self.RunScenario(
        db, repository_configs,
        self._ECs('1001', '1') + [
            ActionExpectation(
                actions.Migration,
                {'revisions': list(reversed(revisions)),
                 'num_revisions_to_migrate': 1,
                 }, self)
            ],
        project_config_name='separate_revisions_project_config.txt',
        )

if __name__ == '__main__':
  basetest.main()
