#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Actions are the steps MOE performs to manage codebases."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import copy

from moe import base
from moe import codebase_utils
from moe import config
from moe import db_client
from moe import merge_codebases
from moe import moe_app
from moe import push_codebase
from moe.translators import translators

class Action(object):
  """An Action is a step in managing codebases."""

  def __init__(self, project):
    """Initialize.

    Args:
      project: config.MoeProjectConfig
    """
    assert isinstance(project, config.MoeProjectConfig), (
        'Expected MoeProjectConfig')
    self.project = project

  def Perform(self, **unused_kwargs):
    """Perform the action, and determine next actions.

    Args:
      various kwargs from **ActionState.Dict()

    Returns:
      StateUpdate, an update to the state of the Action sequence
    """
    raise NotImplementedError


class ActionState(object):
  """The state of an executing sequence of Actions."""

  def __init__(self, internal_codebase_creator, public_codebase_creator,
               report, db, temp_dir, actions):
    """Construct.

    Args:
      internal_codebase_creator: codebase_utils.CodebaseCreator
      public_codebase_creator: codebase_utils.CodebaseCreator
      report: config.MoeReport
      db: moe_db.MoeDbClient
      temp_dir: str, path to a tempoprary directory
      actions: sequence of Action
    """
    self.internal_codebase_creator = internal_codebase_creator
    self.public_codebase_creator = public_codebase_creator
    self.report = report
    self.db = db
    self.temp_dir = temp_dir
    self.actions = actions

  def Dict(self):
    """Returns a dictionary representation of the state."""
    return {'internal_codebase_creator': self.internal_codebase_creator,
            'public_codebase_creator': self.public_codebase_creator,
            'report': self.report,
            'db': self.db,
            'temp_dir': self.temp_dir,
            'actions': self.actions,
           }

  def MergeUpdate(self, update):
    """Updates the state.

    Args:
      update: StateUpdate
    """
    if not update:
      return

    if update.actions is not None:
      self.actions = update.actions


class StateUpdate(object):
  """An update the the state of the executing sequence of Actions."""

  def __init__(self, actions=None):
    """Construct.

    Args:
      actions: list of Actions, the list of actions to execute after this
               one, or None to continue executing the previous list of
               Actions
    """
    self.actions = actions

  def __eq__(self, other):
    return (other and
            self.actions == other.actions)


