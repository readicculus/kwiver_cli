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
from typing import Dict, Tuple, List, Optional

from pep_tk.core.parser import VIAMEDataset
from pep_tk.core.configuration.types import parse_type
from pep_tk.core.configuration.exceptions import *
from pep_tk.core.configuration import ENV_VARIABLE, VALUE


class ConfigOption:
    def __init__(self, name: str, option_dict: Dict):
        self.name = name
        self.default = option_dict['default']
        self.type = option_dict['type']
        self.env_variable = option_dict['env_variable']
        self.description = option_dict.get('description')
        self.validator = parse_type(self.type)
        self.__value: Optional[VALUE] = option_dict.get('_value')
        self._locked = option_dict.get('_locked', False)

        # ensure default is valid
        valid, _ = self.validator.validate(self.default)
        if not valid:
            raise InvalidConfigOptionDefaultException('', self.name, self.default)

    def value(self) -> VALUE:
        if self.__value:
            return self.__value
        return self.default

    def set_value(self, value):
        """
        Sets the value of the ConfigOption
        :param value: new value for the config option
        :return: boolean
        """
        # value = str(value)
        if self._locked:
            return False

        valid, res = self.validator.validate(value)
        if valid:
            self.__value = res
            return True
        return False

    def reset(self):
        """ Resets the ConfigOption to the default value """
        if not self._locked:
            self.__value = self.default

    def get_env(self) -> Tuple[ENV_VARIABLE, VALUE]:
        """ returns a tuple with the first item being the environment variable name and the second begin the value """
        return self.env_variable, self.value()

    def to_dict(self) -> Dict:
        return {'name': self.name,
                '_value': self.value(),
                '_locked': self._locked,
                'default': self.default,
                'type': self.type,
                'env_variable': self.env_variable,
                'description': self.description}



class ConfigOptionGroup:
    def __init__(self, group_name: str, config_dict: Dict, required_group: bool = True):
        self.required_group = required_group
        self.group_name = group_name
        self.options: List[ConfigOption] = []

        group_dict = config_dict.get(group_name)
        if group_dict is None and self.required_group:
            raise MissingConfigGroupException(self.group_name)
        elif group_dict is not None:
            # make a list of ConfigOptions that are in this group
            for name, attributes in group_dict.items():
                opt_type = attributes.get('type')
                if not self.validate_option_type(attributes.get('type')):
                    raise InvalidConfigOptionTypeException(self.group_name, name, opt_type)

                o = ConfigOption(name, attributes)
                self.options.append(o)

    def validate_option_type(self, opt) -> bool:
        msg = self.__class__.__name__ + ' must implement validate_option_type.'
        raise NotImplementedError(msg)
        return False

    def get_config_option(self, name) -> Optional[ConfigOption]:
        """
        :param name: option name to get
        :return: returns the ConfigOption with that name or None if an option with that name doesn't exist
        """
        for opt in self.options:
            if opt.name == name:
                return opt
        return None

    def set_config_option(self, name, value: VALUE) -> bool:
        opt = self.get_config_option(name)
        if opt is not None:
            return opt.set_value(value)
        return False

    def reset_config_option(self, name):
        opt = self.get_config_option(name)
        if opt is not None:
            opt.reset()

    def reset_all(self):
        for opt in self.options:
            opt.reset()

    def get_env_ports(self) -> Dict[ENV_VARIABLE, VALUE]:
        env_list = [opt.get_env() for opt in self.options]
        return {k: v for (k, v) in env_list}

    # serialization (load/save) capabilities
    def to_dict(self):
        return {opt.name: opt.to_dict() for opt in self.options}

    # object methods
    def __len__(self):
        return len(self.options)

    def __getitem__(self, name) -> ConfigOption:
        return self.get_config_option(name)


