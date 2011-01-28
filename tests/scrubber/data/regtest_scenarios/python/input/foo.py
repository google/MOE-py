#!/usr/bin/env python

import path_magic

import toplevel

from mycompany123.internal import mymodule
from mycompany123.internal.foo import myothermodule
from mycompany123.internal.bar import something as bars


if __name__ == '__main__':
  print 'foo'
