#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Prints out MOE's view of differences between two codebases."""




from google.apputils import app
from google.apputils import appcommands
import gflags as flags

from moe import base
from moe import db_client
from moe import moe_app

FLAGS = flags.FLAGS


def DefineFlags(flag_values):
  flags.DEFINE_integer('internal_revision', -1,
                       'The internal revision to diff against.',
                       flag_values=flag_values)

  flags.DEFINE_integer('public_revision', -1,
                       'The public revision to diff against.',
                       flag_values=flag_values)


def main(unused_argv):
  project = db_client.MakeProjectContext()
  try:
    internal_codebase = project.internal_codebase_creator.Create(
        FLAGS.internal_revision > 0 and FLAGS.internal_revision or
        project.internal_repository.GetHeadRevision())
    public_codebase = project.public_codebase_creator.Create(
        FLAGS.public_revision > 0 and FLAGS.public_revision or
        project.public_repository.GetHeadRevision())
    diff_obj = base.AreCodebasesDifferent(
        internal_codebase,
        public_codebase,
        project.config.noisy_files_re,
        record_full_diffs=True)
    moe_app.RUN.ui.Info('\n===== Begin diff_codebases =====\n')
    moe_app.RUN.ui.Info(str(diff_obj))
  finally:
    project.db.Disconnect()


class DiffCmd(appcommands.Cmd):
  def __init__(self, name, flag_values):
    appcommands.Cmd.__init__(self, name, flag_values)
    DefineFlags(flag_values)

  def Run(self, argv):
    main(argv)


if __name__ == '__main__':
  DefineFlags(FLAGS)
  app.run()
