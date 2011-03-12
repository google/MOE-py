#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Tests for moe.moe_project."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

from google.apputils import basetest
from moe import moe_project
from moe.translators import translators


class MoeProjectTest(basetest.TestCase):

  def testMakeTranslators(self):
    ts = moe_project.MakeTranslators([], None)
    self.assertEqual([], ts)

    # Test Translators
    ts = moe_project.MakeTranslators([
        {'type': 'identity',
         'from_project_space': 'foo',
         'to_project_space': 'bar'},
        {'type': 'identity',
         'from_project_space': 'bar',
         'to_project_space': 'foo'},
        {'type': 'scrubber',
         'from_project_space': 'internal',
         'to_project_space': 'public',
         'scrubber_config': {'key': 'value'}
        },
        ], None)

    t0 = ts[0]
    self.assertEqual(translators.IdentityTranslator, type(t0))
    self.assertEqual('foo', t0.FromProjectSpace())
    self.assertEqual('bar', t0.ToProjectSpace())

    t1 = ts[1]
    self.assertEqual(translators.IdentityTranslator, type(t1))
    self.assertEqual('bar', t1.FromProjectSpace())
    self.assertEqual('foo', t1.ToProjectSpace())

    t2 = ts[2]
    self.assertEqual(translators.ScrubberInvokingTranslator, type(t2))
    self.assertEqual('internal', t2.FromProjectSpace())
    self.assertEqual('public', t2.ToProjectSpace())
    self.assertEqual({'key': 'value'}, t2._scrubber_config)

    # Test UndoScrubbingTranslator making
    ts = moe_project.MakeTranslators([
        {'type': 'undo_scrubbing',
         'from_project_space': 'public',
         'to_project_space': 'internal'},
        {'type': 'scrubber',
         'from_project_space': 'internal',
         'to_project_space': 'public',
         'scrubber_config': {'key': 'value'}}
        ], None)

    t0 = ts[0]
    self.assertEqual(translators.ScrubberInvokingTranslator, type(t0))
    self.assertEqual(t0, ts[1]._forward_translator)


if __name__ == '__main__':
  basetest.main()