class EquivalenceCheck(Action):
  """Check if an Equivalence exists between an internal and public revision."""

  def __init__(self, internal_revision, public_revision, project,
               translators, result_dispatch):
    """Construct.

    Args:
      internal_revision: str, the internal revision
      public_revision: str, the public revision
      project: config.MoeProjectConfig
      translators: seq of translators.Translator
      result_dispatch: function, will be called with the results of
                       Perform and must return a list of actions

    """
    Action.__init__(self, project)
    self.internal_revision = internal_revision
    self.public_revision = public_revision
    self.translators = translators
    self.result_dispatch = result_dispatch

  def Perform(self, internal_codebase_creator, public_codebase_creator,
              report, db, temp_dir, actions,
              **unused_kwargs):
    """Perform the action, and determine next actions.

    Args:
      internal_codebase_creator: codebase_utils.CodebaseCreator
      public_codebase_creator: codebase_utils.CodebaseCreator
      report: config.MoeReport
      db: moe_db.MoeDbClient
      temp_dir: str, path to a tempoprary directory
      actions: sequence of Action

    Returns:
      StateUpdate, an update to the state of the Action sequence
    """
    task = moe_app.RUN.ui.BeginIntermediateTask(
        'equivalence_check',
        ('Checking for an Equivalence between internal revision %s and '
         'public revision %s') % (self.internal_revision, self.public_revision))
    with task:
      internal = internal_codebase_creator.Create(self.internal_revision)
      generated = translators.TranslateToProjectSpace(
          internal, base.PUBLIC_STR,
          self.translators)
      public = public_codebase_creator.Create(self.public_revision)
      codebases_differ = None
      if not self.project.manual_equivalence_deltas:
        codebases_differ = base.AreCodebasesDifferent(
            generated, public,
            noisy_files_re=self.project.noisy_files_re)

      return self.result_dispatch(self,
                                  codebases_differ=codebases_differ,
                                  generated=generated,
                                  public=public,
                                  db=db,
                                  report=report,
                                  actions=actions)

  def _NoteEquivalence(self, db, report):
    equivalence = db_client.Equivalence(
        self.internal_revision, self.public_revision)
    db.NoteEquivalence(equivalence)
    report.AddStep(
        'note_equivalence', cmd='moe_db note_equivalence',
        cmd_args=dict(
            internal_revision=self.internal_revision,
            public_revision=self.public_revision))
    return equivalence

  def _DifferenceError(self, codebases_differ, generated, public):
    if codebases_differ.codebase1_only:
      print 'Files that exist only in generated codebase: '
      for f in codebases_differ.codebase1_only:
        print ' ', f
    if codebases_differ.codebase2_only:
      print 'Files that exist only in public codebase: '
      print '(Cf. public_repository:additional_files_re in your moe_config)'
      for f in codebases_differ.codebase2_only:
        print ' ', f
    raise base.Error(
        ('Equivalence is not equivalent.\n'
         'Reason: %s\n'
         'internal: %s \n (viewable at %s )\n'
         'public: %s\n (viewable at %s )') %
        (str(codebases_differ),
         self.internal_revision, generated.ExpandedPath(),
         self.public_revision, public.ExpandedPath()))

  # Possible functions for result_dispatch

  def ErrorIfDifferent(self, codebases_differ, generated, public,
                       **unused_kwargs):
    if codebases_differ:
      self._DifferenceError(codebases_differ, generated, public)
    else:
      return None

  def NoteIfSame(self, codebases_differ, db, report, **unused_kwargs):
    if not codebases_differ:
      self._NoteEquivalence(db, report)

  def NoteAndStopIfSame(self, codebases_differ, db, report, **unused_kwargs):
    if not codebases_differ:
      self._NoteEquivalence(db, report)
      return StateUpdate(actions=[])

  def NoteIfSameErrorIfDifferent(self, codebases_differ, generated, public, db,
                                 report, **unused_kwargs):
    if codebases_differ:
      self._DifferenceError(codebases_differ, generated, public)
    else:
      self._NoteEquivalence(db, report)


class MigrationConfig(object):
  """Configuration for the direction and strategy of a migration."""

  def __init__(self, direction, source_codebase_creator,
               source_repository_config,
               target_codebase_creator, target_repository_config,
               target_repository,
               migration_strategy):
    """Construct.

    Args:
      direction: one of base.Migration.DIRECTION_VALUES
      source_codebase_creator: codebase_utils.CodebaseCreator
      source_repository_config: base.RepositoryConfig
      target_codebase_creator: codebase_utils.CodebaseCreator
      target_repository_config: base.RepositoryConfig
      target_repository: base.SourceControlRepository
      migration_strategy: config.MigrationStrategy
    """
    self.direction = direction
    self.source_codebase_creator = source_codebase_creator
    self.source_repository_config = source_repository_config
    self.target_codebase_creator = target_codebase_creator
    self.target_repository_config = target_repository_config
    self.target_repository = target_repository
    self.migration_strategy = migration_strategy

  def IsExport(self):
    """Whether this is an export configuration."""
    return self.direction == base.Migration.EXPORT

  def IsImport(self):
    """Whether this is an import configuration."""
    return self.direction == base.Migration.IMPORT


