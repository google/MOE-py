#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Objects to represent a MOE Project."""

__author__ = 'dbentley@google.com (Daniel Bentley)'


from moe import base
from moe import config_utils
from moe import translators


class MoeProjectContext(object):
  """A MoeProjectContext comprises the objects to do stuff with a project.

  Most MOE apps will only have one MoeProjectContext in their runtime.
  But they might, and that's why MoeProjectContext is not a global but
  MoeRun is.
  """

  def __init__(self, config, db):
    self.config = config
    self.db = db

    self.translators = MakeTranslators(
        config.config_json.get('translators', []), self)

    self.internal_repository, self.internal_codebase_creator = (
        config.internal_repository_config.MakeRepository(
            translators=self.translators))
    self.public_repository, self.public_codebase_creator = (
        config.public_repository_config.MakeRepository(
            translators=self.translators))


_TRANSLATOR_CONFIG_KEYS = [
    u'from_project_space',
    u'to_project_space',
    u'scrubber_config',
    u'type',
    ]


def MakeTranslators(translators_config, project):
  """Construct the Translators from their config.

  Args:
    translators_config: array of dictionaries (of the sort that come from JSON)
    project: MoeProjectContext

  Returns:
    list of translators.Translator
  """
  result = []
  for config_json in translators_config:
    config_utils.CheckJsonKeys('translator_config', config_json,
                               _TRANSLATOR_CONFIG_KEYS)
    type_arg = config_json.get(u'type')
    if not type_arg:
      raise base.Error('Translator config requires a "type"')
    if type_arg == u'scrubber':
      result.append(translators.ScrubberInvokingTranslator(
          config_json.get('from_project_space'),
          config_json.get('to_project_space'),
          config_json.get('scrubber_config')))
      continue
    if type_arg == u'identity':
      result.append(translators.IdentityTranslator(
          config_json.get('from_project_space'),
          config_json.get('to_project_space')))
      continue
    raise base.Error('Translator type "%s" unknown' % type_arg)
    # TODO(dbentley): new translator type that uses project arg

  return result
