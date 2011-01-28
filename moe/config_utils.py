#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Utilities for handling MOE config files."""

__author__ = 'dborowitz@google.com (Dave Borowitz)'

import os
import re

import json as simplejson

from google.apputils import resources

from moe import base


def CheckJsonKeys(name, json_dict, allowed):
  """Check that the given JSON dict only contains allowed keys.

  Args:
    name: The name of this JSON object, for use in error messages.
    json_dict: A dict of from JSON.
    allowed: A sequence of allowed keys.

  Raises:
    TypeError: if json_dict is not a dict.
    ValueError: if keys other than the allowed keys are found.
  """
  if not isinstance(json_dict, dict):
    raise TypeError('Expected dict, got %s' % type(json_dict))
  json_dict = _StripComments(json_dict)
  allowed = set(allowed)
  unknown = sorted(k for k in json_dict if k not in allowed)
  if unknown:
    raise ValueError('Unknown key(s) in %s dict: %r' % (name, unknown))


def _IsComment(json_obj):
  """Return whether the given object is a comment string."""
  return isinstance(json_obj, basestring) and json_obj.lstrip().startswith('#')


def _StripComments(json_obj):
  """Recursively strip comments from json_obj, possibly returning a copy."""
  if isinstance(json_obj, list):
    return [_StripComments(v) for v in json_obj if not _IsComment(v)]
  if isinstance(json_obj, dict):
    return dict((k, _StripComments(v)) for k, v in json_obj.iteritems()
                if not _IsComment(k))
  return json_obj


def _ReadJsonFileObj(file_obj):
  """Read a config file from a file object and close it."""
  try:
    config_text = file_obj.read()
    return LoadConfig(config_text)
  finally:
    file_obj.close()


def LoadConfig(config_text):
  """Read a JSON config file from a filename.

  Args:
    config_text: str, the text

  Returns:
    A JSON object with comments recursively stripped.
  """
  try:
    return _StripComments(simplejson.loads(config_text))
  except ValueError, e:
    raise base.Error(
        "Config: %s\nError: %s\nError parsing JSON; see above for details." %
        (config_text, str(e)))

def ReadConfigFile(filename):
  """Read a JSON config file from a filename.

  Args:
    filename: The filename.

  Returns:
    A JSON object with comments recursively stripped.
  """
  return _ReadJsonFileObj(open(filename, 'rb'))


def ReadConfigResource(resource_name):
  """Read a JSON config file from a named resource.

  Args:
    resource_name: The resource name.

  Returns:
    A JSON object with comments recursively stripped.
  """
  return _ReadJsonFileObj(resources.GetResourceAsFile(resource_name))


# The strategy for determining absolute/relative filenames if (currently)
# inflexible. It assumes that MONOLITHIC_CODEBASE_NAME appears as a path
# element in the filename. MONOLITHIC_CODEBASE_MIRROR is a path to a current-ish
# mirror of the monolithic codebase. If this is not sufficient for your case,
# let us know.
MONOLITHIC_CODEBASE_NAME = 'moe'
MONOLITHIC_CODEBASE_MIRROR = '/path/to/moe_mirror'


def MakeConfigFilenameRelative(absolute_filename):
  """Determine an absolute filename's path relative to the monolith.

  Args:
    absolute_filename: str

  Returns:
    str

  NB:
    looks at MONOLITHIC_CODEBASE_NAME to determine where the monolithic
    codebase starts. e.g., if MONOLITHIC_CODEBASE_NAME is 'bar', then in
    the path /foo/bar/baz/quux , the relative name is baz/quux.
  """
  if not os.path.isabs(absolute_filename):
    raise base.Error('%s is not an absolute path' % absolute_filename)
  s = os.path.sep + MONOLITHIC_CODEBASE_NAME + os.path.sep
  occurrence = absolute_filename.rfind(s)
  if occurrence == -1:
    raise base.Error(
        'Cannot determine root. (%s does not occur in %s)' % (
            MONOLITHIC_CODEBASE_NAME, absolute_filename))
  return absolute_filename[occurrence + len(s):]


def MakeConfigFilenameAbsolute(relative_filename):
  """Take a relative filename and return a path that can be open()'ed.

  Args:
    relative_filename: str, the relative filename

  Returns:
    str, what to pass to open() to load the config file
  """
  cwd = os.getcwd()
  if MONOLITHIC_CODEBASE_NAME in cwd.split(os.path.sep):
    monolithic_root = re.match('.*' + os.path.sep + MONOLITHIC_CODEBASE_NAME,
                               cwd).group(0)
    in_monolithic_path = os.path.join(monolithic_root, relative_filename)
    if os.path.exists(in_monolithic_path):
      return in_monolithic_path

  return os.path.join(MONOLITHIC_CODEBASE_MIRROR, relative_filename)
