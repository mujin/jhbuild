# jhbuild - a build script for GNOME 1.x and 2.x
# Copyright (C) 2001-2002  James Henstridge
#
#   module.py: logic for running the build.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import os
import cvs

_isxterm = os.environ.get('TERM','') == 'xterm'
_boldcode = os.popen('tput bold', 'r').read()
_normal = os.popen('tput sgr0', 'r').read()
user_shell = os.environ.get('SHELL', '/bin/sh')

class _Struct:
    pass

if not hasattr(__builtins__, 'True'):
    True = 1
    False = 0

class Package:
    STATE_START = 'start'
    STATE_DONE  = 'done'
    def __init__(self, name, dependencies=[]):
        self.name = name
        self.dependencies = dependencies
    def __repr__(self):
        return "<%s '%s'>" % (self.__class__.__name__, self.name)

    def get_builddir(self, buildscript):
        pass

    def run_state(self, buildscript, state):
        '''run a particular part of the build for this package.

        Returns a tuple of the following form:
          (next-state, error-flag, [other-states])'''
        method = getattr(self, 'do_' + state)
        return method(buildscript)


class CVSModule(Package):
    STATE_CHECKOUT       = 'checkout'
    STATE_FORCE_CHECKOUT = 'force_checkout'
    STATE_CONFIGURE      = 'configure'
    STATE_BUILD          = 'build'
    STATE_INSTALL        = 'install'

    def __init__(self, cvsmodule, checkoutdir=None, revision=None,
                 autogenargs='', dependencies=[], cvsroot=None):
        Package.__init__(self, checkoutdir or cvsmodule, dependencies)
        self.cvsmodule   = cvsmodule
        self.checkoutdir = checkoutdir
        self.revision    = revision
        self.autogenargs = autogenargs
        self.cvsroot     = cvsroot

    def get_builddir(self, buildscript):
        return os.path.join(buildscript.config.checkoutroot,
                            self.checkoutdir or self.cvsmodule)

    def do_start(self, buildscript):
        checkoutdir = self.get_builddir(buildscript)
        if not buildscript.config.nonetwork: # normal start state
            return (self.STATE_CHECKOUT, None, None)
        elif buildscript.config.nobuild:
            return (self.STATE_DONE, None, None)
        elif not buildscript.config.alwaysautogen and \
                 os.path.exists(os.path.join(checkoutdir, 'Makefile')):
            return (self.STATE_BUILD, None, None)
        else:
            return (self.STATE_CONFIGURE, None, None)

    def do_checkout(self, buildscript, force_checkout=False):
        if self.cvsroot:
            cvsroot = cvs.CVSRoot(self.cvsroot,buildscript.config.checkoutroot)
        else:
            cvsroot = buildscript.cvsroot
        checkoutdir = self.get_builddir(buildscript)
        buildscript.message('checking out %s' % self.name)
        res = cvsroot.update(buildscript, self.cvsmodule,
                             self.revision, self.checkoutdir)

        if buildscript.config.nobuild:
            nextstate = self.STATE_DONE
        elif not buildscript.config.alwaysautogen and \
                 os.path.exists(os.path.join(checkoutdir, 'Makefile')):
            nextstate = self.STATE_BUILD
        else:
            nextstate = self.STATE_CONFIGURE
        # did the checkout succeed?
        if res == 0 and os.path.exists(checkoutdir):
            return (nextstate, None, None)
        else:
            return (nextstate, 'could not update module',
                    [self.STATE_FORCE_CHECKOUT])

    def do_force_checkout(self, buildscript):
        if self.cvsroot:
            cvsroot = cvs.CVSRoot(self.cvsroot,buildscript.config.checkoutroot)
        else:
            cvsroot = buildscript.cvsroot

        checkoutdir = self.get_builddir(buildscript)
        buildscript.message('checking out %s' % self.name)
        res = cvsroot.checkout(buildscript, self.cvsmodule,
                               self.revision, self.checkoutdir)
        if res == 0 and os.path.exists(checkoutdir):
            return (self.STATE_CONFIGURE, None, None)
        else:
            return (self.STATE_CONFIGURE, 'could not checkout module',
                    [self.STATE_FORCE_CHECKOUT])

    def do_configure(self, buildscript):
        checkoutdir = self.get_builddir(buildscript)
        os.chdir(checkoutdir)
        buildscript.message('running configure for %s' % self.name)
        cmd = './autogen.sh --prefix %s %s %s' % \
              (buildscript.config.prefix, buildscript.config.autogenargs,
               self.autogenargs)
        if buildscript.execute(cmd) == 0:
            return (self.STATE_BUILD, None, None)
        else:
            return (self.STATE_MAKE, 'could not configure module',
                    [self.STATE_FORCE_CHECKOUT])

    def do_build(self, buildscript):
        os.chdir(self.get_builddir(buildscript))
        buildscript.message('running build for %s' % self.name)
        cmd = 'make %s' % buildscript.config.makeargs
        if buildscript.execute(cmd) == 0:
            return (self.STATE_INSTALL, None, None)
        else:
            return (self.STATE_INSTALL, 'could not build module',
                    [self.STATE_FORCE_CHECKOUT])

    def do_install(self, buildscript):
        os.chdir(self.get_builddir(buildscript))
        buildscript.message('running install for %s' % self.name)
        cmd = 'make %s install' % buildscript.config.makeargs
        error = None
        if buildscript.execute(cmd) != 0:
            error = 'could not make module'
        return (self.STATE_DONE, error, [])

