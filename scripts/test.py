#!/usr/bin/env python3

'''Developer build/test script for PyMuPDF.

Examples:

    ./PyMuPDF/scripts/test.py --mupdf mupdf buildtest
        Build and test with pre-existing local mupdf/ checkout.

    ./PyMuPDF/scripts/test.py buildtest
        Build and test with default internal download of mupdf.

    ./PyMuPDF/scripts/test.py --mupdf 'git:https://git.ghostscript.com/mupdf.git' buildtest
        Build and test with internal checkout of mupdf master.

    ./PyMuPDF/scripts/test.py --mupdf 'git:--branch 1.24.x https://github.com/ArtifexSoftware/mupdf.git' buildtest
        Build and test using internal checkout of mupdf 1.24.x branch from Github.

Usage:
    scripts/test.py <options> <command(s)>

* Commands are handled in order, so for example `build` should usually be
  before `test`.

* If we are not already running inside a Python venv, we automatically create a
  venv and re-run ourselves inside it.

* We build directly with pip (unlike gh_release.py, which builds with
  cibuildwheel).

* We run tests with pytest.

* One can generate call traces by setting environment variables in debug
  builds. For details see:
  https://mupdf.readthedocs.io/en/latest/language-bindings.html#environmental-variables

Options:
    --help
    -h
        Show help.
    -b <build>
        Set build type for `build` or `buildtest` commands. `<build>` should
        be one of 'release', 'debug', 'memento'. [This makes `build` set
        environment variable `PYMUPDF_SETUP_MUPDF_BUILD_TYPE`, which is used by
        PyMuPDF's `setup.py`.]
    -d
        Equivalent to `--build-type debug`.
    -f 0|1
        If 1 (the default) we also test alias `fitz` as well as `pymupdf`.
    -i <implementations>
        Set PyMuPDF implementations to test.
        <implementations> must contain only these individual characters:
             'r' - rebased.
             'R' - rebased without optimisations.
            Default is 'rR'. Also see `PyMuPDF:tests/run_compound.py`.
    -k <expression>
        Passed straight through to pytest's `-k`.
    -m <location> | --mupdf <location>
        Location of local mupdf/ directory or 'git:...' to be used
        when building PyMuPDF. [This sets environment variable
        PYMUPDF_SETUP_MUPDF_BUILD, which is used by PyMuPDF/setup.py. If not
        specified PyMuPDF will download its default mupdf .tgz.]
    -p <pytest-options>
        Set pytest options; default is ''.
    -t <names>
        Pytest test names, comma-separated. Should be relative to PyMuPDF
        directory. For example:
            -t tests/test_general.py
            -t tests/test_general.py::test_subset_fonts.
        To specify multiple tests, use comma-separated list and/or multiple `-t
        <names>` args.
    -v 0|1|2
        0 - do not use a venv.
        1 - Use venv. If it already exists, we assume the existing directory
            was created by us earlier and is a valid venv containing all
            necessary packages; this saves a little time.
        2 - use venv.
        The default is 2.
    --build-isolation 0|1
        If true (the default on non-OpenBSD systems), we let pip create and use
        its own new venv to build PyMuPDF. Otherwise we force pip to use the
        current venv.
    --build-flavour <build_flavour>
        Combination of 'p', 'b', 'd'. See ../setup.py's description of
        PYMUPDF_SETUP_FLAVOUR. Default is 'pb', i.e. self-contained PyMuPDF
        wheels without MuPDF build-time files.
    --build-mupdf 0|1
        Whether to rebuild mupdf when we build PyMuPDF. Default is 1.
    --gdb 0|1
        Run tests under gdb.
    --system-site-packages 0|1
        If 1, use `--system-site-packages` when creating venv.
    --timeout <seconds>
        Sets timeout when running tests.
    --valgrind 0|1
        Use valgrind in `test` or `buildtest`.
        This will run `apk add valgrind`.

Commands:
    build
        Builds and installs PyMuPDF into venv, using `pip install .../PyMuPDF`.
    buildtest
        Same as 'build test'.
    test
        Runs PyMuPDF's pytest tests in venv. Default is to test rebased and
        unoptimised rebased; use `-i` to change this.
    wheel
        Build wheel.

Environment:
    PYMUDF_SCRIPTS_TEST_options
        Is prepended to command line args.
'''

import gh_release

import glob
import os
import platform
import re
import shlex
import subprocess
import sys
import textwrap

pymupdf_dir = os.path.abspath(f'{__file__}/../..')