class PipelineOutputOptionGroup(ConfigOptionGroup):
    __image_list_type = 'output_image_list'
    __detections_csv_type = 'output_detections_csv'

    def __init__(self, config_dict: Dict):
        super().__init__('output_config', config_dict, required_group=False)

    def validate_option_type(self, opt) -> bool:
        return opt in [self.__image_list_type, self.__detections_csv_type]

    def get_image_list_options(self) -> List[ConfigOption]:
        opts = []
        for opt in self.options:
            if opt.type == self.__image_list_type:
                opts.append(opt)
        return opts

    def get_det_csv_options(self) -> List[ConfigOption]:
        opts = []
        for opt in self.options:
            if opt.type == self.__detections_csv_type:
                opts.append(opt)
        return opts

    def get_image_list_env_ports(self):
        env_list = [opt.get_env() for opt in self.get_image_list_options()]
        return {k: v for (k, v) in env_list}

    def get_det_csv_env_ports(self):
        env_list = [opt.get_env() for opt in self.get_det_csv_options()]
        return {k: v for (k, v) in env_list}

class PipelineParametersOptionGroup(ConfigOptionGroup):
    def __init__(self, config_dict: Dict):
        super().__init__('parameters_config', config_dict, required_group=False)

    def validate_option_type(self, opt) -> bool: return True


class DatasetPipelineEnvAdaptersGroup:
    def __init__(self, config_dict: Dict):
        self.__config = config_dict.get('dataset_pipeline_adapters')

    def get_env_ports(self, dataset: VIAMEDataset, missing_ok=False) -> Dict[ENV_VARIABLE, VALUE]:
        res = {}
        missing_ports = []
        for name, attributes in self.__config.items():
            attr = attributes['dataset_attribute']
            if dataset.get(attr) is None:
                missing_ports.append(attr)

            if attr in dataset:
                res[attributes['env_variable']] = dataset[attr]

        if not missing_ok and len(missing_ports) > 0:
            raise MissingPortsException(missing_ports, dataset.name)

        return res

    def get_existing_ports(self, dataset: VIAMEDataset) -> List[ENV_VARIABLE]:
        existing_ports = []
        for name, attributes in self.__config.items():
            attr = attributes['dataset_attribute']
            if dataset.get(attr) is not None:
                existing_ports.append(attr)

        return existing_ports

    def to_dict(self):
        return self.__config


class PipelineConfig:
    def __init__(self, pipeline_name, config_dict: Dict):
        """
        A PipelineConfig is made up of two config groups, the first is parameters such as thresholds, and
        the second is the pipeline output such as output detections file and image lists.  It also has
        dataset ports, which given a dataset will connect any dataset specific parameters required by the pipeline.
        :param pipeline_name: name of the pipeline
        :param config_dict: dictionary of the given pipeline from the parsed pipeline manifest yaml file
        """
        from pep_tk import PLUGIN_PATH
        self.name = pipeline_name
        self.path = os.path.join(PLUGIN_PATH, os.path.normpath(config_dict['path']))
        self.directory = os.path.dirname(self.path)
        if not os.path.exists(self.path):
            raise Exception('pipeline %s does not exist' % self.path)
        self.parameters_group = PipelineParametersOptionGroup(config_dict)
        self.output_group = PipelineOutputOptionGroup(config_dict)
        self.dataset_ports = DatasetPipelineEnvAdaptersGroup(config_dict)

    def get_output_env_ports(self, output_directory = ''):
        output_ports = self.output_group.get_env_ports()
        # append output directory to all output files
        output_ports_in_out_dir = {k: os.path.join(output_directory, v) for k,v in output_ports.items()}
        return output_ports_in_out_dir

    def get_parameter_env_ports(self):
        return self.parameters_group.get_env_ports()

    def get_pipeline_dataset_environment(self, dataset: VIAMEDataset, missing_ok=False) -> Dict[ENV_VARIABLE, VALUE]:
        return self.dataset_ports.get_env_ports(dataset, missing_ok)

    def to_dict(self) -> Dict:
        d = {
                'name': self.name,
                'parameters_config': self.parameters_group.to_dict(),
                'output_config': self.output_group.to_dict(),
                'dataset_pipeline_adapters': self.dataset_ports.to_dict(),
                'path': self.path
            }
        return d
