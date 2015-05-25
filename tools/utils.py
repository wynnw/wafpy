#! /usr/bin/env python2.7
# encoding: utf-8
# vim:softtabstop=4:ts=4:sw=4:expandtab:tw=120
"""A waf build tool that provides compiler/configure script support utilities, and platform detection.

"""
import os, multiprocessing, subprocess

#pylint: disable=F0401
from waflib import Context, Logs, Options
from waflib.Errors import WafError
#pylint: enable=F0401


########################################################################################################################
##  Utility functions
########################################################################################################################
def sh(cmd, **kwargs):
    """Run a shell command that can print out to the console in real time, and raise a waf error for failures"""
    try:
        errmsg = kwargs.pop('errmsg', None)
        capture = kwargs.pop('capture', False)
        Logs.debug('runner: %r' % cmd)
        if capture:
            return subprocess.check_output(cmd, shell=True, **kwargs)
        else:
            subprocess.check_call(cmd, shell=True, **kwargs)
    except subprocess.CalledProcessError:
        if errmsg:
            print errmsg
        raise WafError(errmsg)


def load_env(cmd_env=None):
    """Return a copy of the existing environment extended with cmd_env"""
    runenv = os.environ.copy()
    if cmd_env:
        for key in cmd_env.keys():
            runenv[key] = cmd_env[key]

    return runenv


def find_abspath(exe):
    for path_dir in os.environ['PATH'].split(os.pathsep):
        path = os.path.join(path_dir, exe)
        if os.path.exists(path):
            return os.path.abspath(path)
    return None


def find_topdir(ctx):
    """return a string for absolute path to the top directory of the project"""
    if not hasattr(ctx, 'top_dir') or ctx.top_dir is None:
        topdir = ctx.path.abspath()
    else:
        topdir = ctx.top_dir
    return topdir


def find_proj_module(ctx, force_top):
    """return the python module for the top level wscript"""
    if not force_top:
        cur = getattr(ctx, 'cur_script', None)
        if cur is not None:
            if ctx.cur_script.abspath() in Context.cache_modules:
                return Context.cache_modules[ctx.cur_script.abspath()]
            else:
                raise WafError("couldn't find project module")

    wscript_dir = find_topdir(ctx)
    return Context.cache_modules[wscript_dir + '/wscript']


def projopts_get(ctx, tools_name, key, default, callfunc=True, force_top=True):
    """return a key value for the tool specific project options"""
    projopts = getattr(find_proj_module(ctx, force_top=force_top), tools_name + '_options', {})
    rval     = projopts.get(key, default)

    if hasattr(rval, '__call__') and callfunc:
        rval = rval(ctx)
    return rval


def autotools_build(ctx, srcpath, configure_opts, configure_create_cmd=None, cppflags=None, cflags=None):
    """Utility function meant to be used in a build rule for an autotools project that is building libraries.
    srcpath - a non-absolute path for the directory the project is in
    configure_opts - a string with extra configure options to add to the execution of the configure script
    configure_create_cmd - optional command to create the configure script if it does not exist. defaults to autoreconf
    cppflags - optional c++ compile flags to use
    cflags - optional c compile flags to use

    The project is build with it's prefix as the top build directory with a specific lib directory that is the
    build directory as well so that the libraries are easy to find. Any headers will be installed to build/include
    """
    bld     = ctx.generator.bld
    srcdir  = (bld.cur_script.parent if bld.cur_script else bld.path).find_dir(srcpath)
    cpus    = multiprocessing.cpu_count() + 1

    _env   = load_env({'CC': ctx.env.CC[0], 'CXX': ctx.env.CXX[0]})
    blddir = srcdir.get_bld()
    blddir.mkdir()

    if cppflags: _env["CPPFLAGS"] = cppflags
    if cflags:   _env["CFLAGS"] = cflags

    top_blddir = ctx.generator.bld.bldnode.abspath()

    # check if the configure script exists, if not we need to create it
    configure_path = os.path.join(srcdir.abspath(), 'configure')
    if not os.path.exists(configure_path):
        if configure_create_cmd is None:
            configure_create_cmd = "autoreconf -fiv"
        err = bld.exec_command(configure_create_cmd, cwd=srcdir.abspath())
        if err != 0:
            ctx.generator.bld.fatal("creating the configure script failed with error: %d" % err)
    else:
        # we've ran into weird problems building on older platforms where the configure script could be
        # regenerated if the timestamps from the initial git clone didn't match up (i.e. the Makefile.am's
        # were detected to be newer than the Makefile/configure files that are already checked in), and
        # the regenerated configure/Makefile produces build errors. So if we just touch the configure
        # script, then things work fine and we avoid the build errors
        fixfiles = ['aclocal.m4', 'Makefile.in', 'configure']
        for fixfile in fixfiles:
            fixfile_path = os.path.join(srcdir.abspath(), fixfile)
            if os.path.exists(fixfile_path):
                err = bld.exec_command('touch ' + fixfile_path)
                if err != 0:
                    ctx.generator.bld.fatal("updating the %s timestamp failed with error: %d" % (fixfile_path, err))

    # now check if the Makefile exists, if not we need to run configure
    makefile_path = os.path.join(blddir.abspath(), 'Makefile')
    if not os.path.exists(makefile_path):
        cmd = "%(srcdir)s/configure --prefix=%(top_blddir)s --libdir=%(top_blddir)s %(configure_opts)s" % \
                dict(srcdir=srcdir.abspath(), top_blddir=top_blddir, configure_opts=configure_opts)
        err = bld.exec_command(cmd, cwd=blddir.abspath(), env=_env)
        if err != 0:
            ctx.generator.bld.fatal("running the configure script failed with error: %d" % err)

    verbose_flag = "V=1" if Options.options.verbose >= 1 else ""
    err = bld.exec_command('make %s -j %d' % (verbose_flag, cpus), cwd=blddir.abspath(), env=_env)
    if err != 0:
        ctx.generator.bld.fatal("make failed with error: %d" % err)

    err = bld.exec_command('make install', cwd=blddir.abspath(), env=_env)
    if err != 0:
        ctx.generator.bld.fatal("make install failed with error: %d" % err)
