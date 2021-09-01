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

import os
import shutil
import tarfile
import unittest

import requests
import pathlib as pl

TEST_DIR = os.path.dirname(__file__)
TESTDATA_DIR = os.path.join(TEST_DIR, 'pep_tk-testdata')
CONF_FILEPATH = os.path.join(os.path.dirname(TEST_DIR), 'conf')
print('TEST_DIR %s' % TEST_DIR)
print('DATA_FILEPATH %s' % TESTDATA_DIR)
print('CONF_FILEPATH %s' % CONF_FILEPATH)


def add_src_to_pythonpath():
    import os
    import sys
    src_dir = os.path.abspath(os.path.normpath(os.path.join(TEST_DIR, "../src")))
    print('Added PYTHONPATH: %s' % src_dir)
    sys.path.insert(0, src_dir)


def download_dummy_data():
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

        URL = "https://drive.google.com/uc?export=download"

        session = requests.Session()

        response = session.get(URL, params={'id': id}, stream=True)
        token = get_confirm_token(response)

        if token:
            params = {'id': id, 'confirm': token}
            response = session.get(URL, params=params, stream=True)

        save_response_content(response, destination)
        session.close()

    if os.path.isdir(TESTDATA_DIR):
        print('%s already exists.  Skipping download.' % TESTDATA_DIR)
        return
    archive_fn = 'pep_tk-testdata.tar.gz'
    print(f'Downloading {archive_fn} from Google Drive.....')
    download_file_from_google_drive('1C1yNhG0Aoh15IAG7QU2bUrT6X299j1VL', archive_fn)
    print(f'Extracting archive.')
    with tarfile.open(archive_fn) as tar:
        tar.extractall(path=TEST_DIR)

    print(f'Cleaning up, removing {archive_fn}.')
    os.remove(archive_fn)

    print('DEBUG listdir TEST_DIR')
    print(os.listdir(TEST_DIR))
    print('DEBUG listdir DATA_FILEPATH')
    print(os.listdir(TESTDATA_DIR))


class TestCaseBase(unittest.TestCase):
    def assertIsFile(self, path):
        if not pl.Path(path).resolve().is_file():
            raise AssertionError("File does not exist: %s" % str(path))

    def assertIsDir(self, path):
        if not pl.Path(path).resolve().is_dir():
            raise AssertionError("Directory does not exist: %s" % str(path))


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
