#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Implementation of the MOE config."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import os

import json as simplejson

from google.apputils import file_util
import gflags as flags

from moe import base
from moe import config_utils
from moe import git
from moe import mercurial
from moe import svn

FLAGS = flags.FLAGS


class MigrationStrategy(object):
  """Encapsulates a strategy for dealing with code that needs to be migrated."""

  def __init__(self, merge_strategy=None, commit_strategy=None,
               separate_revisions=False, copy_metadata=False,
               default_strategy=None):
    if not merge_strategy:
      if default_strategy:
        merge_strategy = default_strategy.merge_strategy
      else:
        raise ValueError('No merge strategy specified.')
    if not commit_strategy:
      if default_strategy:
        commit_strategy = default_strategy.commit_strategy
      else:
        commit_strategy = base.LEAVE_PENDING

    if merge_strategy not in base.MERGE_STRATEGIES:
      raise ValueError('Invalid merge strategy %r' % merge_strategy)
    if commit_strategy not in base.COMMIT_STRATEGIES:
      raise ValueError('Invalid commit strategy %r' % commit_strategy)

    # TODO(user): Check separate_revisions and copy_metadata for booleanness

    self.merge_strategy = merge_strategy
    self.commit_strategy = commit_strategy
    self.separate_revisions = separate_revisions
    self.copy_metadata = copy_metadata

  def Serialized(self):
    """Serialize the migration strategy."""
    result = {}
    result[u'merge_strategy'] = self.merge_strategy
    result[u'commit_strategy'] = self.commit_strategy
    result[u'separate_revisions'] = self.separate_revisions
    result[u'copy_metadata'] = self.copy_metadata
    return result

  def __eq__(self, other):
    if not isinstance(other, MigrationStrategy):
      return False
    return (self.merge_strategy == other.merge_strategy and
            self.commit_strategy == other.commit_strategy and
            self.separate_revisions == other.separate_revisions and
            self.copy_metadata == other.copy_metadata)


class MoeProjectConfig(object):
  """Encapsulates a project configuration."""
  # TODO(dborowitz): copy documentation

  def __init__(self, name):
    self.name = name
    self.filename = ''
    self.empty = True
    self.internal_repository_config = EmptyRepositoryConfig()
    self.public_repository_config = EmptyRepositoryConfig()
    self.import_strategy = DefaultImportStrategy()
    self.export_strategy = DefaultExportStrategy()
    self.moe_db_url = None
    self.owners = []
    self.manual_equivalence_deltas = None
    self.noisy_files_re = None
    self.config_json = {}

  def Serialized(self):
    """Return json representation for this project."""
    result = self.config_json
    result['name'] = self.name
    if self.filename:
      result['filename'] = self.filename
    if self.internal_repository_config:
      result['internal_repository'] = (
          self.internal_repository_config.Serialized())
    if self.public_repository_config:
      result['public_repository'] = (
          self.public_repository_config.Serialized())

    result['import_strategy'] = self.import_strategy.Serialized()
    result['export_strategy'] = self.export_strategy.Serialized()
    if self.moe_db_url:
      result['moe_db_url'] = self.moe_db_url
    if self.owners:
      result['owners'] = self.owners
    if self.manual_equivalence_deltas:
      result['manual_equivalence_deltas'] = self.manual_equivalence_deltas
    if self.noisy_files_re:
      result['noisy_files_re'] = self.noisy_files_re
    return simplejson.dumps(result)


def DefaultImportStrategy():
  """Generates the default import migration strategy."""
  return MigrationStrategy(merge_strategy=base.MERGE,
                           commit_strategy=base.LEAVE_PENDING,
                           separate_revisions=False, copy_metadata=False)


def DefaultExportStrategy():
  """Generates the default export migration strategy."""
  return MigrationStrategy(merge_strategy=base.OVERWRITE,
                           commit_strategy=base.LEAVE_PENDING,
                           separate_revisions=False, copy_metadata=False)


