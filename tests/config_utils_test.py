#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for config file functions."""

__author__ = 'dborowitz@google.com (Dave Borowitz)'

import os

from mox import stubout
import json as simplejson

from google.apputils import basetest
from moe import base
from moe import config_utils
import test_util


class CheckJsonKeysTest(basetest.TestCase):

  def setUp(self):
    self._keys = [u'foo', u'bar', u'baz', u'quux']
    self._dict = dict((s, i) for i, s in enumerate(self._keys))

  def assertCheckSucceeds(self):
    config_utils.CheckJsonKeys('test', self._dict, self._keys)

  def assertCheckRaises(self, error_cls):
    self.assertRaises(error_cls, config_utils.CheckJsonKeys, 'test', self._dict,
                      self._keys)

  def testType(self):
    self._dict = []
    self.assertCheckRaises(TypeError)

  def testSucceeds(self):
    self.assertCheckSucceeds()

  def testComment(self):
    self._dict.update({
        u'#': u'comment',
        u'  #': u'comment',
        u'# comment': u'comment',
        })
    self.assertCheckSucceeds()

  def testFails(self):
    self._dict[u'badkey'] = 27
    self.assertCheckRaises(ValueError)

  def testFromJson(self):
    self._dict = simplejson.loads('{"#": "comment 1",'
                                  '"#": "comment 2",'
                                  '"foo": 123,'
                                  '"# comment 3": 456,'
                                  '"bar": 789,'
                                  '"  #": null}')
    self.assertCheckSucceeds()


SIMPLE_FILE = test_util.TestResourceName('config_utils_test/simple.json')


class ConfigUtilsTest(basetest.TestCase):
  def setUp(self):
    config_utils.MONOLITHIC_CODEBASE_NAME = 'monolith'
    config_utils.MONOLITHIC_CODEBASE_MIRROR = ('/path/to/monolith_mirror/'
                                               'monolith')
    self.stubs = stubout.StubOutForTesting()

  def tearDown(self):
    self.stubs.UnsetAll()

  def testWrapsErrors(self):
    self.assertRaises(
        base.Error,
        config_utils.LoadConfig,
        # This input has a trailing comma that json forbids.
        '{"a":"b",}')

  def testLoadConfig(self):
    self.assertDictEqual(
        {u'key1': u'value1', u'key2': u'value2'},
        config_utils.LoadConfig(
            '{"key1": "value1", "key2": "value2"}'))

  def testReadConfigResource(self):
    self.assertDictEqual({u'key1': u'value1', u'key2': u'value2'},
                         config_utils.ReadConfigResource(SIMPLE_FILE))

  def testStripCommentsList(self):
    json_list = [
        u'#',
        u'1',
        u' #',
        2,
        u'# comment',
        None, True,
        ]
    self.assertListEqual([u'1', 2, None, True],
                         config_utils._StripComments(json_list))

  def testStripCommentsDict(self):
    json_dict = {
        u'#': u'comment0',
        u'key1': u'value1',
        u' #': [u'ignored', u'list'],
        u'key2': u'value2',
        u'# comment': None,
        }
    self.assertDictEqual({u'key1': u'value1', u'key2': u'value2'},
                         config_utils._StripComments(json_dict))

  def testStripCommentsRecursive(self):
    json_dict = {u'#': u'comment0',
                 u'key1': [
                     u'# comment2',
                     u'value1', {
                         u'subkey1': u'subvalue',
                         u'# subcomment': u'',
                         u'subkey2': [u'# comment'],
                         },
                     ],
                 u'# one more comment': '',
                }
    stripped = {u'key1': [u'value1', {u'subkey1': u'subvalue',
                                      u'subkey2': []}]}
    self.assertDictEqual(stripped, config_utils._StripComments(json_dict))

  def testMakeConfigFilenameRelative(self):
    self.assertEqual(
        'foo',
        config_utils.MakeConfigFilenameRelative('/home/user/srcs/monolith/foo'))
    self.assertEqual(
        'foo',
        config_utils.MakeConfigFilenameRelative(
            '/path/to/monolith_mirror/monolith/foo'))

  def testMakeConfigFilenameAbsolute(self):
    def MockCwd(value):
      self.stubs.Set(os, 'getcwd', lambda: value)

    MockCwd('/not/a/source/checkout')
    self.assertEqual(
        '/path/to/monolith_mirror/monolith/foo',
        config_utils.MakeConfigFilenameAbsolute('foo'))

    MockCwd('/home/user/srcs/monolith/subdir')
    self.assertEqual(
        '/path/to/monolith_mirror/monolith/foo',
        config_utils.MakeConfigFilenameAbsolute('foo'))

    self.stubs.Set(os.path, 'exists', lambda s: True)
    self.assertEqual(
        '/home/user/srcs/monolith/foo',
        config_utils.MakeConfigFilenameAbsolute('foo'))


if __name__ == '__main__':
  basetest.main()
