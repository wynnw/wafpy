# vim:softtabstop=4:ts=4:sw=4:expandtab:tw=120:ft=python
"""Python project commands and utilities

Configuration - create a dictionary in your top level wscript file like so:

pytools_options = {
    pyenv_dir: "<name of virtualenv directory - defaults to 'pyenv'>",
    sdists_dir: "<name of cached sdists directory - defaults to '.sdists'>",
    setup_hook: <callable that is called before creating the virtualenv>,
    pip_hook: <callable that is called after creating the virtualenv>,
    sources: <list of relative paths from top level that are the project sources>,
    dbschema_hook: <callable that is called after creating/updating the dbschema>,
    manage: <python module string for the manage.py file>,
    sys_vardir: <callable that returns the path to the system var directory>,
}

Notes:
    - The pyenv_dir may be an absolute path.
    - The setup_hook function should be used to do any system provisioning required - i.e. install
      packages with yum, run salt scripts, etc.
    - The pip_hook function should be used to do pip installations. It is passed a build context parameter which will
      have a pyd member that is a PyenvData instance. It's pyenv_install method should be used to install various
      requirement text files using the local sdists cache.

"""
import abc, os, pwd, tempfile

from waflib import Build, Configure, Context, Errors, Logs, Options  #pylint: disable=F0401
from .utils import projopts_get


def options(ctx):
    """Add command line options for the build"""
    ctx.add_option("--localdir", action="store", default=None,
            help="Specify a local path to store the build and pyenv directories in " \
                 "(use when the source tree is a network share.)")
    ctx.add_option("--sys-python", action="store", default="python2.7",
            help="Specify the system python binary to use to create the virtualenv.")
    ctx.add_option("--mod", action="store", default=None,
            help="Specify a comma separated list of modules to run for test or pylint")
    ctx.add_option("--stdout", action="store_true", default=False,
            help="Print pyflakes/pylint output to stdout instead of a build logfile")

    ctx.load("python")


def configure(ctx):
    ctx.env.PREFIX = "/"
    ctx.env.BINDIR = "/bin"
    ctx.env.LIBDIR = "/lib"

    ctx.load("python")
    ctx.check_python_version()


## Internal methods for looking up pytools options
def _sources(ctx):
    return projopts_get(ctx, 'pytools', 'sources', ())


def _pyenv_dir(ctx):
    return projopts_get(ctx, 'pytools', 'pyenv_dir', 'pyenv')


def _sdists_dir(ctx):
    return projopts_get(ctx, 'pytools', 'sdists_dir', '.sdists')


