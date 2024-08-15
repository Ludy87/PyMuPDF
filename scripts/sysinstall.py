#! /usr/bin/env python3

'''
Test for Linux system install of MuPDF and PyMuPDF on Alpine Linux.

We build and install MuPDF and PyMuPDF into a root directory, then use
scripts/test.py to run PyMuPDF's pytest tests with LD_PRELOAD_PATH and
PYTHONPATH set.

PyMuPDF itself is installed using `python -m install` with a wheel created with
`pip wheel`.

We run install commands with root privileges if `--root /` is used.

Note that we run some commands with root privileges; it's important that these use the
same python as non-root, otherwise things can be built and installed for
different python versions. For example when we are run from a github action, it
should not do `- uses: actions/setup-python@v5` but instead use whatever system
python is already defined.

Args:

    --mupdf-dir <mupdf_dir>
        Path of MuPDF checkout; default is 'mupdf'.
    --mupdf-do 0|1
        Whether to build and install mupdf.
    --mupdf-git <git_args>
        Get or update `mupdf_dir` using git. If `mupdf_dir` already
        exists we run `git pull` in it; otherwise we run `git
        clone` with `<git_args> <mupdf_dir>`. For example:
            --mupdf-git "--branch master https://github.com/ArtifexSoftware/mupdf.git"
    --mupdf-so-mode <mode>
        Used with `install -m <mode> ...` when installing MuPDF. For example
        `--mupdf-so-mode 744`.
    --packages 0|1
        If 1 (the default) we install required system packages such as
        `freetype-dev`.
    --pip 0|venv|sudo
        Whether/how to install Python packages.
        If '0' we assume required packages are already available.
        If 'sudo' we install required Python packages using `pip install
        ...`.
        If 'venv' (the default) we install Python packages and run installer
        and test commands inside venv's.
    --prefix:
        Directory within `root`; default is `/usr/local`. Must start with `/`.
    --pymupdf-dir <pymupdf_dir>
        Path of PyMuPDF checkout; default is 'PyMuPDF'.
    --pymupdf-do 0|1
        Whether to build and install pymupdf.
    --root <root>
        Root of install directory; default is `/`.
    --tesseract5 0|1
        If 1 (the default), we force installation of libtesseract-dev version
        5 (which is not available as a default package in Ubuntu-22.04) from
        package repository ppa:alex-p/tesseract-ocr-devel.
    --test-venv <test_venv>
        Set the name of the venv in which we run tests (only with `--pip
        venv`); the default is a hard-coded venv name. The venv will be
        created, and required packages installed using `pip`.
    --use-installer 0|1
        If 1 (the default), we use `python -m installer` to install PyMuPDF
        from a generated wheel. [Otherwise we use `pip install`, which refuses
        to do a system install with `--root /`, referencing PEP-668.]
    -i <implementations>
        Passed through to scripts/test.py.
    -f <test-fitz>
        Passed through to scripts/test.py.
    -p <pytest-options>
        Passed through to scripts/test.py.
    -t <names>
        Passed through to scripts/test.py.

To only show what commands would be run, but not actually run them, specify `-m
0 -p 0 -t 0`.
'''

import glob
import multiprocessing
import os
import platform
import shlex
import subprocess
import sys
import sysconfig

import test as test_py

# Requirements for a system build and install:
#
# system packages (Alpine names):
#
g_sys_packages = [
        'freetype-dev',
        'gumbo-dev',
        'harfbuzz-dev',
        'jbig2dec-dev',
        'jpeg-dev',
        'leptonica-dev',
        'openjpeg-dev',
        ]

# We also need tesseract5.
#

