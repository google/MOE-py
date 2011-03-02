#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.

"""Create a Codebase and then push it back to the same place.

This is a good end-to-end test of MOE's integration with an SCM.
"""

__author__ = 'dbentley@google.com (Dan Bentley)'

import mimetypes
import os.path

from google.apputils import appcommands
from google.apputils import file_util
import gflags as flags

from moe import base
from moe import codebase_utils
from moe import config
from moe import db_client
from moe import moe_app
from moe import push_codebase

FLAGS = flags.FLAGS


EDITABLE_FILETYPES = set(['.cc', '.html', '.java', '.js', '.py', '.txt'])


class RoundTripCmd(appcommands.Cmd):
  def __init__(self, name, flag_values):
    appcommands.Cmd.__init__(self, name, flag_values)
    flags.DEFINE_string(
        'repository',
        'internal',
        ('Repository to take code from and push to (must be one of %s)' %
         repr(base.REPOSITORIES)),
        flag_values=flag_values)
    flags.DEFINE_string(
        'source_revision', '',
        'Revision to create codebase from (empty for head)',
        flag_values=flag_values)
    # TODO(dbentley): we should probably allow the user to specify that we
    # should translate into a project space to test translation, as well.

  def Run(self, argv):
    project = db_client.MakeProjectContext()

    try:
      revision = FLAGS.source_revision

      repository = FLAGS.repository
      if repository not in base.REPOSITORIES:
        raise app.UsageError('repository should be one of %s' %
                             str(base.REPOSITORIES))

      print 'Generating from and pushing into %s for MOE project %s' % (
          repository, project.config.name)

      if repository == base.INTERNAL_STR:
        codebase_creator = project.internal_codebase_creator
      elif destination == base.PUBLIC_STR:
        codebase_creator = project.public_codebase_creator
      else:
        raise base.Error('Unexpected repository: %s' % destination)

      original_codebase = codebase_creator.Create(revision)

      codebase = codebase_utils.CreateModifiableCopy(original_codebase)

      for relative_filename in codebase.Walk():
        filename = codebase.FilePath(relative_filename)

        if os.path.splitext(filename)[1] in EDITABLE_FILETYPES:
          file_util.Write(filename,
                          file_util.Read(filename) + '\nMOE was here.\n')

      migration_strategy = config.MigrationStrategy(
          merge_strategy=base.ERROR,
          commit_strategy=base.LEAVE_PENDING,
          separate_revisions=False,
          copy_metadata=False)

      # TODO(dbentley): this creates the codebase just to make an editor.
      # We should make it possible to skip this step.
      destination_editor = codebase_creator.Create(
          revision).MakeEditor(migration_strategy)

      # TODO(dbentley):
      # We should be able to remove this additional_files_re, as it is
      # accounted for in the call to Codebase.Walk(). Unfortunately, we can't.
      # Why? Because a generated codebase is currently, incorrectly, getting
      # generated with the additional_files_re from the internal codebase,
      # even when it should be in the public project space.
      additional_files_re = (
          project.config.public_repository_config.additional_files_re)
      pusher = push_codebase.CodebasePusher(
          codebase, destination_editor, files_to_ignore_re=additional_files_re)
      pusher.Push()
      moe_app.RUN.report.PrintSummary()
    finally:
      project.db.Disconnect()


if __name__ == '__main__':
  DefineFlags(FLAGS)
  app.run()
