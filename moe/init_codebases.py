#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.

"""Initialize a project for use with manage_codebases.

Usage:
  init_codebases --project_config_file <config file> --internal_revision
                 <revision> [--public_revision <revision>]

Set up a project with the MOE DB for use with manage_codebases. If the
  public repository already has a revision which is equivalent to a revision
  in the internal repository, specify it with --public_revision. Otherwise, this
  will export the internal repository.

After using this, the project should be usable with
  $ manage_codebases --project <project name>
"""



import getpass

from google.apputils import app
from google.apputils import appcommands
import gflags as flags

from moe import actions
from moe import base
from moe import db_client
from moe import moe_app
from moe import push_codebase

FLAGS = flags.FLAGS

def DefineFlags(flag_values):
  flags.DEFINE_integer('internal_revision', -1,
                       'The internal revision to sync to. Should be the most '
                       'recent green revision.',
                       flag_values=flag_values)
  flags.DEFINE_string('public_revision', '',
                      'The public revision in equivalence with the given '
                      'internal revision',
                      flag_values=flag_values)


class InitCodebasesContext(object):
  """Context for initializing a MOE project."""

  def __init__(self, project, report, db, internal_revision,
               public_revision=''):
    self.project = project
    self._db = db
    self._internal_revision = internal_revision
    self._public_revision = public_revision
    self.report = report
    self._temp_dir = moe_app.RUN.temp_dir

    self._expander = moe_app.RUN.expander

    (self._internal_repository, self._internal_codebase_creator) = (
        project.internal_repository.MakeRepository(self._temp_dir,
                                                   self._expander))
    self._internal_revision_obj = self._internal_repository.MakeRevisionFromId(
        self._internal_repository.GetHeadRevision(self._internal_revision))

    (self._public_repository, self._public_codebase_creator) = (
        project.public_repository.MakeRepository(self._temp_dir,
                                                 self._expander))

  def InitializeProject(self):
    """Initialize a MOE project.

    Export the internal codebase to the public repository if there is
    not yet an equivalent version there, then note an equivalence.
    """
    if not self._public_revision:
      source = self._internal_codebase_creator.Create(
          self._internal_revision_obj.rev_id)

      export_strategy = self.project.export_strategy
      public_config = self.project.public_repository

      done = False
      while not done:
        response = raw_input('Would you like to automatically commit the '
                             'codebase generated from revision %s to the '
                             'public repository (y/n)? ' %
                             self._internal_revision_obj.rev_id)
        if response.lower() == 'y':
          export_strategy.commit_strategy = 'commit_remotely'
          print ('Note: Use your code.google.com login. It should use your '
                 'username@google.com, but not your LDAP password. You can '
                 'check your googlecode.com password at '
                 'https://code.google.com/hosting/settings')
          username = raw_input('Public repository username: ')
          password = getpass.getpass('Public repository password: ')
          done = True
        elif response.lower() == 'n':
          export_strategy.commit_strategy = 'leave_pending'
          username = public_config.username
          password = public_config.password
          done = True

      public_client = self._public_repository.MakeClient(
          self._temp_dir, username=username, password=password)
      public_editor = public_client.MakeEditor(
          export_strategy, revisions=[self._internal_revision_obj])

      pusher_args = {
          'source_codebase': source,
          }
      export_step = self.report.AddStep('export_changes',
                                        'push_codebase',
                                        cmd_args=pusher_args)
      pusher = push_codebase.CodebasePusher(
          source_codebase=source,
          destination_editor=public_editor,
          report=self.report,
          commit_message=self._internal_revision_obj.changelog)
      self._public_revision = pusher.Push()

      if pusher.pushed:
        if self._public_revision:
          export_step.SetResult('Export completed')
        else:
          export_step.SetResult('Export ready for human intervention')
          self.report.AddTodo('After committing this change, go to '
                              '%s to note the equivalence for project %s.'
                              % (self._db.GetDashboardUrl(), self.project.name))
      else:
        export_step.SetResult('Nothing to export')

    if self._public_revision:
      try:
        check = actions.EquivalenceCheck(
            self._internal_revision_obj.rev_id,
            self._public_revision, self.project,
            actions.EquivalenceCheck.NoteIfSameErrorIfDifferent)
        check.Perform(
            self._internal_codebase_creator, self._public_codebase_creator,
            self.report, self._db, self._temp_dir, [])
        self.report.AddTodo('Project in equivalence. Begin managing by '
                            'running [ manage_codebases --project %s ]'
                            % self.project.name)
      except base.Error, e:
        print e
        print ('The given two revisions (internal %(irev)s, public %(prev)s) '
               'are not equivalent. Check for two revisions that are '
               'equivalent, or run [ init_codebases --project_config_file '
               '%(pcfg)s --internal_revision %(irev)s ] to export a new '
               'revision that is equivalent to revision %(irev)s.'
               % {'irev': self._internal_revision_obj.rev_id,
                  'prev': self._public_revision,
                  'pcfg': FLAGS.project_config_file})


def main(unused_argv):
  project, db = db_client.MakeProjectAndDbClient(
      create_project=True, acquire_lock=False)

  try:
    moe_app.Init(project.name)
    internal_revision = FLAGS.internal_revision
    if internal_revision <= 0:
      raise app.UsageError('Must supply a revision using --internal_revision '
                           'flag.')
    public_revision = FLAGS.public_revision
    context = InitCodebasesContext(
        project, moe_app.RUN.report, db,
        str(internal_revision), public_revision)
    context.InitializeProject()
    context.report.PrintSummary()
  finally:
    db.Disconnect()


class InitCmd(appcommands.Cmd):
  def __init__(self, name, flag_values):
    appcommands.Cmd.__init__(self, name, flag_values)
    DefineFlags(flag_values)

  def Run(self, argv):
    main(argv)


if __name__ == '__main__':
  DefineFlags(FLAGS)
  app.run()
