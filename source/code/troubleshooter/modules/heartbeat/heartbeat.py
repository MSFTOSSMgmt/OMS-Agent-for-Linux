import re
import subprocess

from error_codes        import *
from errors             import error_info, is_error, print_errors
from helpers            import geninfo_lookup
from install.check_oms  import get_oms_version
from install.install    import check_installation
from connect.connect    import check_connection
from .check_multihoming import check_multihoming
from .check_logs        import check_log_heartbeat

OMSADMIN_CONF_PATH = "/etc/opt/microsoft/omsagent/conf/omsadmin.conf"
OMSADMIN_SH_PATH = "/opt/microsoft/omsagent/bin/omsadmin.sh"
SC_PATH = "/opt/microsoft/omsagent/bin/service_control"



def check_omsagent_running_sc():
    # check if OMS is running through service control
    is_running = subprocess.call([SC_PATH, 'is-running'])
    if (is_running == 1):
        return NO_ERROR
    elif (is_running == 0):
        # don't have any extra info
        return ERR_OMS_WONT_RUN
    else:
        err_msg = "Command '{0} is-running' returned {1}".format(SC_PATH, is_running)
        error_info.append((err_msg,))
        return ERR_OMS_WONT_RUN

def check_omsagent_running_omsadmin(workspace):
    output = subprocess.check_output(['sh', OMSADMIN_SH_PATH, '-l'], universal_newlines=True)
    output_regx = "Primary Workspace: (\S+)    Status: (\w+)\((\b+)\)\n"
    output_matches = re.match(output_regx, output)

    if (output_matches == None):
        err_regx = "-e error	(\b+)\n"
        err_matches = re.match(err_regx, output)
        if (err_matches == None):
            error_info.append((OMSADMIN_SH_PATH, output))
            return ERR_FILE_ACCESS
        # matched to error
        err_info = err_matches.groups()[0]
        # check if permission error
        if (err_info == "This script must be run as root or as the omsagent user."):
            error_info.append((OMSADMIN_SH_PATH,))
            return ERR_SUDO_PERMS
        # some other error
        error_info.append((OMSADMIN_SH_PATH, err_info))
        return ERR_FILE_ACCESS

    # matched to output
    (output_wkspc, status, details) = output_matches.groups()

    # check correct workspace
    if (output_wkspc != workspace):
        error_info.append((output_wkspc, workspace))
        return ERR_GUID

    # check status
    if (status=="Onboarded" and details=="OMS Agent Running"):
        # enabled, running
        return NO_ERROR
    elif (status=="Warning" and details=="OMSAgent Registered, Not Running"):
        # enabled, stopped
        return ERR_OMS_STOPPED
    elif (status=="Saved" and details=="OMSAgent Not Registered, Workspace Configuration Saved"):
        # disabled
        return ERR_OMS_DISABLED
    else:
        # unknown status
        info_text = "OMS Agent has status {0} ({1})".format(status, details)
        error_info.append((info_text,))
        return ERR_OMS_WONT_RUN

def check_omsagent_running_ps(workspace):
    # check if OMS is running through 'ps'
    processes = subprocess.check_output(['ps', '-ef'], universal_newlines=True).split('\n')
    for process in processes:
        # check if process is OMS
        if (not process.startswith('omsagent')):
            continue

        # [ UID, PID, PPID, C, STIME, TTY, TIME, CMD ]
        process = process.split()
        command = ' '.join(process[7:])

        # try to match command with omsagent command
        regx_cmd = "/opt/microsoft/omsagent/ruby/bin/ruby /opt/microsoft/omsagent/bin/omsagent "\
                   "-d /var/opt/microsoft/omsagent/(\S+)/run/omsagent.pid "\
                   "-o /var/opt/microsoft/omsagent/(\S+)/log/omsagent.log "\
                   "-c /etc/opt/microsoft/omsagent/(\S+)/conf/omsagent.conf "\
                   "--no-supervisor"
        matches = re.match(regx_cmd, command)
        if (matches == None):
            continue

        matches_tup = matches.groups()
        guid = matches_tup[0]
        if (matches_tup.count(guid) != len(matches_tup)):
            continue

        # check if OMS is running with a different workspace
        if (workspace != guid):
            error_info.append((guid, workspace))
            return ERR_GUID

        # OMS currently running and delivering to the correct workspace
        return NO_ERROR

    # none of the processes running are OMS
    return ERR_OMS_WONT_RUN

