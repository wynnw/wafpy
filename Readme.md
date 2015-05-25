## wafpy description
This project provides a custom version of waf that has been prebuilt with
several custom tasks and functionality to simplify the management of a python
project (with a focus on django).

The waf source code is in the repo as a git subtree. The top level Makefile is
used to generate the waf binary that has all the functionality bundled in. To
use it, just grab the waf binary and couple it with a wscript file.

The waf source was added with the following git command:

    $ git subtree add -P subtree-waf  --squash -m "Adding waf 1.8.10 as a subtree" https://github.com/waf-project/waf.git waf-1.8.10

To updated to newer waf releases, run:

    $ git subtree pull -P subtree-waf --squash -m "Upgrading waf to <version>" https://github.com/waf-project/waf.git <waf-tag>


# virtual environments
To simplify the creation of virtual environments, a copy of virtualenv is
bundled with the generated waf. The virtualenv sources are managed in this repo
as a git subtree. They were initially added with the following git command:

    $ git subtree add -P subtree-virtualenv --squash https://github.com/pypa/virtualenv.git 13.0.1

To upgrade to newer virtualenv releases, do the following:
    $ git subtree pull -P subtree-virtualenv --squash -m "Upgrading virtualenv to <version>" https://github.com/pypa/virtualenv.git <virtualenv-tag>