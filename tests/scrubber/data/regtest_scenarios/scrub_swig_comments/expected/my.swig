

/* MOE Test Swig file.
 * 
 * This is private and public text.
 * 
 */

%module mymodule
%{
#include "header.h"
#include "public_utils.h"
#include "public_only_header.h"

%}
extern int foo(double);
extern double bar(int, int);
extern void dump(FILE *f);

