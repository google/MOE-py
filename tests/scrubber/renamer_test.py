#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Tests for moe.scrubber.renamer."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

from google.apputils import basetest
from moe.scrubber import base
from moe.scrubber import renamer


class RenamerTest(basetest.TestCase):

  def testSucceeds(self):
    config = {
        'mappings': [
            # NB(dbentley): it might be better to have prefixes break at
            # directory boundaries
            {'input_prefix': 'first',
             'output_prefix': 'first_moved'},
            {'input_prefix': 'data/readme.txt',
             'output_prefix': 'readme.txt'},
            ],
        }
    renamer_obj = renamer.FileRenamer(config)
    self.assertEqual('first_moved/foo', renamer_obj.RenameFile('first/foo'))
    self.assertEqual('readme.txt', renamer_obj.RenameFile('data/readme.txt'))

  def testFailsWithDoubleMapping(self):
    config = {
        'mappings': [
            {'input_prefix': 'first',
             'output_prefix': 'first_moved'},
            {'input_prefix': 'second',
             'output_prefix': 'first_moved'},
            ],
        }
    renamer_obj = renamer.FileRenamer(config)
    self.assertEqual('first_moved/foo', renamer_obj.RenameFile('first/foo'))
    self.assertRaises(base.Error, renamer_obj.RenameFile,
                      'second/foo')

  def testFailsWithNoMapping(self):
    config = {
        'mappings': [
            ],
        }
    renamer_obj = renamer.FileRenamer(config)
    self.assertRaises(base.Error, renamer_obj.RenameFile, 'foo')

if __name__ == '__main__':
  basetest.main()