class PyenvData(object):
    def __init__(self, ctx, pyenv_path=None):
        self.ctx = ctx
        self.pyenv_ = pyenv_path
        self.curruser = pwd.getpwuid(os.getuid()).pw_name
        self._sys_vardir = None

    @property
    def pyenv(self):
        """Return the path for the pyenv (the python virtualenvironment)"""
        if self.pyenv_ is None:
            pyenv_dir = _pyenv_dir(self.ctx)
            if pyenv_dir[0] != '/':
                pyenv_root = (self.ctx and self.ctx.env.PYENV_ROOT) or self.ctx.path.abspath()
                self.pyenv_ = os.path.join(pyenv_root, _pyenv_dir(self.ctx))
            else:
                self.pyenv_ = pyenv_dir

            if not os.path.exists(self.pyenv_):
                os.makedirs(self.pyenv_, mode=0755)
        return self.pyenv_

    @property
    def pythondir(self):
        pycmd = "from distutils.sysconfig import get_python_lib; print get_python_lib()"
        return self.ctx.cmd_and_log([self.python, '-c', pycmd], output=Context.STDOUT).strip()
    def var(self, subdir):
        """Return the path to the subdir in the pyenv var directory"""
        varpath = os.path.join(self.pyenv, "var", subdir)
        if not os.path.exists(varpath):
            os.makedirs(varpath, mode=0755)
        return varpath

    @property
    def tmp(self):
        """Return the path to the pyenv tmp directory"""
        return self.var("tmp")

    @property
    def cache(self):
        """Return the path to the pyenv cache directory"""
        return self.var("cache")

    @property
    def log(self):
        """Return the path to the pyenv log directory"""
        return self.var("log")

    @property
    def etc(self):
        """Return the path to the pyenv etc directory"""
        etcpath = os.path.join(self.pyenv, "etc")
        if not os.path.exists(etcpath):
            os.makedirs(etcpath, mode=0755)
        return etcpath

    def prog(self, util_name):
        """Return the path to the pyenv program located in the pyenv bin directory"""
        rval = os.path.join(self.pyenv, "bin", util_name)
        if not os.path.exists(rval):
            raise Exception("pyenv utility(%s) does not exist" % util_name)
        return rval

    def mkdtmp(self):
        """Return a newly created temporary directory in the pyenv tmp dir"""
        return tempfile.mkdtemp(dir=self.tmp)

    @property
    def python(self):
        """Return the path to the virtualenv python"""
        return self.prog("python")

    @property
    def pip(self):
        """Return the path to the virtualenv pip"""
        return self.prog("pip")

    @property
    def pylint(self):
        """Return the path to the virtualenv pylint"""
        return self.prog("pylint")

    @property
    def sys_vardir(self):
        if self._sys_vardir is None:
            self._sys_vardir = projopts_get(self.ctx, "pytools", "sys_vardir", None)
            if self._sys_vardir is None:
                raise Exception("You must define the wscript pytools[sys_vardir] configuration option")
        return self._sys_vardir

    def activate(self):
        f = self.prog("activate_this.py")
        execfile(f, dict(__file__=f))

    @property
    def shared_srcroot(self):
        """Return true if the source root is a network share (i.e. it belongs to a mounted directory)"""
        # find the mount point for our source root
        mount_point = self.ctx.path.abspath()
        while not os.path.ismount(mount_point):
            mount_point = os.path.dirname(mount_point)

        # find the file system type for the mount point
        shared_folder_fs_types = ["cifs", "vboxsf"]  # TODO: get more possible filesystem types (i.e. vmware, etc.
        with open("/proc/mounts", "r") as mounts:
            for line in mounts:
                parts = line.split()
                mount_point_, mount_impl = parts[1], parts[2]
                if mount_point_ == mount_point:
                    if mount_impl in shared_folder_fs_types:
                        return True
        return False

    def pyenv_create(self):
        """Create a virtualenv using the bundled virtualenv utility"""
        ve = os.path.join(os.path.dirname(__file__), 'virtualenv.py')
        self.ctx.exec_command([Options.options.sys_python, ve, self.pyenv])

    def pyenv_install(self, requirements, paths=None, local_only=True, cache_only_dir=None):
        env = os.environ.copy()
        if paths:
            env["PATH"] = ":".join([env["PATH"]] + paths)
        args = [self.pip, "install", "-r", requirements]
        if local_only:
            args.extend(["--no-index", "--find-links=file://%s/.sdists" % self.ctx.path.abspath()])
        if cache_only_dir:
            args.extend(["-d", cache_only_dir])
        self.ctx.exec_command(args, env=env)

    def pyenv_add_src_pth(self, extra_paths=None):
        if extra_paths is None: extra_paths = []
        pythondir = self.pythondir
        relpath = os.path.relpath(self.ctx.path.abspath(), pythondir)
        projname = os.path.basename(self.ctx.path.abspath())
        with open(os.path.join(pythondir, projname + ".pth"), "w") as pth:
            pth.write(relpath + "\n")
            for extra_path in extra_paths:
                pth.write(relpath + '/' + extra_path + "\n")

    def pyenv_collectstatic(self):
        mm = projopts_get(self.ctx, 'pytools', 'manage', None)
        self.ctx.exec_command([self.python, '-m', mm, 'collectstatic', '--noinput'])


