#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Objects to represent a MOE Project."""

__author__ = 'dbentley@google.com (Daniel Bentley)'


from moe import base
from moe import config_utils
from moe.translators import python_translators
from moe.translators import translators
from moe.translators import undo_scrubbing_translator


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


_SCRUBBING_TRANSLATOR_CONFIG_KEYS = [
    u'from_project_space',
    u'to_project_space',
    u'scrubber_config',
    u'type',
    ]


_TRANSLATOR_CONFIG_KEYS = [
    u'from_project_space',
    u'to_project_space',
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
  dependent_scrubber_configs = []
  for config_json in translators_config:
    type_arg = config_json.get(u'type')
    if not type_arg:
      raise base.Error('Translator config requires a "type"')
    if type_arg == u'scrubber':
      config_utils.CheckJsonKeys('translator_config', config_json,
                                 _SCRUBBING_TRANSLATOR_CONFIG_KEYS)
      result.append(translators.ScrubberInvokingTranslator(
          config_json.get('from_project_space'),
          config_json.get('to_project_space'),
          config_json.get('scrubber_config')))
      continue
    if type_arg == u'python_2to3':
      config_utils.CheckJsonKeys('translator_config', config_json,
                                 _TRANSLATOR_CONFIG_KEYS)
      result.append(python_translators.TwoToThreeTranslator(
          config_json.get('from_project_space'),
          config_json.get('to_project_space')))
      continue
    if type_arg == u'python_3to2':
      config_utils.CheckJsonKeys('translator_config', config_json,
                                 _TRANSLATOR_CONFIG_KEYS)
      result.append(python_translators.ThreeToTwoTranslator(
          config_json.get('from_project_space'),
          config_json.get('to_project_space')))
      continue
    if type_arg == u'identity':
      config_utils.CheckJsonKeys('translator_config', config_json,
                                 _TRANSLATOR_CONFIG_KEYS)
      result.append(translators.IdentityTranslator(
          config_json.get('from_project_space'),
          config_json.get('to_project_space')))
      continue
    if type_arg in set([u'undo_scrubbing']):
      dependent_scrubber_configs.append(config_json)
      continue
    raise base.Error('Translator type "%s" unknown' % type_arg)
    # TODO(dbentley): new translator type that uses project arg

  for config_json in dependent_scrubber_configs:
    # These are scrubbers that are dependent on other translators.
    # We can only process them once the first round of translators are
    # constructed.
    type_arg = config_json.get(u'type')
    if type_arg == u'undo_scrubbing':
      # The undo scrubber undoes a previous scrubbing translator. Which
      # previous translator? The one that has the opposite from/to project
      # spaces as this one.
      config_utils.CheckJsonKeys('translator_config', config_json,
                                 _TRANSLATOR_CONFIG_KEYS)
      forward_translator = None
      for t in result:
        if (t.ToProjectSpace() == config_json.get('from_project_space') and
            t.FromProjectSpace() == config_json.get('to_project_space')):
          forward_translator = t
          break
      else:
        raise base.Error(
            'Could find no forward_translator from %s to %s to undo' %
            (config_json.get('to_project_space'),
             config_json.get('from_project_space')))
      result.append(undo_scrubbing_translator.UndoScrubbingTranslator(
          config_json.get('from_project_space'),
          config_json.get('to_project_space'),
          project,
          forward_translator
          ))

  return result
