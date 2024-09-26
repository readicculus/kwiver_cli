#      This file is part of the PEP GUI detection pipeline batch running tool
#      Copyright (C) 2021 Yuval Boss yuval@uw.edu
#
#      This program is free software: you can redistribute it and/or modify
#      it under the terms of the GNU General Public License as published by
#      the Free Software Foundation, either version 3 of the License, or
#      (at your option) any later version.
#
#      This program is distributed in the hope that it will be useful,
#      but WITHOUT ANY WARRANTY; without even the implied warranty of
#      MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#      GNU General Public License for more details.
#
#      You should have received a copy of the GNU General Public License
#      along with this program.  If not, see <https://www.gnu.org/licenses/>.
import logging
import os
import pathlib as pl
import shutil
import tarfile
import unittest
import configparser
import requests

logging.basicConfig(format='%(asctime)s [%(levelname)s][%(name)s] - %(message)s', level=logging.DEBUG)
global_logger = logging.getLogger(f'')

TEST_DIR = os.path.dirname(__file__)
TESTDATA_DIR = os.path.join(TEST_DIR, 'pep_tk-testdata')
CONF_FILEPATH = os.path.join(os.path.dirname(TEST_DIR),'src', 'pep_tk/conf')
global_logger.debug('TEST_DIR %s' % TEST_DIR)
global_logger.debug('DATA_FILEPATH %s' % TESTDATA_DIR)
global_logger.debug('CONF_FILEPATH %s' % CONF_FILEPATH)

test_config = os.path.join(TEST_DIR, 'config.ini')
config = configparser.ConfigParser()
config.read(test_config)


def add_src_to_pythonpath():
    import os
    import sys
    src_dir = os.path.abspath(os.path.normpath(os.path.join(TEST_DIR, "../src")))
    global_logger.debug('Added PYTHONPATH: %s' % src_dir)
    sys.path.insert(0, src_dir)


def download_dummy_data():
    if os.path.isdir(TESTDATA_DIR):
        global_logger.debug('%s already exists.  Skipping download.' % TESTDATA_DIR)
        return

    def download_file_from_google_drive(id, destination):
        def get_confirm_token(response):
            for key, value in response.cookies.items():
                if key.startswith('download_warning'):
                    return value

            return None

        def save_response_content(response, destination):
            CHUNK_SIZE = 32768

            with open(destination, "wb") as f:
                for chunk in response.iter_content(CHUNK_SIZE):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)

        URL = "https://drive.usercontent.google.com/download?"

        session = requests.Session()

        response = session.get(URL, params={'id': id, 'confirm': 'yy'}, stream=True)
        token = get_confirm_token(response)

        if token:
            params = {'id': id, 'confirm': token}
            response = session.get(URL, params=params, stream=True)

        save_response_content(response, destination)
        session.close()

    archive_fn = 'pep_tk-testdata.tar.gz'
    archive_fp = os.path.join(TEST_DIR, archive_fn)

    global_logger.debug(f'Downloading {archive_fn} from Google Drive.....')
    gdrive_testdata_id = config['TestConfig'].get('gdrive_testdata_id')
    download_file_from_google_drive(gdrive_testdata_id, archive_fp)
    global_logger.debug(f'Extracting archive to {TEST_DIR}.')
    print(os.listdir())
    with tarfile.open(archive_fp) as tar:
        def is_within_directory(directory, target):
            
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
        
            prefix = os.path.commonprefix([abs_directory, abs_target])
            
            return prefix == abs_directory
        
        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        
            for member in tar.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
        
            tar.extractall(path, members, numeric_owner=numeric_owner) 
            
        
        safe_extract(tar, path=TEST_DIR)
    global_logger.debug(os.listdir(os.path.join(TEST_DIR, 'pep_tk-testdata')))

    global_logger.debug('DEBUG listdir TEST_DIR')
    global_logger.debug(os.listdir(TEST_DIR))
    global_logger.debug('DEBUG listdir DATA_FILEPATH')
    global_logger.debug(os.listdir(TESTDATA_DIR))


class TestCaseBase(unittest.TestCase):
    log = None

    def assertIsFile(self, path):
        if not pl.Path(path).resolve().is_file():
            raise AssertionError("File does not exist: %s" % str(path))

    def assertIsDir(self, path):
        if not pl.Path(path).resolve().is_dir():
            raise AssertionError("Directory does not exist: %s" % str(path))

    def _setup(self):
        self.log = logging.getLogger(self.id())
        self.print('Test Started', logging.DEBUG)

    # print to test log
    def print(self, message, loglevel=logging.INFO):
        if not self.log:
            self._setup()

        self.log.log(level=loglevel, msg=message)

    def setUp(self) -> None:
        self._setup()

    def tearDown(self) -> None:
        try:
            if self._outcome.success:
                self.print('Test Succeeded', logging.DEBUG)
            else:
                self.print('Test Failed', logging.ERROR)
        except:
            pass


class TestCaseRequiringTestData(TestCaseBase):
    temp_dir = os.path.join(os.getcwd(), 'tmp')

    @classmethod
    def setUpClass(cls):
        download_dummy_data()
        if os.path.isdir(cls.temp_dir):
            shutil.rmtree(cls.temp_dir)

        os.makedirs(cls.temp_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.temp_dir)


class TestCaseRequiringSEALTK(TestCaseRequiringTestData):

    def __init__(self, *args, **kwargs):
        super(TestCaseRequiringTestData, self).__init__(*args, **kwargs)
        self.sealtk_dir = ""
        self.is_valid_sealtk_dir = False

        sealtk_directory = config['TestConfig'].get('sealtk_dir')
        self.sealtk_dir = sealtk_directory
        from pep_tk.psg.settings import get_viame_bash_or_bat_file_path

        if sealtk_directory is not None and os.path.isdir(sealtk_directory) and \
                os.path.isfile(get_viame_bash_or_bat_file_path(sealtk_directory)):
            self.is_valid_sealtk_dir = True

    def setUp(self) -> None:
        if not self.is_valid_sealtk_dir:
            self.print('Test Skipped', logging.INFO)
            self.skipTest(f'TestConfig SEAL-TK directory is not defined or is not a valid seal-tk directory: '
                          f'"{self.sealtk_dir}".\n'
                          f'In order to run tests that actuall run a pipeline SEAL-TK needs to be downloaded. '
                          f'You can find SEAL-TK binaries at https://github.com/VIAME/VIAME/.\n'
                          'To configure the location for tests, change the location of your SEAL-TK directory in '
                          'pep_gui/tests/config.ini')
        else:
            super(TestCaseRequiringTestData, self).setUp()
