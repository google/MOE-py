# Why Moe? #

MOE helps one project live in two repositories. If you only ever want your code to be used in one repository, you should stop reading now.

# Why is this Hard? #

Some people know how to command git or mercurial to dance to their command, and have no need for MOE.

MOE is useful in the face of:
  * users who are not git/hg wizards
  * source control system heterogeneity
  * having differences between the internal and public codebases. This last reason gives rise to the concept of Project Spaces

# Concepts #

With MOE, you describe your project's two Repositories:

A Repository is a source control repository that stores your project. It offers:
  * way to get metadata about what has happened in that repository
  * way to construct a Codebase at a revision.

A Codebase is a set of files with their contents and metadata (for now, only their executable bits).

We assume that these repositories are in different ProjectSpace s: i.e., they should always be different. (For background on why this might be useful, check out ProjectSpace s).

A Translator takes a Codebase in one ProjectSpace and creates a Codebase in another ProjectSpace. The Identity Translator does nothing (in the case that you expect the two ProjectSpace s to always be equal). More complex translators like the ScrubberInvokingTranslator and UndoScrubbingTranslator (which will exist soon) allow you to maintain differences.

A Revision is known in each Repository by a different name (a changeset in mercurial; a revision in subversion; a commit in git, etc.).

A Migration is an attempt to take code from one Repository (at one Revision) and move it to another Revision. This may include attempting to translate it (via a translator) and copy metadata (such as a Revision description, or author, or time/data of commit), and submit it to another Repository.

MOE is a toolkit for acting on these concepts.

# What Next #

If you don't know anyone else using MOE, it sounds like you're using MOE at a new site. See NewMoeSite .

If your site is already using moe, then see SetUpMoe to get your project up to speed.