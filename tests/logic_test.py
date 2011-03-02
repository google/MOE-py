#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Tests for moe.logic."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

from google.apputils import basetest

from moe import base
from moe import logic
from moe import moe_app


def setUp():
  moe_app.InitForTest()

class LogicTest(basetest.TestCase):

  def testVerifyEquivalences(self):
    noted_equivalences = []

    class DbMock(object):
      def NoteEquivalence(self,
                          e, verification_status=base.VERIFICATION_VERIFIED):
        noted_equivalences.append((e.internal_revision, e.public_revision,
                                   verification_status))

      def FindUnverifiedEquivalences(self):
        return [base.Correspondence('1001', '1'),
                base.Correspondence('1003', '3')]

    class InternalRepositoryMock(object):
      def GetHeadRevision(self, max_revision):
        if max_revision == '1001': return '1001'
        return '1002'

    class PublicRepositoryMock(object):
      def GetHeadRevision(self, max_revision):
        if max_revision == '1': return '1'
        return '2'

    logic.VerifyEquivalences(
        DbMock(), InternalRepositoryMock(), PublicRepositoryMock())
    self.assertEqual(
        [('1001', '1', base.VERIFICATION_VERIFIED),
         ('1002', '2', base.VERIFICATION_VERIFIED),
         ('1003', '3', base.VERIFICATION_INVALID)],
        noted_equivalences)


if __name__ == '__main__':
  basetest.main()
