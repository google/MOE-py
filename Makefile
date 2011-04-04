# Edit these to your needs.

PREFIX=/usr/local
UTFPREFIX=/usr/local

CC=gcc
CFLAGS=-I$(UTFPREFIX)/include

LEX=flex
LEXFLAGS=

PYTHON=python
PYBUILDFLAGS=
PYTESTFLAGS=
PYINSTALLFLAGS=

# End configuration options.

COMMENT=moe/scrubber/comment

all: comment py

install: comment
	$(PYTHON) setup.py install $(PYINSTALLFLAGS)

check: comment
	$(PYTHON) setup.py google_test $(PYTESTFLAGS)

py: comment
	$(PYTHON) setup.py build $(PYBUILDFLAGS)

comment: $(COMMENT)

$(COMMENT): $(COMMENT).yy.c $(UTFPREFIX)/lib/libutf.a
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^

$(COMMENT).yy.c: $(COMMENT).l
	$(LEX) $(LEXFLAGS) -o $@ $<

clean:
	rm -f $(COMMENT) $(COMMENT).yy* && $(PYTHON) setup.py clean
