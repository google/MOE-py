#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved

import cProfile
import os

from google.appengine.ext.webapp import template

DEBUG_MODE = False

PROFILING_ENABLED = False

profiler_ = cProfile.Profile()


def GetProfiler():
  """Returns the profiler."""
  return profiler_


def RenderTemplate(template_name, template_values):
  """Return render of template 'template_name' with template_values."""
  return template.render(
      os.path.join(os.path.dirname(__file__), 'templates', template_name),
      template_values)
