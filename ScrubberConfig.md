# Intro #
Scrubber config files are text files containing JSON objects. Any object keys or array entries beginning with "#" are treated as comments and ignored. The following configuration options are supported. All options are optional, so an empty JSON object is a valid configuration file.



# General options #

  * ignore\_files\_re: Regular expression of filenames to omit from scrubbing completely; this option should be used with care. Defaults to ignoring no files.
  * sensitive\_words: Array of words that must not be in the scrubbed output; the presence of a sensitive word causes scrubbing to fail unless that occurrence is whitelisted. Some heuristics are applied to search for words in camel case identifiers and so on.
  * whitelist: Array of objects for ignoring specified scrubber errors. Defaults to the empty array. Objects must have the following keys:
filter: String of the error type; currently, one of:
    * SENSITIVE\_WORD: Error on a sensitive word.
    * EMPTY\_JAVA: Error an a Java class file that is empty after scrubbing.
    * trigger: The item that triggered the error, e.g. the specific sensitive word.
    * filename: The file this whitelist entry applies to, or "`*`" for all files.

# User options #

The following options affect how usernames in TODO comments and language-specific author tags are treated. (To avoid false positives, usernames outside of TODO comments and author tags are not affected.)

  * username\_to\_scrub: String of one username that should be scrubbed, i.e. replaced with "user". May be repeated.
  * username\_to\_publish: String of username that can be published. May be repeated.
  * usernames\_file: Filename of a JSON object config file with publishable\_usernames and scrubbable\_usernames keys, interpreted the same as above. This allows a site to have a site-wide username configuration.
  * scrub\_unknown\_users: Bool; if true, all usernames not in usernames\_to\_publish will be scrubbed, i.e. replaced with "user". If false, usernames not in usernames\_to\_publish will result in an error; usernames in usernames\_to\_scrub will still be scrubbed. Defaults to false.
  * scrub\_authors: Bool; if true, language-specific author tags ( @author, // Author, and author) will be replaced with empty comment lines. Defaults to true.

# Java-specific options #

  * empty\_java\_file\_action: String of one of "IGNORE", "DELETE", or "ERROR", to ignore, delete, or raise an error on Java files that are effectively empty after scrubbing (except for comments, package delcarations, and imports).
  * maximum\_blank\_lines: Integer; if set, sequences of blank lines longer than this number will be coalesced into the maximum. Defaults to no coalescing.
  * annotations\_to\_scrub: Array of strings of Java annotation class names whose annotated declarations will be scrubbed. Defaults to the empty array.
  * scrub\_java\_testsize\_annotations: Bool; if true, SmallTest, Smoke, MediumTest, and LargeTest annotations will be stripped, with the declarations left intact. Defaults to false.

# Javascript-specific options #

  * js\_directory\_rename: Object specifying directory renames for Javascript source files. Implemented as a simple string search and replace. Defaults to no replacement. Must have the following keys:
    * internal\_directory: String of the internal directory name.
    * public\_directory: String of the public directory name.

# Python-specific options #

  * python\_module\_renames: Array of objects specifying rename rules for Python modules. An attempt is made to intelligently replace e.g. "import foo" with "import bar" but "from foo import baz" with "from bar import baz". If module names differ, a regex search is used to replace usages; note that depending on the module names, this may result in false positives. Defaults to the empty list. Objects have the following keys:
    * internal\_module: String of the fully-qualified internal module name.
    * public\_module: String of the fully-qualified public module name.
    * as\_name: Optional string of a name to import the public module as. Set this to the internal module name to avoid having to replace usages.
  * python\_module\_removes: Array of strings of fully-qualified module names to remove entirely. Defaults to the empty array.
  * python\_shebang\_replace: Object with a single key, shebang\_line, which is a string of the shebang line of outputted Python scripts. Defaults to no replacement.

# GWT-specific options #

  * scrub\_gwt\_inherits: Array of strings of GWT inherits to scrub. Each `<inherits>` element with a matching name attribute at will be removed from `*`.gwt.xml files. Note that the XML is entirely rewritten, so this may result in other semantically-neutral differences. Defaults to the empty array.

# Protobuf-specific options #

  * scrub\_proto\_comments: Bool; if true, apply scrubbing directives such as "MOE:insert" to .proto files.