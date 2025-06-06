import os
import subprocess
import configparser
import shutil
import difflib

def get_app_data_from_desktop_file(filepath):
    config = configparser.ConfigParser(interpolation=None)
    try:
        config.read(filepath)
    except configparser.Error:
        return None

    if 'Desktop Entry' in config:
        desktop_entry = config['Desktop Entry']
        app_name = desktop_entry.get('Name')
        exec_command = desktop_entry.get('Exec')
        terminal = desktop_entry.get('Terminal', 'false').lower() == 'true'
        no_display = desktop_entry.get('NoDisplay', 'false').lower() == 'true'
        hidden = desktop_entry.get('Hidden', 'false').lower() == 'true'
        type_ = desktop_entry.get('Type')

        if app_name and exec_command and type_ == 'Application' and not no_display and not hidden:
            clean_exec_command = exec_command.split('%')[0].strip().split()[0].strip()

            if not clean_exec_command:
                return None

            resolved_path = clean_exec_command if os.path.isabs(clean_exec_command) else shutil.which(clean_exec_command)

            if resolved_path and os.path.exists(resolved_path):
                return {
                    'name': app_name,
                    'exec_path': resolved_path,
                    'terminal': terminal
                }
    return None

def get_installed_applications():
    applications = {}
    search_paths = [
        '/usr/share/applications/',
        '/usr/local/share/applications/',
        os.path.expanduser('~/.local/share/applications/'),
        '/var/lib/snapd/desktop/applications/',
    ]

    snap_base_dir = '/snap/'
    if os.path.isdir(snap_base_dir):
        for entry in os.listdir(snap_base_dir):
            snap_app_path = os.path.join(snap_base_dir, entry, "current", "usr", "share", "applications")
            if os.path.isdir(snap_app_path):
                search_paths.append(snap_app_path)

    for base_dir in search_paths:
        if not os.path.isdir(base_dir):
            continue

        try:
            for filename in os.listdir(base_dir):
                if filename.endswith(".desktop"):
                    filepath = os.path.join(base_dir, filename)
                    app_data = get_app_data_from_desktop_file(filepath)
                    if app_data:
                        applications[app_data['name'].lower()] = app_data
        except Exception:
            continue

    return applications


def launch_application_by_name(app_name):
    apps = get_installed_applications()
    app_names = list(apps.keys())

    # First try exact match
    app_info = apps.get(app_name.lower())

    # If no exact match, try close fuzzy match
    if not app_info:
        close_matches = difflib.get_close_matches(app_name.lower(), app_names, n=1, cutoff=0.75)
        if close_matches:
            matched_name = close_matches[0]
            app_info = apps[matched_name]
            print(f"Matched input '{app_name}' to '{app_info['name']}'")

    if not app_info:
        print(f"App '{app_name}' not found.")
        return False

    try:
        if app_info['terminal']:
            subprocess.Popen(['x-terminal-emulator', '-e', app_info['exec_path']])
        else:
            subprocess.Popen([app_info['exec_path']])
        print(f"Launched '{app_info['name']}'")
        return True
    except Exception as e:
        print(f"Failed to launch '{app_info['name']}': {e}")
        return False
# Example usage
if __name__ == "__main__":
    while 1:
        launch_application_by_name(input('Name : '))  # Change app name here


print(get_installed_applications())