def _MigrationStrategyFromJson(strategy_json, default_strategy=None):
  if strategy_json is None:
    return default_strategy
  config_utils.CheckJsonKeys('strategy', strategy_json,
                             [u'merge_strategy', u'commit_strategy',
                              u'separate_revisions', u'copy_metadata'])

  return MigrationStrategy(
      merge_strategy=strategy_json.get(u'merge_strategy'),
      commit_strategy=strategy_json.get(u'commit_strategy'),
      separate_revisions=strategy_json.get(u'separate_revisions'),
      copy_metadata=strategy_json.get(u'copy_metadata'),
      default_strategy=default_strategy)


_PROJECT_CONFIG_KEYS = [
    u'name',
    u'internal_repository',
    u'public_repository',
    u'translators',
    u'noisy_files_re',
    u'moe_db_url',
    u'owners',
    u'manual_equivalence_deltas',
    u'import_strategy',
    u'export_strategy',
    u'filename',
    ]


def MoeProjectConfigFromJson(config_json, filename=''):
  """Create a MoeProjectConfig from a config JSON object."""
  config_utils.CheckJsonKeys('project', config_json, _PROJECT_CONFIG_KEYS)
  project_name = config_json[u'name']
  project = MoeProjectConfig(project_name)
  project.empty = False
  project.filename = config_json.get(u'filename') or filename

  project.translators = config_json.get(u'translators', [])

  project.internal_repository_config = MakeRepositoryConfig(
      config_json[u'internal_repository'],
      repository_name=project_name + '_internal',
      project_space=base.INTERNAL_STR)

  project.public_repository_config = MakeRepositoryConfig(
      config_json[u'public_repository'],
      repository_name=project_name + '_public',
      project_space=base.PUBLIC_STR)

  project.noisy_files_re = config_json.get('noisy_files_re')
  project.moe_db_url = config_json.get('moe_db_url')
  project.owners = config_json.get('owners', [])
  project.manual_equivalence_deltas = config_json.get(
      'manual_equivalence_deltas')
  project.import_strategy = _MigrationStrategyFromJson(
      config_json.get(u'import_strategy'),
      default_strategy=project.import_strategy)
  project.export_strategy = _MigrationStrategyFromJson(
      config_json.get(u'export_strategy'),
      default_strategy=project.export_strategy)

  project.config_json = config_json
  return project


def ParseConfigFile(filename):
  """Parse a JSON config file."""
  text = filename and file_util.Read(filename) or ''
  filename = os.path.abspath(filename)
  relative_name = config_utils.MakeConfigFilenameRelative(filename)
  return ParseConfigText(text, relative_name)


def MakeMoeProjectConfig():
  """Make the MOE project for this invocation.

  NB: may be empty

  Returns:
    config.MoeProjectConfig
  """
  name = FLAGS.project

  if not FLAGS.project_config_file:
    return None

  project = ParseConfigFile(FLAGS.project_config_file)
  if name and name != project.name:
    raise base.Error('Name "%s" from --project and name "%s" from config '
                     'differ.' % (name, project.name))
  return project


class EmptyRepositoryConfig(base.RepositoryConfig):
  """An empty repository config."""

  def __init__(self):
    self.additional_files_re = None

  def MakeRepository(self, translators=None):
    return None, None

  def Serialized(self):
    return {}

  def Info(self):
    return {'name': 'empty'}


def MakeRepositoryConfig(json_config, repository_name='', project_space=''):
  """Make the populate repository config from json.

  Args:
    json_config: json object
    repository_name: str, the name of the project this repository is in
    project_space: str

  Returns:
    base.RepositoryConfig
  """
  repository_type = json_config['type']
  if repository_type == 'svn':
    return svn.SvnRepositoryConfig(json_config,
                                   username=FLAGS.public_username,
                                   password=FLAGS.public_password,
                                   repository_name=repository_name,
                                   project_space=project_space)
  if repository_type == 'mercurial':
    return mercurial.MercurialRepositoryConfig(json_config,
                                               repository_name=repository_name,
                                               project_space=project_space)
  if repository_type == 'git':
    return git.GitRepositoryConfig(json_config,
                                   repository_name=repository_name,
                                   project_space=project_space)
  raise base.Error('unknown repository type: %s' % repository_type)


def ParseConfigText(text, filename=''):
  return MoeProjectConfigFromJson(config_utils.LoadConfig(text), filename)
