#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""A structure UI for MOE tools."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import sys

import logging

from moe import base


class _MoeUIFormatter(object):
  """Formats messages in the MOE UI."""

  def __init__(self, ui):
    """Construct.

    Args:
      ui: MoeUI
    """
    self._ui = ui

  def PrintBeginning(self, description):
    raise NotImplementedError

  def PrintEnding(self, description, result=None):
    raise NotImplementedError


class ImmediateTaskFormatter(_MoeUIFormatter):
  def PrintBeginning(self, description):
    self._ui._Print(description + '...', new_line=False)

  def PrintEnding(self, description, result=None):
    self._ui._Print(result or 'Done', with_indentation=False)


class IntermediateTaskFormatter(_MoeUIFormatter):
  def PrintBeginning(self, description):
    self._ui._Print('BEGINNING: %s' % description)

  def PrintEnding(self, description, result=None):
    self._ui._Print('DONE: %s' % description)


class _MoeUITask(object):
  """_MoeUITask encapsulates a single, transactional task in the UI."""

  def __init__(self, ui, task_name, description, formatter):
    # Immutable
    self._ui = ui
    self._task_name = task_name
    self._description = description
    self._formatter = formatter

    # Mutable
    self._result = None

  def __enter__(self):
    """Begin this task."""
    self._formatter.PrintBeginning(self._description)
    self._ui._tasks.append(self._task_name)
    return self

  def SetResult(self, result):
    """Note that this task is finished, with result.

    Args:
      result: str, a description of the Result
    """
    if self._result:
      raise base.Error(
          "Trying to set result on task %s, but it is already %s" % (
              self._task_name, self._result))
    self._result = result

  def __exit__(self, type, value, traceback):
    """End this task."""
    if not self._ui._tasks:
      raise base.Error("Trying to end task %s, but no tasks on the stack"
                       % self._task_name)
    if self._ui._tasks[-1] != self._task_name:
      raise base.Error("Trying to end task %s, but current task is %s" %
                       (self._task_name, self._ui._tasks[-1]))

    # Delete the task from the stack now
    self._ui._tasks = self._ui._tasks[:-1]

    self._formatter.PrintEnding(self._description, self._result)

    return False  # Don't swallow exception


# NB(dbentley): this class is trying to replace MoeReport
class MoeUI(object):
  """The MoeUI allows MOE code to explain what it is doing.

  MoeUI keeps a stack of tasks, and may present this in the UI.
  """

  def __init__(self):
    self._tasks = []

  def _Print(self, text, new_line=True, with_indentation=True):
    """Helper function to format and print text."""
    if with_indentation:
      text = self._Indent(text)
    sys.stdout.write(text)
    if new_line:
      sys.stdout.write('\n')
    sys.stdout.flush()

  def _Indent(self, message):
    lines = message.split('\n')
    indented_lines = ['  ' * len(self._tasks) + l for l in lines]
    return '\n'.join(indented_lines)

  def Info(self, description):
    """Print some text in the current context."""
    self._Print(description)

  def Debug(self, msg):
    """Pring a message for debugging"""
    logging.debug(msg)

  def BeginTask(self, task_name, description, formatter):
    """Begin a task.

    Returns an object suitable for use as a with statement context manager.
    The task may raise a base.Error if completion is attempted in an invalid
    state.

    Args:
      task_name: str, the name of the task. Not shown to user.
      description: str, a description of the task. Displayed to user.
    """
    return _MoeUITask(self, task_name, description, formatter)

  def BeginImmediateTask(self, task_name, description):
    return self.BeginTask(task_name, description, ImmediateTaskFormatter(self))

  def BeginIntermediateTask(self, task_name, description):
    return self.BeginTask(task_name, description,
                          IntermediateTaskFormatter(self))
