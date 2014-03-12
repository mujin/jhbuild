# jhbuild - a tool to ease building collections of source packages
# Copyright (C) 2001-2006  James Henstridge
# Copyright (C) 2007-2008  Frederic Peters
# Copyright (C) 2014 Canonical Limited
#
#   environment.py: environment variable setup
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

import sys
import os

from jhbuild.errors import FatalError, CommandError
from jhbuild.utils.cmds import get_output

def addpath(envvar, path):
    '''Adds a path to an environment variable.'''
    # special case ACLOCAL_FLAGS
    if envvar in [ 'ACLOCAL_FLAGS' ]:
        if sys.platform.startswith('win'):
            path = jhbuild.utils.subprocess_win32.fix_path_for_msys(path)

        envval = os.environ.get(envvar, '-I %s' % path)
        parts = ['-I', path] + envval.split()
        i = 2
        while i < len(parts)-1:
            if parts[i] == '-I':
                # check if "-I parts[i]" comes earlier
                for j in range(0, i-1):
                    if parts[j] == '-I' and parts[j+1] == parts[i+1]:
                        del parts[i:i+2]
                        break
                else:
                    i += 2
            else:
                i += 1
        envval = ' '.join(parts)
    elif envvar in [ 'LDFLAGS', 'CFLAGS', 'CXXFLAGS' ]:
        if sys.platform.startswith('win'):
            path = jhbuild.utils.subprocess_win32.fix_path_for_msys(path)

        envval = os.environ.get(envvar)
        if envval:
            envval = path + ' ' + envval
        else:
            envval = path
    else:
        if envvar == 'PATH':
            # PATH is special cased on Windows to allow execution without
            # sh.exe. The other env vars (like LD_LIBRARY_PATH) don't mean
            # anything to native Windows so they stay in UNIX format, but
            # PATH is kept in Windows format (; separated, c:/ or c:\ format
            # paths) so native Popen works.
            pathsep = os.pathsep
        else:
            pathsep = ':'
            if sys.platform.startswith('win'):
                path = jhbuild.utils.subprocess_win32.fix_path_for_msys(path)

            if sys.platform.startswith('win') and len(path) > 1 and \
               path[1] == ':':
                # Windows: Don't allow c:/ style paths in :-separated env vars
                # for obvious reasons. /c/ style paths are valid - if a var is
                # separated by : it will only be of interest to programs inside
                # MSYS anyway.
                path='/'+path[0]+path[2:]

        envval = os.environ.get(envvar, path)
        parts = envval.split(pathsep)
        parts.insert(0, path)
        # remove duplicate entries:
        i = 1
        while i < len(parts):
            if parts[i] in parts[:i]:
                del parts[i]
            elif envvar == 'PYTHONPATH' and parts[i] == "":
                del parts[i]
            else:
                i += 1
        envval = pathsep.join(parts)

    os.environ[envvar] = envval

def setup_env_defaults(system_libdirs):
    '''default "system values" for environment variables that are not already set'''

    # PKG_CONFIG_PATH
    if os.environ.get('PKG_CONFIG_PATH') is None:
        for dirname in reversed(system_libdirs + ['/usr/share']):
            full_name = os.path.join(dirname, 'pkgconfig')
            if os.path.exists(full_name):
                addpath('PKG_CONFIG_PATH', full_name)

    # GI_TYPELIB_PATH
    if not 'GI_TYPELIB_PATH' in os.environ:
        for dirname in reversed(system_libdirs):
            full_name = os.path.join(dirname, 'girepository-1.0')
            if os.path.exists(full_name):
                addpath('GI_TYPELIB_PATH', full_name)

    # XDG_DATA_DIRS
    if not 'XDG_DATA_DIRS' in os.environ:
        os.environ['XDG_DATA_DIRS'] = '/usr/local/share:/usr/share'

    # XDG_CONFIG_DIRS
    if not 'XDG_CONFIG_DIRS' in os.environ:
        XDG_CONFIG_DIRS='/etc/xdg'

    # get rid of gdkxft from the env -- it will cause problems.
    if os.environ.has_key('LD_PRELOAD'):
        valarr = os.environ['LD_PRELOAD'].split(' ')
        for x in valarr[:]:
            if x.find('libgdkxft.so') >= 0:
                valarr.remove(x)
        os.environ['LD_PRELOAD'] = ' '.join(valarr)

