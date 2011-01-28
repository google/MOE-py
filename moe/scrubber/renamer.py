#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Code for renaming files from input to output in the scrubber."""

__author__ = 'dbentley@google.com (Daniel Bentley)'


from moe.scrubber import base


class FileRenamer(object):
  """Rename files according to a mapping."""

  def __init__(self, renaming_config):
    """Construct the Renamer.

    Args:
      renaming_config: dict. Should have an entry for 'mappings' that maps
                       to a list of dicts that have an 'input_prefix' and an
                       'output_prefix' entries.
                       NB(dbentley): prefixes are considered purely as strings
                       and do not split only at directories. So a prefix of
                       foo will match foo, foo/bar, foo.txt, and fool.
    """
    self._renaming_config = renaming_config
    self._renamed_files = {}

  def RenameFile(self, input_relative_filename):
    """Rename a file, and register its mapping.

    Args:
      input_relative_filename: str

    Returns:
      str, the name the file should take in the output

    Raises:
      base.Error if there was an error
    """
    for mapping in self._renaming_config.get('mappings', []):
      if input_relative_filename.startswith(mapping[u'input_prefix']):
        output_relative_filename = (
            mapping[u'output_prefix'] +
            input_relative_filename[len(mapping[u'input_prefix']):])
        break
    else:
      raise base.Error(
          'Cannot find a mapping covering input file %s' %
          input_relative_filename)

    if output_relative_filename in self._renamed_files:
      original_filename = self._renamed_files[output_relative_filename]
      raise base.Error(
          ('Two files got mapped to the same name in the output: %s and %s\n'
           'Unsure how to continue, exiting') %
          (original_filename, input_relative_filename))
    self._renamed_files[output_relative_filename] = input_relative_filename
    return output_relative_filename
