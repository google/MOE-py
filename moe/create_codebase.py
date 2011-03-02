#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Command to create a codebase for a MOE project."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

from google.apputils import app
from google.apputils import appcommands
import gflags as flags

from moe import base
from moe import db_client
from moe import moe_app

FLAGS = flags.FLAGS


class CreateCodebaseCmd(appcommands.Cmd):
  """Create a codebase from a project for examination."""

  def __init__(self, name, flag_values):
    appcommands.Cmd.__init__(self, name, flag_values)
    flags.DEFINE_string(
        'source_repository',
        'internal',
        ('Repository to create the codebase from (Must be one of %s)' %
         repr(base.REPOSITORIES)),
        flag_values=flag_values)
    flags.DEFINE_string(
        'source_revision', '',
        'Revision to create codebase from (empty for head)',
        flag_values=flag_values)
    flags.DEFINE_string(
        'target_project_space', base.PUBLIC_STR,
        'Project Space to create codebase in')

  def Run(self, unused_argv):
    project = db_client.MakeProjectContext()

    try:
      source_revision = FLAGS.source_revision
      source = FLAGS.source_repository
      if source not in base.REPOSITORIES:
        raise app.UsageError('source_repository should be one of %s' %
                             str(base.REPOSITORIES))

      if source == base.INTERNAL_STR:
        repository = project.internal_repository
        codebase_creator = project.internal_codebase_creator
      elif source == base.PUBLIC_STR:
        repository = project.public_repository
        codebase_creator = project.public_codebase_creator
      else:
        raise base.Error('Unexpected source: %s' % source)

      with moe_app.RUN.ui.BeginImmediateTask(
          'head_revision', 'Determining Head Revision') as t:
        head_revision = repository.GetHeadRevision(source_revision)
        t.SetResult(head_revision)
      source_codebase = codebase_creator.CreateInProjectSpace(
          revision=head_revision, project_space=FLAGS.target_project_space)

      moe_app.RUN.ui.Info('Codebase created at %s' % source_codebase.Path())
    finally:
      project.db.Disconnect()