class MetaModule(Package):
    def get_builddir(self, buildscript):
        return buildscript.config.checkoutroot
    # nothing to actually build in a metamodule ...
    def do_start(self, buildscript):
        return (self.STATE_DONE, None, None)

class Tarball(Package):
    STATE_DOWNLOAD = 'download'
    STATE_UNPACK   = 'unpack'
    STATE_PATCH    = 'patch'
    STATE_BUILD    = 'build'
    STATE_INSTALL  = 'install'
    def __init__(self, name, version, source_url, source_size,
                 patches=[], versioncheck=None, dependencies=[]):
        Package.__init__(self, package, dependencies)
        self.version      = version
        self.source_url   = source_url
        self.source_size  = source_size
        self.patches      = []
        self.versioncheck = versioncheck

    def get_builddir(self, buildscript):
        localfile = os.path.basename(self.source_url)
        # strip off packaging extension ...
        if localfile[-7:] == '.tar.gz':
            localfile = localfile[:-7]
        elif localfile[-8:] == '.tar.bz2':
            localfile = localfile[:-8]
        elif localfile[-4:] == '.tgz':
            localfile = localfile[:-4]
        return os.path.join(buildscript.config.checkoutroot, localfile)

    def do_start(self, buildscript):
        # check to see if tarball is already installed ...
        # ...
        # return (self.STATE_DONE, None, None)
        # else download and build it
        return (self.STATE_DOWNLOAD, None, None)

    def do_download(self, buildscript):
        localfile = os.path.join(buildscript.config.checkoutroot,
                                 os.path.basename(self.source_url))
        if not buildscript.config.nonetwork:
            if not os.path.exists(localfile) or \
                   os.stat(localfile)[6] != self.source_size:
                buildscript.message('downloading %s' % self.source_url)
                res = buildscript.execute('wget "%s" -O "%s"' %
                                          (self.source_url, localfile))
                if res != 0:
                    return (self.STATE_UNPACK, 'error downloading file', [])

        if not os.path.exists(localfile) or \
               os.stat(localfile)[6] != self.source_size:
            return (self.STATE_UNPACK,
                    'file not downloaded, or of incorrect size', [])
        return (self.STATE_UNPACK, None, None)

    def do_unpack(self, buildscript):
        os.chdir(buildscript.config.checkoutroot)
        localfile = os.path.basename(self.sourceurl)
        checkoutdir = self.get_builddir(buildscript)

        buildscript.message('unpacking %s', self.name)
        if localfile[-4:] == '.bz2':
            res = buildscript.execute('bunzip2 -dc %s | tar xf -' % localfile)
        else:
            res = buildscript.execute('gunzip -dc %s | tar xf -' % localfile)

        if res != 0 or not os.path.exists(checkoutdir):
            return (self.STATE_PATCH, 'could not unpack tarball', [])

        return (self.STATE_PATCH, None, None)

    def do_patch(self, buildscript):
        os.chdir(self.get_builddir(buildscript))
        for patch in self.patches:
            patchfile = os.path.join(os.path.dirname(__file__), patch[0])
            buildscript.message('applying patch %s' % patch[0])
            res = buildscript.execute('patch -p%d < %s' % (patch[1],patchfile))
            if res != 0:
                return (self.STATE_BUILD, 'could not apply patch', [])
        return (self.STATE_BUILD, None, None)

    def do_build(self, buildscript):
        os.chdir(self.get_builddir(buildscript))
        buildscript.message('running build for %s' % self.name)
        cmd = 'make %s' % buildscript.config.makeargs
        if buildscript.execute(cmd) == 0:
            return (self.STATE_INSTALL, None, None)
        else:
            return (self.STATE_INSTALL, 'could not build module', [])

    def do_install(self, buildscript):
        os.chdir(self.get_builddir(buildscript))
        buildscript.message('running install for %s' % self.name)
        cmd = 'make %s install' % buildscript.config.makeargs
        error = None
        if buildscript.execute(cmd) != 0:
            error = 'could not make module'
        return (self.STATE_DONE, error, [])

