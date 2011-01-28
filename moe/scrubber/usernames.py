#!/usr/bin/env python
# Copyright 2009 Google Inc. All Rights Reserved.

"""A module that classifies usernames."""

import re

from moe import config_utils

PUBLISH = object()
SCRUB = object()
UNKNOWN_USER = object()


class UsernameFilter(object):
  """Class to filter usernames based on some configuration."""

  def __init__(self,
               usernames_file=None,
               publishable_usernames=None,
               scrubbable_usernames=None,
               scrub_unknown_users=False):
    """Create a UsernameFilter.

    Args:
      usernames_file: str, filename of usernames to publish/scrub
      publishable_usernames: set, usernames to publish
      scrubbable_usernames: set, usernames to scrub
      scrub_unknown_users: bool, whether usernames not specified as publishable
                           or scrubbable should be scrubbed or reported as
                           errors
    """
    publishable_usernames = set(publishable_usernames or [])
    scrubbable_usernames = set(scrubbable_usernames or [])

    self._scrub_unknown_users = scrub_unknown_users

    if usernames_file:
      usernames = config_utils.ReadConfigFile(usernames_file)
      config_utils.CheckJsonKeys(
          'usernames config', usernames,
          [u'publishable_usernames', u'scrubbable_usernames'])
      publishable_usernames.update(usernames.get(u'publishable_usernames', []))
      scrubbable_usernames.update(usernames.get(u'scrubbable_usernames', []))

    self._publishable_usernames = publishable_usernames
    self._scrubbable_usernames = scrubbable_usernames

  def DetermineScrubAction(self, username):
    """Determines whether username should be published, scrubbed, or unknown.

    Args:
      username: str, the username in question

    Returns:
      one of PUBLISH, SCRUB, and UNKNOWN_USER
    """
    if username in self._publishable_usernames:
      return PUBLISH
    if username in self._scrubbable_usernames:
      return SCRUB
    if self._scrub_unknown_users:
      return SCRUB
    return UNKNOWN_USER

  def CanPublish(self, username):
    return self.DetermineScrubAction(username) is PUBLISH


class EmailAddressFilter(object):
  """Class to filter email addresses given an (optional) username filter."""

  def __init__(self, username_filter=None):
    self._username_filter = username_filter

  USERNAME_RE = re.compile(r'(.*)@google.com')

  def CanPublish(self, text_with_email_address):
    username = self.USERNAME_RE.match(text_with_email_address)
    return (self._username_filter and username and
            self._username_filter.CanPublish(username.group(1).strip()))
