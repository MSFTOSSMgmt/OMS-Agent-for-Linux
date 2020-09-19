import os
import subprocess

from error_codes import *
from errors      import error_info, get_input

CLCONF_PATH = "/etc/opt/microsoft/omsagent/conf/omsagent.d/customlog.conf"
OMSCONFLOG_PATH = "/var/opt/microsoft/omsconfig/omsconfig.log"
OMSCONFLOGDET_PATH = "/var/opt/microsoft/omsconfig/omsconfigdetailed.log"



def no_clconf(interactive):
    # check if enough time has passed for agent to pull config from OMS backend
    print("--------------------------------------------------------------------------------")
    print(" The troubleshooter cannot find the customlog.conf file. If the custom log \n"\
          " configuration was just applied in portal, it takes up to 15 minutes for the \n"\
          " agent to pick the new configuration.\n"\
          " You can manually pull the config from the OMS backend by running this command:\n"\
          "\n  $ sudo su omsagent -c 'python /opt/microsoft/omsconfig/Scripts/PerformRequiredConfigurationChecks.py'\n")

    # errors out here if not using custom logs (for silent mode)
    if (not interactive):
        print(" (NOTE: if you aren't using custom logs, please ignore this message.)")
        error_info.append((OMSCONFLOG_PATH, OMSCONFLOGDET_PATH))
        return ERR_BACKEND_CONFIG

    # ask if already tried pulling config from OMS backend
    if (interactive):
        manual_pull = get_input("Have you already tried pulling the config manually? (y/n)",\
                             (lambda x : x.lower() in ['y','yes','n','no']),\
                             "Please type either 'y'/'yes' or 'n'/'no' to proceed.")

        # tried pulling, see if that fixed it
        if (manual_pull.lower() in ['y','yes']):
            # config now exists
            if (os.path.isfile(CLCONF_PATH)):
                print("The config file has been pulled successfully.")
                print("Continuing on with troubleshooter...")
                print("--------------------------------------------------------------------------------")
                return NO_ERROR
            # config still doesn't exist
            else:
                # TODO: check the log files for an error in DSC
                error_info.append((OMSCONFLOG_PATH, OMSCONFLOGDET_PATH))
                return ERR_BACKEND_CONFIG

        # haven't tried pulling yet
        else:
            print(" Please try running the above command to pull the config file.")
            return ERR_FOUND



def check_customlog(log_dict):
    log_path = log_dict[path]
    # check if path exists
    if (not os.path.isfile(log_path)):
        # try splitting on like './' or something to check both file paths
        # if that doesn't work:
        error_info.append(('file', log_path))
        return ERR_FILE_MISSING

    # check if pos file exists
    log_pos_file = log_dict[pos_file]
    if (not os.path.isfile(log_pos_file)):
        error_info.append(('file', log_pos_file))
        return ERR_FILE_MISSING

    # check pos file contents
    with open(log_pos_file, 'r') as lpf:
        parsed_lines = lpf.readlines().split()
        # mismatch in pos file filepath and custom log filepath
        if (parsed_lines[0] != log_path):
            error_info.append((log_pos_file, log_path, CLCONF_PATH))
            return ERR_CL_FILEPATH
        #TODO: check size of custom log
        pos_size = parsed_lines[1]

        # check unique number with custom log
        un_pos = parsed_lines[2]
        log_ls_info = subprocess.check_output(['ls','-li',log_path])
        un_log = (log_ls_info.split())[0]
        un_log_hex = hex(int(un_log)).lstrip('0x').rstrip('L')
        if (un_pos != un_log_hex):
            error_info.append((log_path, un_log_hex, log_pos_file, un_pos, \
                                    CLCONF_PATH))
            return ERR_CL_UNIQUENUM

    return NO_ERROR
        

    

def check_customlog_conf(interactive):
    # verify customlog.conf exists / not empty
    if (not os.path.isfile(CLCONF_PATH)):
        backend_grab = no_clconf(interactive)
        if (backend_grab != NO_ERROR):
            return backend_grab
    if (os.stat(CLCONF_PATH).st_size == 0):
        error_info.append((CLCONF_PATH,))
        return ERR_FILE_EMPTY

    with open(CLCONF_PATH, 'r') as cl_file:
        cl_lines = cl_file.readlines()
        curr_log = dict()
        in_log = False
        for cl_line in cl_lines:
            # start of new custom log
            if ((not in_log) and (cl_line=="<source>")):
                in_log = True
                continue
            # end of custom log
            elif (in_log and (cl_line=="</source>")):
                in_log = False
                checked_customlog = check_customlog(curr_log.deepcopy())
                if (checked_customlog != NO_ERROR):
                    return checked_customlog
                curr_log = dict()
                continue
            # inside custom log
            elif (in_log):
                parsed_line = cl_line.lstrip('  ').split(' ')
                curr_log[parsed_line[0]] = parsed_line[1]
                continue

    return NO_ERROR
