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

char *filename;
int lineno;
int char_index;
int exitcode;

/* Whether we're in the first comment, for appropriate comma insertion. */
static int first;

%}

%option nounput

CCOMMENT	[/][*]([^*]+|[*]+([^*/]|\n)|\n)*[*]+[/]
CPPCOMMENT	[/][/][^\n]*
CSTRING		["]([^\\"]|\\.)*["]
CCHAR		[']([^\\']|\\.)*[']

%%
{CCOMMENT}	save(yytext, yyleng); char_index += utflen(yytext);
{CPPCOMMENT}	save(yytext, yyleng); char_index += utflen(yytext);
{CSTRING}	{
                    /* ignore. TODO(dbentley): scrub string literals */
                    char_index += utflen(yytext);
                }
{CCHAR}		{
                    /* Ignore. C char constant or js string literal. */
                    char_index += utflen(yytext);
                }
[/][*]		yyerror("unterminated constant"); return 0;
["]		yyerror("unterminated double-quote string"); return 0;
[']		yyerror("unterminated single-quote string"); return 0;
\n		lineno++; char_index += yyleng;
.               {
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

%%

int
yywrap(void)
{
	return -1;
}

int
main(int argc, char **argv)
{
	first = 1;
	if (argc == 2 || argc == 4) {
		printf("[");
		// Usage: comment filename [line char_index] << contents
		filename = argv[1];
		lineno = 1;
                char_index = 0;
		if (argc == 4) {
			lineno = atoi(argv[2]);
                        char_index = atoi(argv[3]);
		}
		yylex();
		printf("\n]\n");
		return 0;
	}

	fprintf(stderr, "usage: %s filename [line char_index]\n", argv[0]);
	return 1;
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
