#! /usr/bin/env python3

import glob
import inspect
import os
import platform
import re
import shlex
import subprocess
import sys
import textwrap


pymupdf_dir = os.path.abspath(f'{__file__}/../..')

def log(message):
    print(message)

def run(command, env_extra=None):
    if env_extra is None:
        env_extra = {}
    env = os.environ.copy()
    env.update(env_extra)
    log(f'Running command: {command}')
    subprocess.run(command, shell=True, check=True, env=env)

def main():
    log('### main():')
    log(f'{platform.platform()=}')
    log(f'{platform.python_version()=}')
    log(f'{platform.architecture()=}')
    log(f'{platform.machine()=}')
    log(f'{platform.processor()=}')
    log(f'{platform.release()=}')
    log(f'{platform.system()=}')
    log(f'{platform.version()=}')
    log(f'{platform.uname()=}')
    log(f'{sys.executable=}')
    log(f'{sys.maxsize=}')
    log(f'sys.argv ({len(sys.argv)}):')
    for i, arg in enumerate(sys.argv):
        log(f'    {i}: {arg!r}')
    log(f'os.environ ({len(os.environ)}):')
    for k in sorted(os.environ.keys()):
        v = os.environ[k]
        log(f'    {k}: {v!r}')

    valgrind = False
    if len(sys.argv) == 1:
        args = iter(['build'])
    else:
        args = iter(sys.argv[1:])
    while True:
        try:
            arg = next(args)
        except StopIteration:
            break
        if arg == 'build':
            build(valgrind=valgrind)
        elif arg == 'build-devel':
            if platform.system() == 'Linux':
                p = 'linux'
            elif platform.system() == 'Windows':
                p = 'windows'
            elif platform.system() == 'Darwin':
                p = 'macos'
            else:
                assert 0, f'Unrecognised {platform.system()=}'
            build(platform_=p)
        elif arg == 'pip_install':
            prefix = next(args)
            d = os.path.dirname(prefix)
            log(f'{prefix=}')
            log(f'{d=}')
            for leaf in os.listdir(d):
                log(f'    {d}/{leaf}')
            pattern = f'{prefix}-*{platform_tag()}.whl'
            paths = glob.glob(pattern)
            log(f'{pattern=} {paths=}')
            awp = os.environ.get('AUDITWHEEL_PLAT')
            if awp:
                paths = [i for i in paths if awp in i]
                log(f'After selecting AUDITWHEEL_PLAT={awp!r}, {paths=}.')
            paths = ' '.join(paths)
            run(f'pip install {paths}')
        elif arg == 'venv':
            command = ['python', sys.argv[0]]
            for arg in args:
                command.append(arg)
            venv(command, packages='cibuildwheel')
        elif arg == 'test':
            project = next(args)
            package = next(args)
            # test(project, package, valgrind=valgrind)
        elif arg == '--valgrind':
            valgrind = int(next(args))
        else:
            assert 0, f'Unrecognised {arg=}'