class ModuleSet:
    def __init__(self, baseset=None):
        self.modules = {}
        if baseset:
            self.modules.update(baseset.modules)
    def add(self, module):
        '''add a Module object to this set of modules'''
        self.modules[module.name] = module
    def addmod(self, *args, **kwargs):
        mod = apply(CVSModule, args, kwargs)
        self.add(mod)

    # functions for handling dep expansion
    def __expand_mod_list(self, modlist, skip):
        '''expands a list of names to a list of Module objects.  Expands
        dependencies.  Does not handle loops in deps''' #"
        ret = [ self.modules[modname]
                for modname in modlist if modname not in skip ]
        i = 0
        while i < len(ret):
            depadd = []
            for depmod in [ self.modules[modname]
                            for modname in ret[i].dependencies ]:
                if depmod not in ret[:i+1] and depmod.name not in skip:
                    depadd.append(depmod)
            if depadd:
                ret[i:i] = depadd
            else:
                i = i + 1
        i = 0
        while i < len(ret):
            if ret[i] in ret[:i]:
                del ret[i]
            else:
                i = i + 1
        return ret

    def get_module_list(self, seed, skip=[]):
        '''gets a list of module objects (in correct dependency order)
        needed to build the modules in the seed list''' #"
        ret = [ self.modules[modname]
                for modname in seed if modname not in skip ]
        i = 0
        while i < len(ret):
            depadd = []
            for depmod in [ self.modules[modname]
                            for modname in ret[i].dependencies ]:
                if depmod not in ret[:i+1] and depmod.name not in skip:
                    depadd.append(depmod)
            if depadd:
                ret[i:i] = depadd
            else:
                i = i + 1
        i = 0
        while i < len(ret):
            if ret[i] in ret[:i]:
                del ret[i]
            else:
                i = i + 1
        return ret
    def get_full_module_list(self, skip=[]):
        return self.get_module_list(self.modules.keys(), skip=skip)


class BuildScript:
    def __init__(self, configdict, module_list):
        self.modulelist = module_list
        self.module_num = 0

        self.config = _Struct
        self.config.autogenargs = configdict.get('autogenargs',
                                                 '--disable-static --disable-gtk-doc')
        self.config.makeargs = configdict.get('makeargs', '')
        self.config.prefix = configdict.get('prefix', '/opt/gtk2')
        self.config.nobuild = configdict.get('nobuild', False)
        self.config.nonetwork = configdict.get('nonetwork', False)
        self.config.alwaysautogen = configdict.get('alwaysautogen', False)
        self.config.makeclean = configdict.get('makeclean', True)

        self.config.checkoutroot = configdict.get('checkoutroot')
        if not self.config.checkoutroot:
            self.config.checkoutroot = os.path.join(os.environ['HOME'], 'cvs','gnome')
        self.cvsroot = cvs.CVSRoot(configdict['cvsroot'],
                                   self.config.checkoutroot)

        assert os.access(self.config.prefix, os.R_OK|os.W_OK|os.X_OK), \
               'install prefix must be writable'

    def message(self, msg):
        '''shows a message to the screen'''
        if self.module_num > 0:
            percent = ' [%d/%d]' % (self.module_num, len(self.modulelist))
        else:
            percent = ''
        print '%s*** %s ***%s%s' % (_boldcode, msg, percent, _normal)
        if _isxterm:
            print '\033]0;jhbuild: %s%s\007' % (msg, percent)

    def execute(self, command):
        '''executes a command, and returns the error code'''
        print command
        ret = os.system(command)
        print
        return ret

    def build(self):
        poison = [] # list of modules that couldn't be built

        self.module_num = 0
        for module in self.modulelist:
            self.module_num = self.module_num + 1
            poisoned = 0
            for dep in module.dependencies:
                if dep in poison:
                    self.message('module %s not built due to non buildable %s'
                                 % (module.name, dep))
                    poisoned = True
            if poisoned:
                poison.append(module.name)
                continue

            state = module.STATE_START
            while state != module.STATE_DONE:
                nextstate, error, altstates = module.run_state(self, state)

                if error:
                    newstate = self.handle_error(module, state,
                                                 nextstate, error, altstates)
                    if newstate == 'poison':
                        poison.append(module.name)
                        state = module.STATE_DONE
                    else:
                        state = newstate
                else:
                    state = nextstate
        if len(poison) == 0:
            self.message('success')
        else:
            self.message('the following modules were not built')
            for module in poison:
                print module,
            print

    def handle_error(self, module, state, nextstate, error, altstates):
        '''handle error during build'''
        self.message('error during stage %s of %s: %s' % (state, module.name,
                                                          error))
        while True:
            print
            print '  [1] rerun stage %s' % state
            print '  [2] ignore error and continue to %s' % nextstate
            print '  [3] give up on module'
            print '  [4] start shell'
            i = 5
            for altstate in altstates:
                print '  [%d] go to stage %s' % (i, altstate)
                i = i + 1
            val = raw_input('choice: ')
            if val == '1':
                return state
            elif val == '2':
                return nextstate
            elif val == '3':
                return 'poison'
            elif val == '4':
                checkoutdir = self.cvsroot.getcheckoutdir(module.cvsmodule,
                                                          module.checkoutdir)
                os.chdir(checkoutdir)
                print 'exit shell to continue with build'
                os.system(user_shell)
            else:
                try:
                    val = int(val)
                    return altstates[val - 5]
                except:
                    print 'invalid choice'

