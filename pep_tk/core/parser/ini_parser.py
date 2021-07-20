import os
from configparser import ConfigParser
from typing import List, Optional

import regex as re

from pep_tk.core.parser import ImageListMissingImage, DatasetFileNotFound, ManifestParser, path_to_absolute
from pep_tk.core.parser import VIAMEDataset


class INIDatasetsParser(ConfigParser, ManifestParser):
    def read(self, filenames, encoding=None):
        if isinstance(filenames, (str, os.PathLike)):
            filenames = [filenames]
        read_ok = []
        for filename in filenames:
            try:
                with open(filename, encoding=encoding) as fp:
                    self._read(fp, filename)
            except OSError:
                continue
            if isinstance(filename, os.PathLike):
                filename = os.fspath(filename)
            read_ok.append(filename)
            self.validate_dataset_files(filename)

        return read_ok

    def as_dict(self):
        d = dict(self._sections)
        for k in d:
            d[k] = dict(self._defaults, **d[k])
            d[k].pop('__name__', None)
        return d


    def validate_dataset_files(self, manifeset_fp):
        manifest_wd = os.path.dirname(manifeset_fp)
        manifeset_fn = os.path.basename(manifeset_fp)

        datasets = self.as_dict()
        for ds_name, attrs in datasets.items():
            # dataset must have an image list
            if self.att_thermal_image_list not in attrs and self.att_color_image_list not in attrs:
                raise Exception(f'[{manifeset_fn}][{ds_name}] ERROR: No color or a thermal image list defined.')

            for a, v in attrs.items():
                datafile_abspath = path_to_absolute(manifest_wd, v)
                datafile_wd = os.path.dirname(datafile_abspath)

                # check that dataset file was found
                if not os.path.isfile(datafile_abspath):
                    raise DatasetFileNotFound(f'[{manifeset_fn}][{ds_name}] ERROR: File "{a}={v}" does not exist.')

                # check that all images exist in the defined image list
                if a in [self.att_color_image_list, self.att_thermal_image_list]:
                    with open(datafile_abspath, 'r') as f:
                        image_paths = list(line for line in (l.strip() for l in f.readlines()) if line)
                    for img_fp in image_paths:
                        img_fp = path_to_absolute(datafile_wd, img_fp)
                        if not os.path.isfile(img_fp):
                            raise ImageListMissingImage(f'[{manifeset_fn}][{ds_name}] ERROR: "{img_fp}" was not found in {a}.')

                # set path to the absolute path
                self.set(ds_name,a, datafile_abspath)

    # given a string, list the dataset keys containing that string
    def list_dataset_keys_txt(self, txt: str) -> List[str]:
        try:
            regkey = '^.*' + txt + '.*$'
            r = re.compile(regkey)
            return list(filter(r.match, list(self)))
        except:
            return []

    def list_dataset_keys(self) -> List[str]:
        return list(self)

    def get_dataset(self, name: str) -> Optional[VIAMEDataset]:
        ds = self.as_dict().get(name)
        if not ds:
            return None
        return VIAMEDataset(name=name,
                            color_image_list=ds.get(self.att_color_image_list),
                            thermal_image_list=ds.get(self.att_thermal_image_list),
                            transformation_file=ds.get(self.att_transform))