def build(platform_=None, valgrind=False):
    log('### build():')

    platform_arg = f' --platform {platform_}' if platform_ else ''

    def get_bool(name, default=0):
        v = os.environ.get(name)
        if v in ('1', 'true'):
            return 1
        elif v in ('0', 'false'):
            return 0
        elif v is None:
            return default
        else:
            assert 0, f'Bad environ {name=} {v=}'
    inputs_flavours = get_bool('inputs_flavours', 1)
    inputs_sdist = get_bool('inputs_sdist')
    inputs_skeleton = os.environ.get('inputs_skeleton')
    inputs_wheels_default = get_bool('inputs_wheels_default', 1)
    inputs_wheels_linux_aarch64 = get_bool('inputs_wheels_linux_aarch64', inputs_wheels_default)
    inputs_wheels_linux_auto = get_bool('inputs_wheels_linux_auto', inputs_wheels_default)
    inputs_wheels_linux_pyodide = get_bool('inputs_wheels_linux_pyodide', 0)
    inputs_wheels_macos_arm64 = get_bool('inputs_wheels_macos_arm64', 0)
    inputs_wheels_macos_auto = get_bool('inputs_wheels_macos_auto', inputs_wheels_default)
    inputs_wheels_windows_auto = get_bool('inputs_wheels_windows_auto', inputs_wheels_default)
    inputs_wheels_cps = os.environ.get('inputs_wheels_cps')
    inputs_PYMUPDF_SETUP_MUPDF_BUILD = os.environ.get('inputs_PYMUPDF_SETUP_MUPDF_BUILD')
    inputs_PYMUPDF_SETUP_MUPDF_BUILD_TYPE = os.environ.get('inputs_PYMUPDF_SETUP_MUPDF_BUILD_TYPE')

    log(f'{inputs_flavours=}')
    log(f'{inputs_sdist=}')
    log(f'{inputs_skeleton=}')
    log(f'{inputs_wheels_default=}')
    log(f'{inputs_wheels_linux_aarch64=}')
    log(f'{inputs_wheels_linux_auto=}')
    log(f'{inputs_wheels_linux_pyodide=}')
    log(f'{inputs_wheels_macos_arm64=}')
    log(f'{inputs_wheels_macos_auto=}')
    log(f'{inputs_wheels_windows_auto=}')
    log(f'{inputs_wheels_cps=}')
    log(f'{inputs_PYMUPDF_SETUP_MUPDF_BUILD=}')
    log(f'{inputs_PYMUPDF_SETUP_MUPDF_BUILD_TYPE=}')

    if platform.system() == 'Linux' and inputs_wheels_linux_pyodide:
        GITHUB_EVENT_NAME = os.getenv('GITHUB_EVENT_NAME')
        if GITHUB_EVENT_NAME == 'schedule':
            if inputs_PYMUPDF_SETUP_MUPDF_BUILD in ('', None):
                log(f'Overriding inputs_PYMUPDF_SETUP_MUPDF_BUILD because {GITHUB_EVENT_NAME=} {inputs_PYMUPDF_SETUP_MUPDF_BUILD=}.')
                inputs_PYMUPDF_SETUP_MUPDF_BUILD = 'git:--branch master https://github.com/ArtifexSoftware/mupdf.git'
                log(f'{inputs_PYMUPDF_SETUP_MUPDF_BUILD=}')
        build_pyodide_wheel(inputs_PYMUPDF_SETUP_MUPDF_BUILD)

    if inputs_sdist:
        if pymupdf_dir != os.path.abspath(os.getcwd()):
            log(f'Changing dir to {pymupdf_dir=}')
            os.chdir(pymupdf_dir)
        run(f'{sys.executable} setup.py sdist')
        assert glob.glob('dist/PyMuPDF-*.tar.gz')
        if inputs_flavours:
            run(
                    f'{sys.executable} setup.py sdist',
                    env_extra=dict(PYMUPDF_SETUP_FLAVOUR='b'),
                    )
            assert glob.glob('dist/PyMuPDFb-*.tar.gz')

    if (0
            or inputs_wheels_linux_aarch64
            or inputs_wheels_linux_auto
            or inputs_wheels_macos_arm64
            or inputs_wheels_macos_auto
            or inputs_wheels_windows_auto
            ):
        env_extra = dict()

        def set_if_unset(name, value):
            v = os.environ.get(name)
            if v is None:
                log(f'Setting environment {name=} to {value=}')
                env_extra[name] = value
            else:
                log(f'Not changing {name}={v!r} to {value!r}')
        set_if_unset('CIBW_BUILD_VERBOSITY', '3')
        set_if_unset('CIBW_SKIP', 'pp* *i686 cp36* cp37* *musllinux*aarch64* cp313-win32')

        def make_string(*items):
            ret = list()
            for item in items:
                if item:
                    ret.append(item)
            return ' '.join(ret)

        cps = inputs_wheels_cps if inputs_wheels_cps else 'cp38* cp39* cp310* cp311* cp312*'
        set_if_unset('CIBW_BUILD', make_string(
                cps,
                '*musllinux*aarch64*',
                ))
        # set_if_unset('CIBW_TEST_REQUIRES', 'pytest')
        set_if_unset('CIBW_ENVIRONMENT', 'CIBW_BUILD_VERBOSITY={CIBW_BUILD_VERBOSITY} CIBW_SKIP={CIBW_SKIP}')

        def update_default(arg, default_value):
            if arg is None:
                return default_value
            else:
                return arg

        cibw_platform = 'linux_aarch64 linux_auto macos_arm64 macos_auto windows_auto'
        run(
                'cibuildwheel --no-use-pep517 --output-dir wheelhouse --verbosity 3 '
                f'{platform_arg}'
                f'--env {make_string(*env_extra)} '
                )

        if inputs_skeleton:
            if inputs_skeleton == 'full':
                run(f'python scripts/make_skeleton.py')
            else:
                run(f'python scripts/make_skeleton.py --custom {inputs_skeleton}')

        if inputs_wheels_cps:
            assert 0, f'{inputs_wheels_cps=} not yet implemented.'

        if inputs_PYMUPDF_SETUP_MUPDF_BUILD:
            if inputs_PYMUPDF_SETUP_MUPDF_BUILD_TYPE == 'source':
                build_mupdf(inputs_PYMUPDF_SETUP_MUPDF_BUILD)

        if platform.system() == 'Darwin':
            log('macOS does not need special handling')

        if platform.system() == 'Windows':
            log('Windows does not need special handling')

        if valgrind:
            log('Running under valgrind')
            run(f'valgrind --leak-check=full {sys.executable} setup.py build', env_extra=dict(PATH='/usr/bin'))

        if platform.system() == 'Linux':
            if inputs_wheels_linux_auto:
                run(f'python -m pip install --no-cache-dir --disable-pip-version-check --extra-index-url https://wheels.artifex.com --find-links wheelhouse --pre --upgrade')
            if inputs_wheels_linux_aarch64:
                run(f'python -m pip install --no-cache-dir --disable-pip-version-check --extra-index-url https://wheels.artifex.com --find-links wheelhouse --pre --upgrade')
            if inputs_wheels_linux_pyodide:
                run(f'python -m pip install --no-cache-dir --disable-pip-version-check --extra-index-url https://wheels.artifex.com --find-links wheelhouse --pre --upgrade')

