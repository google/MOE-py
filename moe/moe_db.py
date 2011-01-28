#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tool for interacting with the MOE db from the command-line."""

__author__ = 'dbentley@google.com (Daniel Bentley)'


from google.apputils import appcommands
from google.apputils import file_util
import gflags as flags

from moe import base
from moe import db_client


FLAGS = flags.FLAGS


class NoteEquivalenceCmd(appcommands.Cmd):
  """Note an equivalence in the project."""

  def __init__(self, name, flag_values):
    appcommands.Cmd.__init__(self, name, flag_values)
    flags.DEFINE_string(
        'internal_revision', '',
        'internal revision of equivalence', flag_values=flag_values)
    flags.DEFINE_string(
        'public_revision', '',
        'public revision of equivalence', flag_values=flag_values)

  def Run(self, argv):
    project = base.MakeMoeProject()
    if not FLAGS.internal_revision or not FLAGS.public_revision:
      raise app.UsageError('Must specify both internal and public revisions')
    db = db_client.MakeDbClient(project=project)

    # TODO(dbentley): error check these values.
    # First, try checking that the revisions are valid.
    # Second, get both codebases and diff them. This is for two reasons:
    # 1) Prevent mistaken runs of the tool
    # 2) Eventually, we want to allow hand-maintained differences between
    # codebases. For this to work, we need to know the diff at the point
    # of equivalence.
    db.NoteEquivalence(db_client.Equivalence(FLAGS.internal_revision,
                                            FLAGS.public_revision))


def main(argv):
  appcommands.AddCmd('note_equivalence', NoteEquivalenceCmd)


if __name__ == '__main__':
  appcommands.Run()
