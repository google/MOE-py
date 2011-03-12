#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Stub entry points for MOE programs."""

__author__ = 'dborowitz@google.com (Dave Borowitz)'

from google.apputils import run_script_module


def RunPushCodebase():
  from moe import push_codebase
  return run_script_module.RunScriptModule(push_codebase)


def RunManageCodebases():
  from moe import manage_codebases
  return run_script_module.RunScriptModule(manage_codebases)


def RunInitCodebases():
  from moe import init_codebases
  return run_script_module.RunScriptModule(init_codebases)


def RunScrubber():
  from moe.scrubber import scrubber
  return run_script_module.RunScriptModule(scrubber)


def RunMoe():
  from moe import moe_main
  return run_script_module.RunScriptModule(moe_main)