class Migration(Action):
  """Import or export code (if necessary)."""

  def __init__(self,
               previous_revision,
               applied_against,
               revisions,
               project,
               translators,
               migration_config,
               mock_migration, num_revisions_to_migrate):
    """Construct.

    Args:
      previous_revision: base.Revision
      applied_against: base.Revision
      revisions: list of base.Revision, the revisions to export
      project: config.MoeProjectContext
      translators: seq of translators.Translator
      migration_config: MigrationConfig, the configuration for this migration
      mock_migration: bool, whether to only mock the migrations (i.e. inform
                      the database only)
      num_revisions_to_migrate: int, the number of revisions to migrate
                            (-1 means take all)
    """
    Action.__init__(self, project)
    self.previous_revision = previous_revision
    self.applied_against = applied_against
    self.revisions = revisions
    self.translators = translators
    self.migration_config = migration_config
    self.mock_migration = mock_migration
    self.num_revisions_to_migrate = num_revisions_to_migrate

  def Perform(self, report=None, db=None, actions=None, **unused_kwargs):
    """Perform the action, and determine next actions.

    Args:
      report: base.MoeReport
      db: moe_db.MoeDbClient
      temp_dir: str, path to a tempoprary directory
      actions: seq of Action, the actions to run after this

    Returns:
      StateUpdate, an update to the state of the Action sequence
    """
    actions = actions or []

    if not self.revisions:
      return

    if self.num_revisions_to_migrate == -1:
      migration_revisions = self.revisions
      remaining_revisions = []
    else:
      migration_revisions = self.revisions[:self.num_revisions_to_migrate]
      remaining_revisions = self.revisions[self.num_revisions_to_migrate:]

    up_to_revision = migration_revisions[-1]

    task = moe_app.RUN.ui.BeginIntermediateTask(
        'migrate',
        'Migrating up to revision %s by applying it against %s' %
        (up_to_revision.rev_id, self.applied_against.rev_id))

    with task:
      if remaining_revisions:
        result_migration = Migration(
            up_to_revision,
            self.applied_against,
            remaining_revisions,
            self.project,
            self.translators,
            self.migration_config, self.mock_migration, 1)
        result_migration_list = [result_migration]
        result = StateUpdate(actions=[result_migration] + actions)
      else:
        result_migration = None
        result_migration_list = []
        result = None

      previous_source = self.migration_config.source_codebase_creator.Create(
          self.previous_revision.rev_id)
      try:
        source = self.migration_config.source_codebase_creator.Create(
            up_to_revision.rev_id)
        translated_source = translators.TranslateToProjectSpace(
            source,
            self.migration_config.target_codebase_creator.ProjectSpace(),
            self.translators)
      except base.CodebaseCreationError:
        if not remaining_revisions:
          # This is an error at the last revision
          # It might be better if we just marked it as an error.
          raise
        # In this case, we can't migrate the up_to_revision. So instead, we
        # fold it into the next migration.
        action = Migration(
            self.previous_revision,
            self.applied_against,
            self.revisions,
            self.project,
            self.translators,
            self.migration_config, self.mock_migration,
            self.num_revisions_to_migrate + 1)
        return StateUpdate(actions=[action] + actions)

      should_migrate = bool(base.AreCodebasesDifferent(
          previous_source, source, noisy_files_re=self.project.noisy_files_re))
      if not should_migrate:
        return result

      migration_strategy = copy.copy(self.migration_config.migration_strategy)

      if migration_strategy.merge_strategy == base.ERROR:
        raise base.Error('Attempted %s invalid with merge strategy.' %
                         self.migration_config.direction)

      migration = db.FindMigration(up_to_revision, abbreviated=False)
      if (not migration or
          (migration.status == base.Migration.CANCELED)):
        changelog = base.ConcatenateChangelogs(migration_revisions)
        creator = self.migration_config.source_codebase_creator
        pre_approved = (migration_strategy.preapprove_public_changelogs and
                        all([r.pre_approved for r in migration_revisions]))
        migration_id = db.StartMigration(
            self.migration_config.direction,
            up_to_revision,
            changelog=changelog,
            migrated_revisions=migration_revisions,
            pre_approved=pre_approved)
      elif migration.status == base.Migration.SUBMITTED:
        # TODO(dbentley): this should never happen
        find_step = moe_app.RUN.report.AddStep(
            'migrate_changes', 'find_migration')
        find_step.SetResult('%s of revisions [%s, %s] has '
                            'already been submitted in migration %s.' %
                            (self.migration_config.direction,
                             self.start_migrated_revision,
                             end_migrated_revision,
                             migration.migration_id))
        return result
      else:
        changelog = migration.changelog
        migration_id = migration.migration_id
        if migration.status == base.Migration.APPROVED:
          # TODO(dbentley): should we do this only if it's somewhere in the
          # project config?
          migration_strategy.commit_strategy = base.COMMIT_REMOTELY

      if self.mock_migration:
        return result

      base_codebase = self.migration_config.target_codebase_creator.Create(
          self.applied_against.rev_id)
      merge_context = None
      if migration_strategy.merge_strategy == base.MERGE:
        merge_args = dict(previous_codebase=previous_source)
        if self.migration_config.IsExport():
          merge_args['generated_codebase'] = translated_source
          merge_args['public_codebase'] = base_codebase
        elif self.migration_config.IsImport():
          merge_args['generated_codebase'] = base_codebase
          merge_args['public_codebase'] = translated_source
        merge_config = merge_codebases.MergeCodebasesConfig(**merge_args)
        merge_context = merge_codebases.MergeCodebasesContext(
            merge_config)
        merge_context.Update()
        p_s = self.migration_config.target_codebase_creator.ProjectSpace()
        codebase_to_push = codebase_utils.Codebase(
            merge_context.config.merged_codebase,
            expanded_path=merge_context.config.merged_codebase,
            project_space=p_s)
      else:
        codebase_to_push = translated_source

      editor = base_codebase.MakeEditor(migration_strategy, migration_revisions)

      source_repository_config = self.migration_config.source_repository_config
      # TODO(dbentley): setting additional_files_re to this is almost
      # certainly superfluous now. But... I'm not completely sure I'm right
      # about that, so I'll do it in a separate change.
      additional_files_re = (
          self.project.public_repository_config.additional_files_re)

      push_codebase_args = dict(
          source_codebase=codebase_to_push.Path(),
          destination_editor=editor.Root(),
          destination_revision=self.applied_against.rev_id,
          source_revision=up_to_revision.rev_id)

      pusher = push_codebase.CodebasePusher(
          source_codebase=codebase_to_push,
          destination_editor=editor,
          report=moe_app.RUN.report,
          files_to_ignore_re=additional_files_re,
          commit_message=changelog,
          migration_id=migration_id
          )
      commit_id = pusher.Push()

      if pusher.pushed:
        db.UpdateMigrationDiff(migration_id, diff=editor.Diff(),
                               link=editor.Link())
        if commit_id:
          moe_app.RUN.ui.Info('%s completed' %
                              self.migration_config.direction)
          r = self.migration_config.target_repository.MakeRevisionFromId(
              commit_id)
          db.FinishMigration(migration_id, r)
          if self.migration_config.direction == base.Migration.EXPORT:
            internal_rev = migration_revisions[-1].rev_id
            public_rev = commit_id
          elif self.migration_config.direction == base.Migration.IMPORT:
            internal_rev = commit_id
            public_rev = migration_revisions[-1].rev_id
          equivalence_check = EquivalenceCheck(
              internal_rev, public_rev, self.project, self.translators,
              EquivalenceCheck.NoteIfSame)
          update = StateUpdate(actions=[equivalence_check] +
                               result_migration_list + actions)
          return update
        else:
          moe_app.RUN.ui.Info('%s ready for human intervention' %
                              self.migration_config.direction)
          if merge_context and merge_context.failed_merges:
            moe_app.RUN.report.AddTodo(
                'Resolve failed merges in %s' %
                base_codebase.Client().directory)
            moe_app.RUN.report.SetReturnCode(2)
          if self.migration_config.IsExport():
            moe_app.RUN.report.AddTodo(
                "Alternately, visit your project's MOE dashboard at "
                '%s , approve each migration, then rerun '
                'manage_codebases.' % db.GetDashboardUrl())
          if remaining_revisions:
            # We committed as requested, but this did not leave a permanent
            # commit. (probably because it wasn't approved on the db).
            # We should no longer continue committing this line of migrations,
            # but we should upload them to the db so they can be approved.

            # TODO(dbentley): no, we shouldn't. We should just quit.
            # But we should quit in a classy way. And explain to the user
            # why we're quitting.
            result_migration = Migration(
                up_to_revision,
                self.applied_against,
                remaining_revisions,
                self.project,
                self.translators,
                self.migration_config,
                True,
                1
                )
            return StateUpdate(actions=[result_migration] + actions)
          else:
            # There are no revisions left to migrate in this direction,
            # so make sure we don't migrate the other way
            if actions:
              for action in actions:
                if isinstance(action, Migration):
                  action.mock_migration = True
              return StateUpdate(actions=actions)
            else:
              return None
      else:
        db.CancelMigration(migration_id)
        # TODO(dbentley): should this Info() (and others in this file) be
        # in some way connected as the result of the current task?
        moe_app.RUN.ui.Info('%s resulted in a no-op' %
                            self.migration_config.direction)
        return result
