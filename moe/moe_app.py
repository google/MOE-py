#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Catch-all binary to run MOE tools."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

from google.apputils import appcommands
import gflags as flags

from moe import create_codebase
from moe import init_codebases
from moe import manage_codebases
from moe import push_codebase
from moe import round_trip
from moe import simple_commands

FLAGS = flags.FLAGS


def main(argv):
  appcommands.AddCmd('auto', manage_codebases.AutoCmd)
  appcommands.AddCmd('change', push_codebase.ChangeCmd)
  appcommands.AddCmd('check_config', simple_commands.CheckConfigCmd)
  appcommands.AddCmd('create_codebase', create_codebase.CreateCodebaseCmd)
  appcommands.AddCmd('hello', simple_commands.HelloWorldCmd)
  appcommands.AddCmd('init', init_codebases.InitCmd)
  appcommands.AddCmd('round_trip', round_trip.RoundTripCmd)


if __name__ == '__main__':
  appcommands.Run()
