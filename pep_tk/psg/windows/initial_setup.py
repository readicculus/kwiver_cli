# https://github.com/PySimpleGUI/PySimpleGUI/issues/3058
import os
from typing import Optional

import PySimpleGUI as sg

from pep_tk.psg.settings import get_settings, SettingsNames


def initial_setup(skip_if_complete = True, modal=False) -> Optional[sg.Window]:
    gui_settings = get_settings()
    def check_complete():
        # TODO: better check for completion
        # TODO: validate datasets correct and setup viame correct
        return gui_settings.get(SettingsNames.setup_viame_filepath, None) is not None and gui_settings.get(
                SettingsNames.dataset_manifest_filepath, None) is not None

    manifest_folder = gui_settings.get(SettingsNames.dataset_manifest_filepath, None)
    if manifest_folder: manifest_folder = os.path.dirname(manifest_folder)
    layout = [[sg.Text('Enter the viame directory:')],
              [sg.Input(gui_settings.get(SettingsNames.setup_viame_filepath, ''), key='-setup_viame_filepath-IN-'),
               sg.FolderBrowse(initial_folder=gui_settings.get(SettingsNames.setup_viame_filepath))],
              [sg.Text('Enter the dataset manfiest filepath:')],
              [sg.Input(gui_settings.get(SettingsNames.dataset_manifest_filepath, ''), key='-dataset_manifest_filepath-IN-'),
               sg.FileBrowse(initial_folder=manifest_folder)],
              [sg.B('Complete Setup'), sg.B('Exit', key='Exit')]]

    if check_complete() and skip_if_complete:
        return None
    location = gui_settings[SettingsNames.window_location] or (0,0)
    window = sg.Window('PEP-TK: Properties',
                       layout,
                       keep_on_top=True,
                       finalize=True,
                       location=location,
                       modal=modal)

    while True:
        if check_complete() and skip_if_complete:
            break

        event, values = window.read()
        if event in (sg.WINDOW_CLOSED, 'Exit'):
            break
        elif event == 'Complete Setup':
            selected_viame_filepath = values['-setup_viame_filepath-IN-']
            if os.path.isfile(os.path.join(selected_viame_filepath, 'setup_viame.sh')) or \
                os.path.isfile(os.path.join(selected_viame_filepath, 'setup_viame.bat')):
                gui_settings[SettingsNames.setup_viame_filepath] = selected_viame_filepath

            selected_dataset_manifest_filepath = values['-dataset_manifest_filepath-IN-']
            if os.path.isfile(selected_dataset_manifest_filepath):
                gui_settings[SettingsNames.dataset_manifest_filepath] = selected_dataset_manifest_filepath

            if check_complete(): break

    return window