def setup_env(prefix):
    '''set environment variables for using prefix'''

    os.environ['JHBUILD_PREFIX'] = prefix

    os.environ['UNMANGLED_LD_LIBRARY_PATH'] = os.environ.get('LD_LIBRARY_PATH', '')

    if not os.environ.get('DBUS_SYSTEM_BUS_ADDRESS'):
        # Use the distribution's D-Bus for the system bus. JHBuild's D-Bus
        # will # be used for the session bus
        os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = 'unix:path=/var/run/dbus/system_bus_socket'

    # LD_LIBRARY_PATH
    libdir = os.path.join(prefix, 'lib')
    addpath('LD_LIBRARY_PATH', libdir)
    os.environ['JHBUILD_LIBDIR'] = libdir

    # LDFLAGS and C_INCLUDE_PATH are required for autoconf configure
    # scripts to find modules that do not use pkg-config (such as guile
    # looking for gmp, or wireless-tools for NetworkManager)
    # (see bug #377724 and bug #545018)

    # This path doesn't always get passed to addpath so we fix it here
    if sys.platform.startswith('win'):
        libdir = jhbuild.utils.subprocess_win32.fix_path_for_msys(libdir)
    os.environ['LDFLAGS'] = ('-L%s ' % libdir) + os.environ.get('LDFLAGS', '')

    includedir = os.path.join(prefix, 'include')
    addpath('C_INCLUDE_PATH', includedir)
    addpath('CPLUS_INCLUDE_PATH', includedir)

    # On Mac OS X, we use DYLD_FALLBACK_LIBRARY_PATH
    addpath('DYLD_FALLBACK_LIBRARY_PATH', libdir)

    # PATH
    bindir = os.path.join(prefix, 'bin')
    addpath('PATH', bindir)

    # MANPATH
    manpathdir = os.path.join(prefix, 'share', 'man')
    addpath('MANPATH', '')
    addpath('MANPATH', manpathdir)

    # INFOPATH
    infopathdir = os.path.join(prefix, 'share', 'info')
    addpath('INFOPATH', infopathdir)

    # PKG_CONFIG_PATH
    pkgconfigdatadir = os.path.join(prefix, 'share', 'pkgconfig')
    pkgconfigdir = os.path.join(libdir, 'pkgconfig')
    addpath('PKG_CONFIG_PATH', pkgconfigdatadir)
    addpath('PKG_CONFIG_PATH', pkgconfigdir)

    # GI_TYPELIB_PATH
    typelibpath = os.path.join(libdir, 'girepository-1.0')
    addpath('GI_TYPELIB_PATH', typelibpath)

    # XDG_DATA_DIRS
    xdgdatadir = os.path.join(prefix, 'share')
    addpath('XDG_DATA_DIRS', xdgdatadir)

    # XDG_CONFIG_DIRS
    xdgconfigdir = os.path.join(prefix, 'etc', 'xdg')
    addpath('XDG_CONFIG_DIRS', xdgconfigdir)

    # XCURSOR_PATH
    xcursordir = os.path.join(prefix, 'share', 'icons')
    addpath('XCURSOR_PATH', xcursordir)

    # GST_PLUGIN_PATH
    gstplugindir = os.path.join(libdir , 'gstreamer-0.10')
    if os.path.exists(gstplugindir):
        addpath('GST_PLUGIN_PATH', gstplugindir)

    # GST_PLUGIN_PATH_1_0
    gstplugindir = os.path.join(libdir , 'gstreamer-1.0')
    if os.path.exists(gstplugindir):
        addpath('GST_PLUGIN_PATH_1_0', gstplugindir)

    # GST_REGISTRY
    gstregistry = os.path.join(prefix, '_jhbuild', 'gstreamer-0.10.registry')
    addpath('GST_REGISTRY', gstregistry)

    # GST_REGISTRY_1_0
    gstregistry = os.path.join(prefix, '_jhbuild', 'gstreamer-1.0.registry')
    addpath('GST_REGISTRY_1_0', gstregistry)

    # ACLOCAL_PATH
    aclocalpath = os.path.join(prefix, 'share', 'aclocal')
    addpath('ACLOCAL_PATH', aclocalpath)

    # ACLOCAL_FLAGS
    aclocaldir = os.path.join(prefix, 'share', 'aclocal')
    if not os.path.exists(aclocaldir):
        try:
            os.makedirs(aclocaldir)
        except:
            raise FatalError(_("Can't create %s directory") % aclocaldir)
    if os.path.exists('/usr/share/aclocal'):
        addpath('ACLOCAL_FLAGS', '/usr/share/aclocal')
        if os.path.exists('/usr/local/share/aclocal'):
            addpath('ACLOCAL_FLAGS', '/usr/local/share/aclocal')
    addpath('ACLOCAL_FLAGS', aclocaldir)

    # PERL5LIB
    perl5lib = os.path.join(prefix, 'lib', 'perl5')
    addpath('PERL5LIB', perl5lib)

    # These two variables are so that people who use "jhbuild shell"
    # can tweak their shell prompts and such to show "I'm under jhbuild".
    # The first variable is the obvious one to look for; the second
    # one is for historical reasons.
    os.environ['UNDER_JHBUILD'] = 'true'
    os.environ['CERTIFIED_GNOMIE'] = 'yes'

    # PYTHONPATH
    # Python inside jhbuild may be different than Python executing jhbuild,
    # so it is executed to get its version number (fallback to local
    # version number should never happen)
    python_bin = os.environ.get('PYTHON', 'python')
    try:
        pythonversion = 'python' + get_output([python_bin, '-c',
            'import sys; print(".".join([str(x) for x in sys.version_info[:2]]))'],
            get_stderr = False).strip()
    except CommandError:
        pythonversion = 'python' + str(sys.version_info[0]) + '.' + str(sys.version_info[1])
        if 'PYTHON' in os.environ:
            logging.warn(_('Unable to determine python version using the '
                           'PYTHON environment variable (%s). Using default "%s"')
                         % (os.environ['PYTHON'], pythonversion))

    # In Python 2.6, site-packages got replaced by dist-packages, get the
    # actual value by asking distutils
    # <http://bugzilla.gnome.org/show_bug.cgi?id=575426>
    try:
        python_packages_dir = get_output([python_bin, '-c',
            'import os, distutils.sysconfig; '\
            'print(distutils.sysconfig.get_python_lib(prefix="%s").split(os.path.sep)[-1])' % prefix],
            get_stderr=False).strip()
    except CommandError:
        python_packages_dir = 'site-packages'
        if 'PYTHON' in os.environ:
            logging.warn(_('Unable to determine python site-packages directory using the '
                           'PYTHON environment variable (%s). Using default "%s"')
                         % (os.environ['PYTHON'], python_packages_dir))

    pythonpath = os.path.join(prefix, 'lib', pythonversion, python_packages_dir)
    addpath('PYTHONPATH', pythonpath)
    if not os.path.exists(pythonpath):
        os.makedirs(pythonpath)

    # if there is a Python installed in JHBuild prefix, set it in PYTHON
    # environment variable, so it gets picked up by configure scripts
    # <http://bugzilla.gnome.org/show_bug.cgi?id=560872>
    if os.path.exists(os.path.join(prefix, 'bin', 'python')):
        os.environ['PYTHON'] = os.path.join(prefix, 'bin', 'python')

    # Mono Prefixes
    os.environ['MONO_PREFIX'] = prefix
    os.environ['MONO_GAC_PREFIX'] = prefix

    # GConf:
    # Create a GConf source path file that tells GConf to use the data in
    # the jhbuild prefix (in addition to the data in the system prefix),
    # and point to it with GCONF_DEFAULT_SOURCE_PATH so modules will be read
    # the right data (assuming a new enough libgconf).
    gconfdir = os.path.join(prefix, 'etc', 'gconf')
    gconfpathdir = os.path.join(gconfdir, '2')
    if not os.path.exists(gconfpathdir):
        os.makedirs(gconfpathdir)
    gconfpath = os.path.join(gconfpathdir, 'path.jhbuild')
    if not os.path.exists(gconfpath) and os.path.exists('/etc/gconf/2/path'):
        try:
            inp = open('/etc/gconf/2/path')
            out = open(gconfpath, 'w')
            for line in inp.readlines():
                if '/etc/gconf' in line:
                    out.write(line.replace('/etc/gconf', gconfdir))
                out.write(line)
            out.close()
            inp.close()
        except:
            traceback.print_exc()
            raise FatalError(_('Could not create GConf config (%s)') % gconfpath)
    os.environ['GCONF_DEFAULT_SOURCE_PATH'] = gconfpath

    # Set GCONF_SCHEMA_INSTALL_SOURCE to point into the jhbuild prefix so
    # modules will install their schemas there (rather than failing to
    # install them into /etc).
    os.environ['GCONF_SCHEMA_INSTALL_SOURCE'] = 'xml:merged:' + os.path.join(
            gconfdir, 'gconf.xml.defaults')
