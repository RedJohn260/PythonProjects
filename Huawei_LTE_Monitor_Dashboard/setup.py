from distutils.core import setup, Extension
import os
import sys
import platform

# find pjsip version
pj_version = ""
pj_version_major = ""
pj_version_minor = ""
pj_version_rev = ""
pj_version_suffix = ""

with open('../../../version.mak', 'r') as f:
    for line in f:
        if "export PJ_VERSION_MAJOR" in line:
            tokens = line.split("=")
            if len(tokens) > 1:
                pj_version_major = tokens[1].strip()
        elif "export PJ_VERSION_MINOR" in line:
            tokens = line.split("=")
            if len(tokens) > 1:
                pj_version_minor = tokens[1].strip()
        elif "export PJ_VERSION_REV" in line:
            tokens = line.split("=")
            if len(tokens) > 1:
                pj_version_rev = tokens[1].strip()
        elif "export PJ_VERSION_SUFFIX" in line:
            tokens = line.split("=")
            if len(tokens) > 1:
                pj_version_suffix = tokens[1].strip()

if not pj_version_major:
    print('Unable to get PJ_VERSION_MAJOR')
    sys.exit(1)

pj_version = pj_version_major + "." + pj_version_minor
if pj_version_rev:
    pj_version += "." + pj_version_rev
if pj_version_suffix:
    pj_version += "-" + pj_version_suffix

# Get 'make' from environment variable if any
MAKE = os.environ.get('MAKE') or "make"

# Fill in pj_inc_dirs
pj_inc_dirs = []
with os.popen(f"{MAKE} -f helper.mak inc_dir") as f:
    for line in f:
        pj_inc_dirs.append(line.rstrip("\r\n"))

# Fill in pj_lib_dirs
pj_lib_dirs = []
with os.popen(f"{MAKE} -f helper.mak lib_dir") as f:
    for line in f:
        pj_lib_dirs.append(line.rstrip("\r\n"))

# Fill in pj_libs
pj_libs = []
with os.popen(f"{MAKE} -f helper.mak libs") as f:
    for line in f:
        pj_libs.append(line.rstrip("\r\n"))

# Mac OS X dependencies
extra_link_args = []
if platform.system() == 'Darwin':
    extra_link_args = ["-framework", "CoreFoundation",
                       "-framework", "AudioToolbox"]
    version = platform.mac_ver()[0].split(".")
    # OS X Lion (10.7.x) or above support
    if version[0] == '10' and int(version[1]) >= 7:
        extra_link_args += ["-framework", "AudioUnit"]

setup(
    name="pjsua",
    version=pj_version,
    description='SIP User Agent Library based on PJSIP',
    url='http://trac.pjsip.org/repos/wiki/Python_SIP_Tutorial',
    ext_modules=[Extension(
        "_pjsua",
        ["_pjsua.c"],
        define_macros=[('PJ_AUTOCONF', '1')],
        include_dirs=pj_inc_dirs,
        library_dirs=pj_lib_dirs,
        libraries=pj_libs,
        extra_link_args=extra_link_args
    )],
    py_modules=["pjsua"]
)