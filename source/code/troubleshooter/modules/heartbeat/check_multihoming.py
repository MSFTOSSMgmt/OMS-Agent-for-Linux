# INSPIRED BY update_mgmt_health_check.py

import os

from error_codes import *
from errors      import error_info

def check_multihoming(workspace):
    directories = []
    potential_workspaces = []

    for (dirpath, dirnames, filenames) in os.walk("/var/opt/microsoft/omsagent"):
        directories.extend(dirnames)
        break # Get the top level of directories

    for directory in directories:
        if len(directory) >= 32:
            potential_workspaces.append(directory)
    workspace_id_list = ', '.join(potential_workspaces)

    # 2+ potential workspaces
    if len(potential_workspaces) > 1:
        error_info.append((workspace_id_list))
        return ERR_MULTIHOMING

    # 0 potential workspaces
    if (len(potential_workspaces) == 0):
        missing_dir = "/var/opt/microsoft/omsagent/{0}".format(workspace)
        error_info.append(('Directory', missing_dir))
        return ERR_FILE_MISSING

    # 1 incorrect workspace
    if (potential_workspaces[0] != workspace):
        error_info.append(potential_workspaces[0], workspace)
        return ERR_GUID

    # 1 correct workspace
    return NO_ERROR
        