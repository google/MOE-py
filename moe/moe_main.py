#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Catch-all binary to run MOE tools."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

from google.apputils import appcommands
import gflags as flags

from moe import create_codebase
from moe import db_client
from moe import init_codebases
from moe import manage_codebases
from moe import moe_app
from moe import push_codebase

FLAGS = flags.FLAGS


class HelloWorldCmd(appcommands.Cmd):
  """Print Hello World, indicating MOE can successfully start-up."""

  def __init__(self, name, flag_values):
    appcommands.Cmd.__init__(self, name, flag_values)

  def Run(self, argv):
    print 'Hello World'


class CheckConfigCmd(appcommands.Cmd):
  """Check that a project config is valid."""

  def __init__(self, name, flag_values):
    appcommands.Cmd.__init__(self, name, flag_values)

  def Run(self, argv):
    project, db = db_client.MakeProjectAndDbClient()
    moe_app.Init(project.name)
    task = moe_app.RUN.ui.BeginIntermediateTask('check_config',
                                                'Checking Config')
    with task:
      moe_app.RUN.ui.Info('Success!')


def main(argv):
  appcommands.AddCmd('hello', HelloWorldCmd)
  appcommands.AddCmd('check_config', CheckConfigCmd)
  appcommands.AddCmd('create_codebase', create_codebase.CreateCodebaseCmd)
  appcommands.AddCmd('change', push_codebase.ChangeCmd)
  appcommands.AddCmd('auto', manage_codebases.AutoCmd)
  appcommands.AddCmd('init', init_codebases.InitCmd)


if __name__ == '__main__':
  appcommands.Run()
