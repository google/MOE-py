#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Globals that all MOE apps can access."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import getpass
import os
import tempfile

import gflags as flags

from moe import base
from moe import moe_ui

FLAGS = flags.FLAGS


flags.DEFINE_string('moe_temp',
                    tempfile.gettempdir(),
                    'Base directory for all MOE temporary clients and files.')


# RUN is the current MOE run. MOE code can assume it is non-None and a valid
# MoeRun.
RUN = None


class MoeRun(object):
  """The environment any MOE code can depend on.

  A MoeRun is the least common denominator of what MOE code can assume.

  It is appropriate for enhanced versions of Unix globals (e.g., temp_dir
  instead of implicit cwd, or a MoeReport instead of stdout).

  It is not appropriate for higher-level information, such as a
  source_codebase_creator, because MOE code can reasonably run without having
  a codebase_creator, or might have more than one.
  """

  def __init__(self, temp_dir, expander, report, ui, for_test=True):
    self.temp_dir = temp_dir
    self.expander = expander
    self.report = report
    self.ui = ui
    self.for_test = for_test


def _Init(project_name):
  """Initialize a MOE run.

  Args:
    project_name: str, the name of the project. The temporary directory
                  is based on this (so each project has its own directory).

  NB: this should be called only by db_client.MakeProjectContext.
  """
  # pylint: disable-msg=W0603
  global RUN
  if RUN:
    if RUN.for_test:
      return
    else:
      raise base.Error('MOE already initialized')
  temp_dir = os.path.join(
      FLAGS.moe_temp, 'moe.%s' % getpass.getuser(), project_name)
  base.MakeDir(temp_dir)
  expander = base.CodebaseExpander(temp_dir)
  report = base.MoeReport()
  ui = moe_ui.MoeUI()
  RUN = MoeRun(temp_dir, expander, report, ui)


def InitForTest():
  """Initialize for test. Must be called before MOE would be initialized."""
  global RUN
  temp_dir = os.path.join(FLAGS.test_tmpdir)
  expander = base.CodebaseExpander(temp_dir)
  base.MakeDir(temp_dir)
  expander = base.CodebaseExpander(temp_dir)
  report = base.MoeReport()
  ui = moe_ui.MoeUI()
  RUN = MoeRun(temp_dir, expander, report, ui, for_test=True)
