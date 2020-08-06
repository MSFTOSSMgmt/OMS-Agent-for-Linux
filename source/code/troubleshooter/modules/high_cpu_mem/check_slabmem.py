import os
import subprocess

from error_codes       import *
from errors            import error_info
from .check_cpu        import get_pkg_ver
from install.check_oms import comp_versions_ge

def check_strace():
    dne_errs = 0
    strace_errors = subprocess.Popen(['strace','-f','-e','trace=access','curl',"'https://www.google.com'"],\
                        stderr=subprocess.PIPE).communicate()[1]
    # count of doesnotexist errors
    for line in (strace_errors.decode('utf8').split('\n')):
        if (line.endswith('= -1 ENOENT (No such file or directory)')):
            dne_errs += 1
    return (dne_errs <= 300)


def check_nss_var(slabtop_10_pretty):
    try:
        nss_var = subprocess.check_output(['printenv','NSS_SDB_USE_CACHE'], universal_newlines=True)
        if (nss_var == 'yes\n'):
            error_info.append((slabtop_10_pretty,))
            return ERR_SLAB_BLOATED
        else:
            return ERR_SLAB_NSS

    # no variable named NSS_SDB_USE_CACHE
    except subprocess.CalledProcessError:
        return ERR_SLAB_NSS
                


def check_slab_memory():
    # no issues found
    if (check_strace()):
        return NO_ERROR

    # >300 DNE error messages called
    try:
        slabtop_output = subprocess.check_output(['slabtop','--once','--sort','c'],\
                            universal_newlines=True, stderr=subprocess.STDOUT)
        slabtop_lines = slabtop_output.split('\n')

        # get top 10 objects based on cache size
        # [ objs, active, use (%), obj size (K), slabs, obj/slab, cache size (K), name ]
        slabtop_10 = list(map((lambda x : x.split()), (slabtop_lines[7:17])))
        for slabtop_line in slabtop_10:

            # dentry in top 10
            if (slabtop_line[-1] == 'dentry'):
                nss_ver = get_pkg_ver('nss-softokn')
                if (comp_versions_ge(nss_ver, '3.14.3-12.el6')):
                    slabtop_10_pretty = slabtop_lines[6:17]
                    return check_nss_var(slabtop_10_pretty)
                else:
                    return ERR_SLAB_NSSSOFTOKN

        # dentry not in top 10
        return ERR_SLAB_BLOATED

    # errored in running slabtop
    except subprocess.CalledProcessError as e:
        if (e.output.endswith('Permission denied\n')):
            return ERR_SUDO_PERMS
        else:
            error_info.append((e.output,))
            return ERR_SLAB
