# Introduction #

The summary is, set up the moe config, then run moe init. moe diff\_codebases will help, once it exists

# Details #

## MOE Config ##

The MOE config is a JSON file that describes the project's metadata, its repositories, and its translators. Here is a sample moe config:

```

{
 "name": "sample",
 "internal_repository": {
  "type": "svn",
  "url": "http://path.svn.server"
 },
 "public_repository": {
  "type": "mercurial",
  "url": "http://some-other-svn-server"
 },
 "translators" : [
   {
   "from_project_space": "internal",
   "to_project_space": "public",
   "type": "identity"
  },
  {
   "from_project_space": "public",
   "to_project_space": "internal",
   "type": "identity"
  }
 ],
 "moe_db_url": "http://localhost:8080"
}

```

For more info, see MoeConfig

## moe init ##

To read the moe config at /path/to/moe\_config.txt and push into the public repository the contents of the internal repository at [revision 1001](https://code.google.com/p/make-open-easy/source/detail?r=1001), run:

```
moe init --project_config_file /path/to/moe_config.txt --internal_revision 1001
```