def main(argv):
    if len(argv) == 1:
        show_help()
        return

    build_isolation = None
    valgrind = False
    s = True
    build_do = 'i'
    build_type = None
    build_mupdf = True
    build_flavour = 'pb'
    gdb = False
    test_fitz = True
    implementations = None
    test_names = list()
    venv = 2
    pytest_options = None
    timeout = None
    pytest_k = None
    system_site_packages = False

    options = os.environ.get('PYMUDF_SCRIPTS_TEST_options', '')
    options = shlex.split(options)

    args = iter(options + argv[1:])
    i = 0
    while 1:
        try:
            arg = next(args)
        except StopIteration:
            arg = None
            break
        if not arg.startswith('-'):
            break
        elif arg == '-b':
            build_type = next(args)
        elif arg == '--build-isolation':
            build_isolation = int(next(args))
        elif arg == '-d':
            build_type = 'debug'
        elif arg == '-f':
            test_fitz = int(next(args))
        elif arg in ('-h', '--help'):
            show_help()
            return
        elif arg == '-i':
            implementations = next(args)
        elif arg in ('--mupdf', '-m'):
            mupdf = next(args)
            if not mupdf.startswith('git:'):
                assert os.path.isdir(mupdf), f'Not a directory: {mupdf=}.'
                mupdf = os.path.abspath(mupdf)
            os.environ['PYMUPDF_SETUP_MUPDF_BUILD'] = mupdf
        elif arg == '-k':
            pytest_k = next(args)
        elif arg == '-p':
            pytest_options  = next(args)
        elif arg == '--system-site-packages':
            system_site_packages = int(next(args))
        elif arg == '-t':
            test_names += next(args).split(',')
        elif arg == '--timeout':
            timeout = float(next(args))
        elif arg == '-v':
            venv = int(next(args))
        elif arg == '--build-flavour':
            build_flavour = next(args)
        elif arg == '--build-mupdf':
            build_mupdf = int(next(args))
        elif arg == '--gdb':
            gdb = int(next(args))
        elif arg == '--valgrind':
            valgrind = int(next(args))
        else:
            assert 0, f'Unrecognised option: {arg=}.'

    if arg is None:
        log(f'No command specified.')
        return

    commands = list()
    while 1:
        assert arg in ('build', 'buildtest', 'test', 'wheel'), \
                f'Unrecognised command: {arg=}.'
        commands.append(arg)
        try:
            arg = next(args)
        except StopIteration:
            break

    venv_quick = (venv==1)

    # Run inside a venv.
    if venv and sys.prefix == sys.base_prefix:
        # We are not running in a venv.
        log(f'Re-running in venv {gh_release.venv_name!r}.')
        gh_release.venv(
                ['python'] + argv,
                quick=venv_quick,
                system_site_packages=system_site_packages,
                )
        return

    def do_build():
        # Clone or update mupdf repo if necessary.
        if build_mupdf:
            log('Building mupdf ...')
            if mupdf.startswith('git:'):
                if not subprocess.call(['which', 'git']):
                    log('git not found.')
                    return
                git_url = mupdf[4:]
                git_args = [ 'git', 'clone' ]
                m = re.search(r'--branch (\S+)', git_url)
                if m:
                    git_args += ['--branch', m.group(1)]
                    git_url = re.sub(r'--branch \S+', '', git_url)
                git_args += [ git_url, 'mupdf' ]
                ret = subprocess.call(git_args)
                if ret == 0:
                    log('git clone successful')
                else:
                    log(f'git clone failed with code {ret}')
                    return
                if not os.path.isdir('mupdf/.git'):
                    log(f'Not a git repository: mupdf/.git')
                    return
            else:
                # Here we assume the mupdf directory is local.
                if not os.path.isdir('mupdf'):
                    os.makedirs('mupdf', exist_ok=True)
                    ret = subprocess.call(['cp', '-a', mupdf, 'mupdf'])
                    if ret:
                        log(f'Failed to copy: {ret}')
                        return
                elif os.path.abspath(mupdf) != os.path.abspath('mupdf'):
                    log(f'Expected mupdf to be at {os.path.abspath(mupdf)}.')
                    return
            log(f'Building PyMuPDF ...')
            if build_type:
                os.environ['PYMUPDF_SETUP_MUPDF_BUILD_TYPE'] = build_type
            else:
                os.environ.pop('PYMUPDF_SETUP_MUPDF_BUILD_TYPE', None)
            subprocess.check_call([
                    'pip', 'install',
                    '.[dev]'
                    ])
            subprocess.check_call([
                    'pip', 'install',
                    '--no-deps',
                    'PyMuPDF',
                    ])
            subprocess.check_call([
                    'pip', 'install',
                    '--no-deps',
                    '--ignore-installed',
                    'PyMuPDF',
                    ])
        else:
            log('Using pre-built PyMuPDF ...')

    def do_buildtest():
        do_build()
        subprocess.check_call(['pytest'] + pytest_options.split() + test_names)

    def do_test():
        do_build()
        subprocess.check_call([
                'pytest',
                *pytest_options.split(),
                *test_names,
                '-k', pytest_k,
                ])

    def log(msg):
        print(msg, file=sys.stderr)

    def show_help():
        print(textwrap.dedent(__doc__))

    # Run commands in order.
    for command in commands:
        if command == 'build':
            do_build()
        elif command == 'buildtest':
            do_buildtest()
        elif command == 'test':
            do_test()
        elif command == 'wheel':
            subprocess.check_call(['python', 'setup.py', 'bdist_wheel'])

if __name__ == '__main__':
    main(sys.argv)
