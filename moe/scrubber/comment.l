/*
Flex program to extract C-like comments.
Works with (at least) C, C++, Go and JS.

Probably works with lex too, but using flex
will avoid any kind of fixed-size buffer length limits
imposed on comments.
*/

%{
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

#include <utf.h>

static void save(char*, int);
static void quote(char*, int);
static void yyerror(const char* s);
int check_usage_and_initialize(int argc, char **argv);
int get_next_file(void);

extern FILE *yyin;

char *filename;
char **filenames;
int num_files;
int lineno;
int char_index;
int exitcode;

/* Whether we're in the first comment, for appropriate comma insertion. */
static int first;

%}

%option nounput

/* When in unterminated state, just consume characters until EOF. */
%x UNTERM

CCOMMENT        [/][*]([^*]+|[*]+([^*/]|\n)|\n)*[*]+[/]
CPPCOMMENT      [/][/][^\n]*
CSTRING         ["]([^\\"]|\\.)*["]
CCHAR           [']([^\\']|\\.)*[']

%%
{CCOMMENT}      save(yytext, yyleng); char_index += utflen(yytext);
{CPPCOMMENT}    save(yytext, yyleng); char_index += utflen(yytext);
{CSTRING}       {
                    /* ignore. TODO(dbentley): scrub string literals */
                    char_index += utflen(yytext);
                }
{CCHAR}         {
                    /* Ignore. C char constant or js string literal. */
                    char_index += utflen(yytext);
                }
[/][*]          yyerror("unterminated constant"); BEGIN(UNTERM);
["]             yyerror("unterminated double-quote string"); BEGIN(UNTERM);
[']             yyerror("unterminated single-quote string"); BEGIN(UNTERM);
\n              lineno++; char_index += yyleng;
<*>.            {
                  // . matches individual bytes. But we want to count
                  // characters. So, we only increment on bytes that start a new
                  // character. What bytes do that? Well, put it the other way:
                  // what bytes do not start a new character? Answer: those
                  // that start with the bits 10. Which is 2 in binary.
                  // So, we shift the byte over 6 bits, then if it's 2, don't
                  // count a new character.
                  // Cf. http://research.swtch.com/2010/03/utf-8-bits-bytes-and-benefits.html
                  if (yytext[0] >> 6 != 2) {
                    char_index += 1;
                  }
                }
<*><<EOF>>      if (get_next_file()) yyterminate(); BEGIN(0);
%%

int
get_next_file(void) {
  if (num_files > 0) {
    filename = filenames[0];
    yyin = fopen(filename, "r");
    if (NULL == yyin) {
      fprintf(stderr, "Couldn't open filename %s\n", filename);
      return -1;
    }
    lineno = 1;
    char_index = 0;
    --num_files;
    ++filenames;
    return 0;
  } else {
    return -1;
  }
}

int
yywrap(void)
{
  return -1;
}

int
main(int argc, char **argv)
{
  if (check_usage_and_initialize(argc, argv)) {
    return 1;
  }

  printf("[");
  yylex();
  printf("\n]\n");
  return 0;
}

int
check_usage_and_initialize(int argc, char **argv)
{
  if (argc < 4) {
    fprintf(stderr, "usage: %s line char_index filename...\n", argv[0]);
    return 1;
  }
  lineno = atoi(argv[1]);
  char_index = atoi(argv[2]);
  if (lineno < 0 || char_index < 0) {
    fprintf(stderr,
            "Invalid range: line number and char index must be >= 0.\n");
    return 1;
  }
  num_files = argc - 3;
  filenames = argv + 3;
  // A line number of 0 means scan the given file(s). Otherwise, scan stdin.
  if (lineno != 0) {
    if (num_files > 1) {
      fprintf(stderr, "error: Can't scan range of multiple files.");
      return 1;
    }
    num_files = 0;
    filename = filenames[0];
  } else {
    // Load first file (or yyin defaults to stdin).
    if (get_next_file()) {
      return 1;
    }
  }
  first = 1;
  return 0;
}

static void
save(char *p, int n)
{
  int i;

  // Print JSON output block.
  if (first)
    first = 0;
  else
    printf(",\n");
  printf("\n{\n");
  if (filename != NULL) {
    printf("\"filename\": \"");
    quote(filename, strlen(filename));
    printf("\", ");
  }
  printf("\"line\": %d, ", lineno);
  printf("\"char_index\": %d, \"text\": \"", char_index);
  quote(p, n);
  printf("\"\n}");

  // Account for newlines in text.
  for (i = 0; i < n; i++)
    if (p[i] == '\n')
      lineno++;
}

static void
quote(char *p, int n)
{
  int i;

  for (i = 0; i < n; i++) {
    /* JSON allows Unicode in string literals, so only the following
     * need special casing; see http://json.org/ */
    switch (p[i]) {
      case '"':
      case '\\':
        printf("\\%c", p[i]);
        break;
      case '\b':
        printf("\\b");
        break;
      case '\f':
        printf("\\f");
        break;
      case '\n':
        printf("\\n");
        break;
      case '\r':
        printf("\\r");
        break;
      case '\t':
        printf("\\t");
        break;
      default:
        printf("%c", p[i]);
        break;
    }
  }
}

static void
yyerror(const char* s)
{
  if (filename == NULL)
    fprintf(stderr, "line %d: ", lineno);
  else
    fprintf(stderr, "%s:%d: ", filename, lineno);
  fprintf(stderr, "%s\n", s);
  exitcode = 1;
}