def build_mupdf(mupdf_build):
    log('### build_mupdf():')
    log(f'{mupdf_build=}')
    assert mupdf_build.startswith(('git:', 'url:'))
    assert platform.system() == 'Linux'
    command = f'python scripts/build_mupdf.py {mupdf_build}'
    run(command)

def build_pyodide_wheel(mupdf_build):
    log('### build_pyodide_wheel():')
    log(f'{mupdf_build=}')
    assert platform.system() == 'Linux'
    command = f'python scripts/build_pyodide_wheel.py {mupdf_build}'
    run(command)

def venv(command, packages=None):
    log(f'Creating virtual environment with command: {command}')
    run(f'python -m venv .venv')
    run(f'.venv/bin/pip install --upgrade pip setuptools wheel')
    if packages:
        run(f'.venv/bin/pip install {packages}')

def test(project, package, valgrind=False):
    log(f'Running tests on {project} {package}')
    if valgrind:
        run(f'valgrind --leak-check=full pytest {project}/{package}')
    else:
        run(f'pytest {project}/{package}')

def platform_tag():
    system = platform.system().lower()
    arch = platform.architecture()[0]
    if system == 'linux':
        if arch == '64bit':
            return 'manylinux_2_28_x86_64'
        else:
            return 'manylinux_2_28_i686'
    elif system == 'darwin':
        if arch == '64bit':
            return 'macosx_10_15_x86_64'
        else:
            return 'macosx_10_15_i386'
    elif system == 'windows':
        if arch == '64bit':
            return 'win_amd64'
        else:
            return 'win32'
    else:
        return ''

if __name__ == '__main__':
    main()