class PythonCleanCommand(Build.CleanContext):
    """Override for the builtin clean command that also deletes pyc files"""
    cmd = "clean"
    def clean(self):  #pylint: disable=E1002
        super(PythonCleanCommand, self).clean()

        Logs.debug("cleaning L2L *.pyc files")
        for subdir in _sources(self):
            #pylint: disable=E1101
            subdirpath = os.path.join(self.path.abspath(), subdir)
            self.exec_command(["find", subdirpath, "-name", "*.pyc", "-delete"])


class ContextUtilsMixin(object):
    """mixin class that provides Context utilities.
    Must be used with a valid waf Context base class.
    """
    def __init__(self, **kwargs):
        super(ContextUtilsMixin, self).__init__(**kwargs)
        self.pyd = PyenvData(self)

    def exec_command(self, cmd, **kwargs):
        ret = super(ContextUtilsMixin, self).exec_command(cmd, **kwargs)
        if ret != 0:
            raise Errors.WafError("command(%r) failed with code(%r)" % (cmd, ret))

    def run_impl(self, impl):
        # run with a custom logger
        logpath = os.path.join(self.out_dir if self.out_dir else Context.out_dir, self.cmd + ".log")
        self.logger = Logs.make_logger(logpath, self.cmd)  #pylint: disable=W0201
        try:
            impl()
        except:
            if hasattr(self, "in_msg"):
                self.end_msg("FAILED\nlog is at: " + logpath)
            raise


class CustomBuildCommandMixin(ContextUtilsMixin):
    """abstract base class for commands that need to load the configuration cache"""
    def execute(self):
        self.load_envs()  # load the cached configuration context, pylint: disable=E1101
        self.run_impl(self.impl)

    @abc.abstractmethod
    def impl(self): pass


class SetupCommand(ContextUtilsMixin, Configure.ConfigurationContext):
    """Setup the pyenv environment"""
    cmd = "setup"

    def __init__(self, **kw):
        self.pyd = PyenvData(self)
        super(SetupCommand, self).__init__(**kw)

    def execute(self):
        self._set_out_dir()  # figure out what the build/pyenv directories should be
        self.init_dirs()  # ConfigurationContext initialization of the build directory
        self.run_impl(self.impl)  # run our setup logic
        super(SetupCommand, self).execute()  # run the actual configure command (calls the configure() function)

    def _set_out_dir(self):
        """runs to determine if we need to have a build/pyenv prefix if the srcroot is from a network share"""
        if Options.options.localdir or self.pyd.shared_srcroot:
            homedir = Options.options.localdir if Options.options.localdir else os.environ["HOME"]
            outdir_root = os.path.basename(self.path)  #pylint: disable=E1101
            pyenv_root = os.path.join(homedir, outdir_root + "-dirs")
            out_dir = os.path.join(pyenv_root, "build")
        else:
            out_dir = os.path.join(self.path.abspath(), "build")  #pylint: disable=E1101
            pyenv_root = self.path.abspath()  #pylint: disable=E1101

        self.out_dir = out_dir  # pylint: disable=W0201
        self.env.PYENV_ROOT = pyenv_root  #pylint: disable=E1101

    def impl(self):
        """Implementation of the virtualenv creation logic"""
        #1) call out to project specific system provisioning hook
        setuphook = projopts_get(self, 'pytools', 'setup_hook', None, callfunc=False)
        if setuphook:
            self.start_msg("Running setup hook")
            setuphook(self)
            self.end_msg("ok")

        #2) create the virtualenv
        self.start_msg("Creating virtualenv at: %s" % self.pyd.pyenv)
        self.pyd.pyenv_create()
        self.end_msg("ok")

        #3) install a pth file for the project sources to the pyenv
        self.start_msg("Installing pth file for virtualenv")
        self.pyd.pyenv_add_src_pth(_sources(self))
        self.end_msg("ok")

        #4) call the pip-requirements installation hook
        piphook = projopts_get(self, 'pytools', 'pip_hook', None, callfunc=False)
        if piphook:
            self.start_msg("Running pip installations")
            piphook(self)
            self.end_msg("ok")