#!/usr/bin/env python


import pubtoplevel as toplevel

from mycompany.external import mymodule
from mycompany.external import myothermodule as foo
from mycompany.external.bar import something as bars


if __name__ == '__main__':
  print 'foo'
