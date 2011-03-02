#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""manage_codebases examines a MOE project and does what's needed.

Usage:
  manage_codebases --project_config_file <config_file>

Returns:
0: no changes to be migrated
1: change ready to be submitted
2: change migration attempted, but requires human intervention
"""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import getpass

from google.apputils import app
from google.apputils import appcommands
import gflags as flags
from moe import actions
from moe import base
from moe import db_client
from moe import logic
from moe import moe_app

FLAGS = flags.FLAGS

def DefineFlags(flag_values):
  flags.DEFINE_integer('internal_revision', -1,
                       'The internal revision to sync to. Should be the most '
                       'recent green revision.',
                       flag_values=flag_values)


class Book(object):
  """The "Book" that is kept by MOE.

  This is a description of what state MOE's in.
  """

  def __init__(self,
               equivalence,
               current,
               finished_imports,
               finished_exports,
               revisions_to_export,
               last_export,
               revisions_to_import,
               last_import
               ):
    """Construct.

    Args:
      equivalence: base.Correspondence
      current: base.Correspondence
      finished_imports: seq of base.Migration
      finished_exports: seq of base.Migration
      revisions_to_export: seq of base.Revision
      last_export: base.Migration (possibly None)
      last_revision_exported: base.Revision
      revisions_to_import: seq of base.Revision
      last_import: base.Migration (possibly None)
    """
    self.equivalence = equivalence
    self.current = current
    self.finished_imports = finished_imports
    self.finished_exports = finished_exports
    self.revisions_to_export = revisions_to_export
    self.last_export = last_export
    self.revisions_to_import = revisions_to_import
    self.last_import = last_import

  def Describe(self):
    """Describe to the user what the state is to do."""
    print 'EQUIVALENCE: internal revision: "%s", public revision: "%s"' % (
        self.equivalence.internal_revision, self.equivalence.public_revision)
    print 'CURRENT: internal revision: "%s", public revision: "%s"' % (
        self.current.internal_revision, self.current.public_revision)
    print 'REVISIONS TO IMPORT:'
    for r in self.revisions_to_import:
      print ' ', r.rev_id, r.single_scrubbed_log[0:60].replace('\n', ' ')
    print 'REVISIONS TO EXPORT:'
    for r in self.revisions_to_export:
      print ' ', r.rev_id, r.single_scrubbed_log[0:60].replace('\n', ' ')


class ManageCodebasesContext(object):
  """Context for a run of ManageCodebases.

  Attributes:
    project: config.MoeProject
  """

  def __init__(self, project, internal_revision=-1):
    """Construct.

    Args:
      project: moe_project.MoeProjectContext, the project to use
      internal_revision: str, the internal revision to sync to, or -1 to use
                         HEAD

    Raises:
      Error: if multiple repository URLs are specified in the project.
    """
    self.project = project

    print 'Managing Codebases for MOE project', project.config.name

    self._temp_dir = moe_app.RUN.temp_dir
    self._report = moe_app.RUN.report

    # TODO(dbentley): storing this here feels wrong. If there get
    # to be more of these, there should be a ManageCodebasesSetting to hold
    # these.
    self._internal_revision = internal_revision

    self.return_code = 0

  def _PerformBookkeeping(self, current):
    """Perform book-keeping to understand what MOE had done/needs to do.

    This includes looking at source control and talking to the MOE db.

    Returns:
      Book, what MOE needs to do.
    """

    task = moe_app.RUN.ui.BeginImmediateTask(
        'verify_equivalences',
        'Verifying Equivalences')

    with task:
      logic.VerifyEquivalences(self.project.db,
                               self.project.internal_repository,
                               self.project.public_repository)

    task = moe_app.RUN.ui.BeginImmediateTask(
        'revisions_since_equivalence',
        'Finding internal revision at equivalence')
    with task:
      (i_r_since_equivalence, internal_candidate_equivalences) = (
          self.project.internal_repository.RevisionsSinceEquivalence(
              current.internal_revision, base.INTERNAL, self.project.db))
      task.SetResult(internal_candidate_equivalences[0].internal_revision)

    task = moe_app.RUN.ui.BeginImmediateTask(
        'revisions_since_equivalence',
        'Finding public revision at equivalence')
    with task:
      (p_r_since_equivalence, public_candidate_equivalences) = (
          self.project.public_repository.RevisionsSinceEquivalence(
              current.public_revision, base.PUBLIC, self.project.db))
      task.SetResult(public_candidate_equivalences[0].public_revision)

    equivalence = None
    # Ensure there is a compatible equivalence.
    for i_c_e in internal_candidate_equivalences:
      for p_c_e in public_candidate_equivalences:
        if (i_c_e.internal_revision == p_c_e.internal_revision and
            i_c_e.public_revision == p_c_e.public_revision):
          equivalence = i_c_e
          break
    if not equivalence:
      raise base.Error(
          ("Did not find a compatible equivalence. "
           "This is a surprising event. Email moe-team@ with this output.\n"
           "Internal Candidate Equivalences: %s\n"
           "Public Candidate Equivalences: %s\n"
           ) % ([str(e) for e in internal_candidate_equivalences],
                [str(e) for e in public_candidate_equivalences]))

    # Retire migrations
    # We need to do this first, so the next step can see them
    task = moe_app.RUN.ui.BeginImmediateTask(
        'finish_imports',
        'Examining internal revisions for finished imports')
    with task:
      finished_imports = self._RetireMigrations(i_r_since_equivalence)

    task = moe_app.RUN.ui.BeginImmediateTask(
        'finish_exports',
        'Examining public revisions for finished exports')
    with task:
      finished_exports = self._RetireMigrations(p_r_since_equivalence)

    # Now, we find migrations that need to migrated.
    # We go through all revisions from newest to oldest until we find one that
    # has already been migrated.
    task = moe_app.RUN.ui.BeginImmediateTask(
        'internal_revisions_to_migrate',
        'Determining which internal revisions need to be exported')
    with task:
      revisions_to_export, last_export = self._RevisionsToMigrate(
          i_r_since_equivalence, base.INTERNAL)

    task = moe_app.RUN.ui.BeginImmediateTask(
        'public_revisions_to_migrate',
        'Determining which public revisions need to be imported')
    with task:
      revisions_to_import, last_import = self._RevisionsToMigrate(
          p_r_since_equivalence, base.PUBLIC)

    task = moe_app.RUN.ui.BeginImmediateTask(
        'noting_revisions',
        'Uploading information about revisions to MOE db')
    with task:
      self.project.db.NoteRevisions(revisions_to_export)
      self.project.db.NoteRevisions(revisions_to_import)

    return Book(
        equivalence,
        current,
        finished_imports,
        finished_exports,
        revisions_to_export,
        last_export,
        revisions_to_import,
        last_import,
        )

  def _RetireMigrations(self, revisions):
    """Find all migrations that were submitted in revisions and deal with them.

    Revisions that contain the string MOE_MIGRATION= are being migrated. When
      we see this revision, we should tell the DB that it's finished. We should
      also consider it when trying to find equivalences.

    Args:
      revisions: seq of base.Revision.

    Returns:
      seq of base.Migrations
    """
    result = []
    for r in revisions:
      if r.migration:
        self.project.db.FinishMigration(r.migration, r)

        try:
          # This will fail if a migration has been cancelled.
          migration = self.project.db.GetMigration(r.migration)
        except base.Error, e:
          migration = None

        if migration:
          result.append(migration)
    return result

  def _RevisionsToMigrate(self, revisions_since_equivalence, which_repository):
    """Determine which migrations need to be migrated.

    We look at all revisions since an equivalence (we know that any revisions
      earlier than that don't need to be migrated). We figure out which
      have been migrated, and which need to be.

    We return a tuple of:
      (migrations that need to be returned,
       the latest completed migration or None)
      NB: None for the migration implies that no migrations in this direction
      have been completed since the equivalence.

    Args:
      revisions_since_equivalence: seq of base.Revision
      which_repository: base.{INTERNAL, PUBLIC}

    Returns:
      (seq of base.Revision, base.Migration (possibly None))
    """
    last_migration = None
    revisions_to_migrate = []
    for r in revisions_since_equivalence:
      m = self.project.db.HasRevisionBeenMigrated(r)
      if m and m.status == base.Migration.SUBMITTED:
        if not m.submitted_as:
          raise base.Error(
              'Migration has no submitted as. Contact moe-team@. '
              'Migration ID: %s %s' % (m.migration_id, m.up_to_revision.rev_id))
        # Everything before this revision has been migrated.
        last_migration = m
        break
      revisions_to_migrate.append(r)
    revisions_to_migrate = list(reversed(revisions_to_migrate))
    return revisions_to_migrate, last_migration

  def _ChooseActions(self, book):
    """Choose the actions we should perform.

    Args:
      book: Book, the book

    Returns:
      sequence of Actions

    NB(dbentley): an Action will, when performed, have the chance to modify
    the Actions performed after it.
    """
    result = []

    # TODO(dbentley): Here is where we should determine what we are going
    # to do in this run.

    # First, we check that an equivalence is, in fact, equivalent
    result.append(actions.EquivalenceCheck(
        book.equivalence.internal_revision,
        book.equivalence.public_revision,
        self.project.config,
        actions.EquivalenceCheck.ErrorIfDifferent))

    # Next, we check newly-finished migrations.
    # Specifically, we think the up_to_revision and submitted_as may be
    # equivalent.
    for m in book.finished_imports:
      result.append(actions.EquivalenceCheck(
          m.submitted_as.rev_id, m.up_to_revision.rev_id, self.project.config,
          actions.EquivalenceCheck.NoteIfSame))

    for m in book.finished_exports:
      result.append(actions.EquivalenceCheck(
          # Note the different order of arguments
          m.up_to_revision.rev_id, m.submitted_as.rev_id, self.project.config,
          actions.EquivalenceCheck.NoteIfSame))

    # At this point, we're just trying to see if we happen to be lucky.
    # We could check all pairs of revisions, but that's expensive.
    # Instead, we just see if we happen to be equivalent.
    result.append(actions.EquivalenceCheck(
        book.current.internal_revision,
        book.current.public_revision,
        self.project.config, actions.EquivalenceCheck.NoteAndStopIfSame))


    if book.revisions_to_import:
      import_config = actions.MigrationConfig(
          base.Migration.IMPORT,
          self.project.public_codebase_creator,
          self.project.config.public_repository_config,
          self.project.internal_codebase_creator,
          self.project.config.internal_repository_config,
          self.project.internal_repository,
          self.project.config.import_strategy)

      # TODO(dbentley): we can't handle separate revisions from
      # a repository that is a DVCS. We should check this.
      if self.project.config.import_strategy.separate_revisions:
        num_revisions_to_migrate = 1
      else:
        num_revisions_to_migrate = -1

      # Which public revision should we apply this migration against?
      # We should apply it against the public revision that corresponds to the
      # last internal revision to get exported. This is probably the last
      # export. But an equivalence will do too. So use last export, and if
      # it doesn't exist, use equivalence.
      if book.last_import:
        previous_revision = book.last_import.up_to_revision
        applied_against = book.last_import.submitted_as
      else:
        previous_revision = self.project.public_repository.MakeRevisionFromId(
            book.equivalence.public_revision)
        applied_against =  self.project.internal_repository.MakeRevisionFromId(
            book.equivalence.internal_revision)

      result.append(actions.Migration(
          previous_revision, applied_against,
          book.revisions_to_import,
          self.project.config,
          import_config, False, num_revisions_to_migrate))

    # TODO(dbentley): we should only do one of importing or exporting per run.
    if book.revisions_to_export:
      # Choose exports
      export_config = actions.MigrationConfig(
          base.Migration.EXPORT,
          self.project.internal_codebase_creator,
          self.project.config.internal_repository_config,
          self.project.public_codebase_creator,
          self.project.config.public_repository_config,
          self.project.public_repository,
          self.project.config.export_strategy)

      if self.project.config.export_strategy.separate_revisions:
        num_revisions_to_migrate = 1
      else:
        num_revisions_to_migrate = -1

      # Choose correspondence to migrate against (as described above).
      if book.last_export:
        previous_revision = book.last_export.up_to_revision
        applied_against = book.last_export.submitted_as
      else:
        previous_revision = self.project.internal_repository.MakeRevisionFromId(
            book.equivalence.internal_revision)
        applied_against =  self.project.public_repository.MakeRevisionFromId(
            book.equivalence.public_revision)

      result.append(actions.Migration(
          previous_revision, applied_against,
          book.revisions_to_export,
          self.project.config, export_config, False, num_revisions_to_migrate))

    return result

  def ManageCodebases(self):
    """Manage codebases. This is the entry point to the one-button MOE."""
    try:
      if self._internal_revision == -1:
        internal_revision = None
      else:
        internal_revision = str(self._internal_revision)

      task = moe_app.RUN.ui.BeginImmediateTask(
          'get_internal_head',
          'Determining current internal revision '
          '(override with --internal_revision)')
      with task:
        current_internal_revision = (
            self.project.internal_repository.GetHeadRevision(
                internal_revision))
        task.SetResult(current_internal_revision)

      task = moe_app.RUN.ui.BeginImmediateTask(
          'get_public_head',
          'Determining current public revision')
      with task:
        current_public_revision = (self.project.public_repository.
                                   GetHeadRevision())
        task.SetResult(current_public_revision)

      current = base.Correspondence(current_internal_revision,
                                    current_public_revision)

      book = self._PerformBookkeeping(current)

      book.Describe()

      actionlist = self._ChooseActions(book)
      state = actions.ActionState(
          self.project.internal_codebase_creator,
          self.project.public_codebase_creator,
          # TODO(dbentley): get rid of report and temp_dir
          self._report, self.project.db, self._temp_dir, actionlist)
      while actionlist:
        (current_action, state.actions) = (actionlist[0], actionlist[1:])
        result = current_action.Perform(**state.Dict())
        state.MergeUpdate(result)
        actionlist = state.actions

      self._report.PrintSummary()
      self.return_code = self._report.GetReturnCode()
    finally:
      self.project.db.Disconnect()


def ChooseMigrations(repository, start, end, target,
                     equivalence, project, migration_config):
  """Choose how to clump revisions into migrations.

  Args:
    repository: base.CodebaseRepository
    start: str, the first revision not to choose
    end: str, the last revision to choose
    target: str, the revision in the target repository against which the
            migrations are to be made
    equivalence: base.Correspondence, an equivalence
    project: config.MoeProject
    migration_config: actions.MigrationConfig

  Returns:
    sequence of Actions
  """
  revisions = repository.GetRevisions(start, end)
  if not revisions:
    return []

  # TODO(dbentley): we can't handle separate_revisions from dvcs's
  if migration_config.migration_strategy.separate_revisions:
    num_revisions_to_migrate = 1
  else:
    num_revisions_to_migrate = -1

  # TODO(dbentley): we shouldn't just set False.
  return [actions.Migration(
      start, target, revisions, project.config, migration_config, False,
      num_revisions_to_migrate)]


def main(unused_argv):
  project = db_client.MakeProjectContext()
  try:
    context = ManageCodebasesContext(
        project,
        internal_revision=FLAGS.internal_revision)
    context.ManageCodebases()

    return context.return_code
  finally:
    project.db.Disconnect()


class AutoCmd(appcommands.Cmd):
  def __init__(self, name, flag_values):
    appcommands.Cmd.__init__(self, name, flag_values)
    DefineFlags(flag_values)

  def Run(self, argv):
    main(argv)


if __name__ == '__main__':
  DefineFlags(FLAGS)
  app.run()