def check_omsagent_running(workspace):
    # check through is-running
    checked_sc = check_omsagent_running_sc()
    if (checked_sc != ERR_OMS_WONT_RUN):
        return checked_sc

    # check if is a process
    checked_ps = check_omsagent_running_ps(workspace)
    if (checked_ps != ERR_OMS_WONT_RUN):
        return checked_ps
    
    # get more info
    return check_omsagent_running_omsadmin(workspace)
        



def start_omsagent(workspace, enabled=False):
    print("Agent curently not running. Attempting to start omsagent...")
    result = 0
    # enable the agent if necessary
    if (not enabled):
        result = subprocess.call([SC_PATH, 'enable'])
    # start the agent if enable was successful
    result = (subprocess.call([SC_PATH, 'start'])) if (result == 0) else (result)

    # check if successful
    if (result == 0):
        return check_omsagent_running(workspace)
    elif (result == 127):
        # script doesn't exist
        error_info.append(('executable shell script', SC_PATH))
        return ERR_FILE_MISSING



def check_heartbeat(interactive, prev_success=NO_ERROR):
    print("CHECKING HEARTBEAT / HEALTH...")

    success = prev_success

    # TODO: run `sh /opt/microsoft/omsagent/bin/omsadmin.sh -l` to check if onboarded and running

    # check if installed correctly
    print("Checking if installed correctly...")
    if (get_oms_version() == None):
        print_errors(ERR_OMS_INSTALL)
        print("Running the installation part of the troubleshooter in order to find the issue...")
        print("================================================================================")
        return check_installation(interactive, err_codes=False, prev_success=ERR_FOUND)

    # get workspace ID
    workspace_id = geninfo_lookup('WORKSPACE_ID')
    if (workspace_id == None):
        error_info.append(('Workspace ID', OMSADMIN_CONF_PATH))
        print_errors(ERR_INFO_MISSING)
        print("Running the connection part of the troubleshooter in order to find the issue...")
        print("================================================================================")
        return check_connection(interactive, err_codes=False, prev_success=ERR_FOUND)
    
    # check if running multi-homing
    print("Checking if omsagent is trying to run multihoming...")
    checked_multihoming = check_multihoming(workspace_id)
    if (is_error(checked_multihoming)):
        return print_errors(checked_multihoming)
    else:
        success = print_errors(checked_multihoming)

    # TODO: check if other agents are sending heartbeats

    # check if omsagent is running
    print("Checking if omsagent is running...")
    checked_omsagent_running = check_omsagent_running(workspace_id)
    if (checked_omsagent_running == ERR_OMS_WONT_RUN):
        # try starting omsagent
        # TODO: find better way of doing this, check to see if agent is stopped / grab results
        checked_omsagent_running = start_omsagent(workspace_id)
    if (is_error(checked_omsagent_running)):
        return print_errors(checked_omsagent_running)
    else:
        success = print_errors(checked_omsagent_running)

    # check if omsagent.log finds any heartbeat errors
    print("Checking for errors in omsagent.log...")
    checked_log_hb = check_log_heartbeat(workspace_id)
    if (is_error(checked_log_hb)):
        # connection issue
        if (checked_log_hb == ERR_HEARTBEAT):
            print_errors(checked_log_hb)
            print("Running the connection part of the troubleshooter in order to find the issue...")
            print("================================================================================")
            return check_connection(err_codes=False, prev_success=ERR_FOUND)
        # other issue
        else:
            return print_errors(checked_log_hb)
    else:
        success = print_errors(checked_log_hb)
    
    return success

