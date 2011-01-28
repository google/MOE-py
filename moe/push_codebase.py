#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.

"""Push a codebase to source control.

Usage:
  push_codebase --project=<PROJECT_NAME> --destination=<internal|public>
                [--codebase=<CODEBASE>]

Uses the project config (either explicitly given as --project_config_file or
  loaded from the db with --project) to know whence to get the code and/or
  whither to push it.

Examples:
  push_codebase --project <PROJECT_NAME> --destination public

will:
1) generate the public codebase from internal head
2) check out head revision from public version control
3) edit that client until it matches what's in the generated tarball

If we wanted to instead push what's in the public VCS into internal, we'd run:
  push_codebase --project jscomp --destination internal

If we had a directory containing a patched public client and we wanted to
undo the renaming and scrubbing to create an internal patch, we'd run:
  push_codebase --project jscomp --destination internal --codebase /path/to/foo
"""

__author__ = 'dbentley@google.com (Dan Bentley)'

import os
import re
import sys

from google.apputils import app
from google.apputils import appcommands
import gflags as flags

from moe import base
from moe import codebase_utils
from moe import config
from moe import db_client
from moe import moe_app


FLAGS = flags.FLAGS


def DefineFlags(flag_values):
  flags.DEFINE_string('codebase', '', 'Codebase to push',
                      flag_values=flag_values)
  flags.DEFINE_string('destination', '',
                      'Destination repository (one of %s)' %
                      str(base.REPOSITORIES),
                      flag_values=flag_values)
  flags.DEFINE_string('source_revision', '',
                      'Revision to build source from',
                      flag_values=flag_values)
  flags.DEFINE_string('destination_revision', '',
                      'Revision to push at',
                      flag_values=flag_values)


COMMIT_MESSAGE_TEMPLATE = """
%s

Revision created by MOE tool push_codebase.
MOE_MIGRATION=%s
"""

class CodebasePusher(object):
  """Pushes codebases into editors."""

  def __init__(self, source_codebase, destination_editor, report,
               files_to_ignore_re='', commit_message='', migration_id=''):
    """Construct.

    Args:
      source_codebase: codebase_utils.Codebase
      destination_editor: base.CodebaseEditor
      report: base.MoeReport
      files_to_ignore_re: str, files that should be ignored
      commit_message: str, message to use for commit
      migration_id: str, the id of this migration
    """
    self.source_codebase = source_codebase
    self.destination_editor = destination_editor
    if files_to_ignore_re:
      self.files_to_ignore_re = re.compile(files_to_ignore_re)
    else:
      self.files_to_ignore_re = None
    self.report = report
    self.commit_message = commit_message
    self.migration_id = migration_id

  def Push(self):
    """Pushes source_codebase into destination_editor.

    Returns:
      str, the revision id of the submitted revision, or None if
      no revision was submitted completely
    """
    self.destination_editor.Checkout()

    files_to_push = self._FileUnion()
    print 'Pushing %d files into %s' % (len(files_to_push),
                                        self.destination_editor.Root())
    for filename in files_to_push:
      codebase_path = os.path.join(self.source_codebase.ExpandedPath(),
                                   filename)
      sys.stdout.write('.')
      sys.stdout.flush()
      self.destination_editor.PutFile(filename, codebase_path)
    print

    # TODO(dbentley): allow client to pass in a change message
    commit_message = COMMIT_MESSAGE_TEMPLATE % (
        self.commit_message, self.migration_id)
    self.destination_editor.FinalizeChange(commit_message, self.report)
    commit_id = self.destination_editor.CommitChange(self.report)

    self.pushed = self.destination_editor.ChangesMade()
    return commit_id

  def _FileUnion(self):
    """Determine the union of files in the codebase and the SCM client.

    Returns:
      seq of str, relative_filenames of files that appear in either.
    """
    file_list = list(self.source_codebase.Walk())
    file_set = set(file_list)

    if not file_list:
      self.source_codebase._DebugWalk()
      raise base.Error(
          "MOE found no files to push. "
          "This may be a case of an over-aggressive additional_files_re. "
          "Look above for debugging output.")

    for filename in self.destination_editor.Walk():
      if filename not in file_set:
        file_list.append(filename)

    result = file_list
    if self.files_to_ignore_re:
      result = [f for f in file_list if
                not self.files_to_ignore_re.search(f)]

    return result


def main(unused_args):

  project, db = db_client.MakeProjectAndDbClient()

  try:
    # TODO(dbentley): we shouldn't have to make a client just to get the config
    # NB(dbentley): this also saves the project, so we call it all the time
    # to save the config.
    moe_app.Init(project.name)
    temp_dir = moe_app.RUN.temp_dir
    expander = moe_app.RUN.expander
    report = moe_app.RUN.report

    source_revision = FLAGS.source_revision
    destination_revision = FLAGS.destination_revision

    destination = FLAGS.destination
    if destination not in base.REPOSITORIES:
      raise app.UsageError('destination should be one of %s' %
                           str(base.REPOSITORIES))

    print 'Pushing codebase for MOE project %s into %s' % (project.name,
                                                           destination)

    if destination == base.INTERNAL_STR:
      source_config = project.public_repository
      destination_config = project.internal_repository
    elif destination == base.PUBLIC_STR:
      source_config = project.internal_repository
      destination_config = project.public_repository
    else:
      raise base.Error('Unexpected destination: %s' % destination)

    if FLAGS.codebase:
      source_codebase = codebase_utils.Codebase(
          FLAGS.codebase, expander)
    else:
      _, source_codebase_creator = source_config.MakeRepository(
          temp_dir, expander)
      source_codebase = source_codebase_creator.Create(source_revision)

    _, destination_codebase_creator = destination_config.MakeRepository(
        temp_dir, expander)

    migration_strategy = config.MigrationStrategy(
        merge_strategy=base.ERROR,
        commit_strategy=base.LEAVE_PENDING,
        separate_revisions=False,
        copy_metadata=False)

    # TODO(dbentley): this creates the codebase just to make an editor.
    # We should make it possible to skip this step.
    destination_editor = destination_codebase_creator.Create(
        destination_revision).MakeEditor(migration_strategy)

    # TODO(dbentley): this is ugly, and mirrors what is done in actions.py
    # Fix this.
    # I believe we can now remove this additional_files_re, as it is
    # accounted for in the call to Codebase.Walk()
    additional_files_re = project.public_repository.additional_files_re
    pusher = CodebasePusher(
        source_codebase, destination_editor, report,
        files_to_ignore_re=additional_files_re)
    pusher.Push()
    report.PrintSummary()
  finally:
    db.Disconnect()


class ChangeCmd(appcommands.Cmd):
  def __init__(self, name, flag_values):
    appcommands.Cmd.__init__(self, name, flag_values)
    DefineFlags(flag_values)

  def Run(self, argv):
    main(argv)


if __name__ == '__main__':
  DefineFlags(FLAGS)
  app.run()