def main():

    if 1:
        print(f'## {__file__}: Starting.')
        print(f'{sys.executable=}')
        print(f'{platform.python_version()=}')
        print(f'{__file__=}')
        print(f'{sys.argv=}')
        print(f'{sysconfig.get_path("platlib")=}')
        run_command(f'python -V', check=0)
        run_command(f'python3 -V', check=0)
        run_command(f'su -c "python -V"', check=0)
        run_command(f'su -c "python3 -V"', check=0)
        run_command(f'su -c "PATH={os.environ["PATH"]} python -V"', check=0)
        run_command(f'su -c "PATH={os.environ["PATH"]} python3 -V"', check=0)

    # Set default behaviour.
    #
    use_installer = True
    mupdf_do = True
    mupdf_dir = 'mupdf'
    mupdf_git = None
    mupdf_so_mode = None
    packages = True
    prefix = '/usr/local'
    pymupdf_do = True
    pymupdf_dir = os.path.abspath(f'{__file__}/../..')
    root = 'sysinstall_test'
    tesseract5 = True
    pytest_args = None
    pytest_do = True
    pytest_name = None
    test_venv = 'venv-pymupdf-sysinstall-test'
    pip = 'venv'
    test_fitz = None
    test_implementations = None

    # Parse command-line.
    #
    args = iter(sys.argv[1:])
    while 1:
        try:
            arg = next(args)
        except StopIteration:
            break
        if arg in ('-h', '--help'):
            print(__doc__)
            return
        elif arg == '--mupdf-do':       mupdf_do = int(next(args))
        elif arg == '--mupdf-dir':      mupdf_dir = next(args)
        elif arg == '--mupdf-git':      mupdf_git = next(args)
        elif arg == '--mupdf-so-mode':  mupdf_so_mode = next(args)
        elif arg == '--packages':       packages = int(next(args))
        elif arg == '--prefix':         prefix = next(args)
        elif arg == '--pymupdf-do':     pymupdf_do = int(next(args))
        elif arg == '--pymupdf-dir':    pymupdf_dir = next(args)
        elif arg == '--root':           root = next(args)
        elif arg == '--tesseract5':     tesseract5 = int(next(args))
        elif arg == '--pytest-do':      pytest_do = int(next(args))
        elif arg == '--test-venv':      test_venv = next(args)
        elif arg == '--use-installer':  use_installer = int(next(args))
        elif arg == '--pip':            pip = next(args)
        elif arg == '-f':               test_fitz = next(args)
        elif arg == '-i':               test_implementations = next(args)
        elif arg == '-p':               pytest_args = next(args)
        elif arg == '-t':               pytest_name = next(args)
        else:
            assert 0, f'Unrecognised arg: {arg!r}'

    assert prefix.startswith('/')
    pip_values = ('0', 'sudo', 'venv')
    assert pip in pip_values, f'Unrecognised --pip value {pip!r} should be one of: {pip_values!r}'
    root = os.path.abspath(root)
    root_prefix = f'{root}{prefix}'.replace('//', '/')

    sudo = ''
    if root == '/':
        sudo = 'su -c "'

    def run(command):
        return run_command(command, check=1)

    if packages:
        if sudo:
            run(f'{sudo} apk update && apk add {" ".join(g_sys_packages)}"')
        else:
            run(f'apk update && apk add {" ".join(g_sys_packages)}')

    # Ensure the Python environment is set up correctly for the script execution.
    #
    if pip == 'sudo':
        run(f'{sudo} pip install --upgrade --force-reinstall pip setuptools')
    elif pip == 'venv':
        venv_cmd = f'python -m venv {test_venv}'
        run(venv_cmd)
        pip_cmd = f'{test_venv}/bin/pip install --upgrade --force-reinstall pip setuptools'
        run(pip_cmd)
    else:
        assert pip == '0'

    if pymupdf_do:
        if pymupdf_git:
            if os.path.exists(pymupdf_dir):
                run(f'cd {pymupdf_dir} && git pull {pymupdf_git}')
            else:
                run(f'git clone {pymupdf_git}')

        if sudo:
            run(f'{sudo} pip install pymupdf')
        else:
            run(f'pip install pymupdf')

    if mupdf_do:
        if sudo:
            run(f'{sudo} apk add gcc g++ make')

        if mupdf_git:
            if os.path.exists(mupdf_dir):
                run(f'cd {mupdf_dir} && git pull {mupdf_git}')
            else:
                run(f'git clone {mupdf_git}')

        if mupdf_so_mode:
            so_mode = f'install -m {mupdf_so_mode}'
        else:
            so_mode = 'install'

        run(f'cd {mupdf_dir} && make && {so_mode} mupdf /usr/local/bin')

    if pytest_do:
        test_cmd = f'python -m pytest {pytest_args} {pytest_name}'
        run(test_cmd)

def run_command(command, check=0):
    """Execute a shell command."""
    print(f'Running command: {command}')
    process = subprocess.run(shlex.split(command), check=check)
    return process.returncode

if __name__ == '__main__':
    main()
