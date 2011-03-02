#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Simple MOE commands."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

from google.apputils import appcommands

from moe import db_client
from moe import moe_app


class HelloWorldCmd(appcommands.Cmd):
  """Print Hello World, indicating MOE can successfully start-up."""

  def Run(self, argv):
    print 'Hello World'


class CheckConfigCmd(appcommands.Cmd):
  """Check that a project config is valid."""

  def Run(self, argv):
    unused_project = db_client.MakeProjectContext()
    task = moe_app.RUN.ui.BeginIntermediateTask('check_config',
                                                'Checking Config')
    with task:
      moe_app.RUN.ui.Info('Success!')
