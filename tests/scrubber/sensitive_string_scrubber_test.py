#!/usr/bin/env python
# Copyright 2009 Google Inc. All Rights Reserved.

"""Tests for finding sensitive strings."""

__author__ = 'nicksantos@google.com (Nick Santos)'

from google.apputils import resources
from google.apputils import basetest

from moe import config_utils
from moe.scrubber import sensitive_string_scrubber
import test_util


STRINGS_JSON = config_utils.ReadConfigResource(
    test_util.TestResourceName('sensitive_strings.json'))


class SensitiveWordsTest(basetest.TestCase):
  """Unittests for the sensitive word search."""

  def setUp(self):
    self.word_scrubber = sensitive_string_scrubber.SensitiveWordScrubber(
        STRINGS_JSON[u'sensitive_words'])

  def assertMatch(self, expected_word, line):
    self.assertEquals([expected_word],
                      self.word_scrubber.FindSensitiveStrings(line))

  def assertNoMatch(self, line):
    self.assertEquals([], self.word_scrubber.FindSensitiveStrings(line))

  def testObviousWords(self):
    self.assertMatch(u'testy', u'testy.delegate()')
    self.assertMatch(u'secrety', u'void fixForSecrety')
    self.assertMatch(u'testy', u'http://foo.com/testy/1234')
    self.assertMatch(u'http://secret.wiki/', u'http://secret.wiki/secret-url')
    self.assertMatch(u'internal.website.com', u'foo.internal.website.com')
    self.assertMatch(u'http://secret.wiki/',
                     u'here is one line\nhttp://secret.wiki/secret-url')

  def testCapitalization(self):
    self.assertMatch(u'abc', u'void fixForABC')
    self.assertMatch(u'testy', u'check out the Testy')
    self.assertMatch(u'secrety', u'notSECRETY')
    self.assertNoMatch(u'NOTSECRETY')

    self.assertNoMatch(u'latEsty')     # does not match testy
    self.assertNoMatch(u'notsecretY')  # does not match secrety

  def testNonMatches(self):
    self.assertNoMatch(u'go to the next line')

  def testWordExtraction(self):
    self.assertMatch(u'testy', u'testy')
    self.assertMatch(u'testy', u' testy ')
    self.assertMatch(u'testy', u'ThisIsATestyString')
    self.assertMatch(u'testy', u' public void buildTesty(')
    self.assertMatch(u'testy', u'THIS_IS_TESTY_A_SECRET_PROJECT')
    self.assertNoMatch(u'kittens attesty')


class SensitiveResTest(basetest.TestCase):
  """Unittests for the sensitive word search."""

  def setUp(self):
    self.re_scrubber = sensitive_string_scrubber.SensitiveReScrubber(
        STRINGS_JSON[u'sensitive_res'])

  def assertMatch(self, expected_string, line):
    self.assertEquals([expected_string],
                      self.re_scrubber.FindSensitiveStrings(line))

  def assertNoMatch(self, line):
    self.assertEquals([], self.re_scrubber.FindSensitiveStrings(line))

  def testSensitiveRes(self):
    self.assertMatch(u'supersecret',
                     u'thisissosupersecretweneedtoscrubitevenwithinaword')
    self.assertMatch(u'SUPERSECRET',
                     u'THISISSOSUPERSECRETWENEEDTOSCRUBITEVENWITHINAWORD')
    self.assertMatch(u'SuPeRsEcReT',
                     u'ThIsIsSoSuPeRsEcReTwEnEeDtOsCrUbItEvEnWiThInAwOrD')
    self.assertNoMatch(u'notasecret')

    self.assertMatch(u'.secretcode1.', u'.secretcode1.')
    self.assertMatch(u' secret_code123 ', u'the secret_code123 is secret')
    self.assertNoMatch(u'SECRET_CODE_123')
    self.assertNoMatch(u'THESECRETCODE123')


if __name__ == '__main__':
  basetest.main()
