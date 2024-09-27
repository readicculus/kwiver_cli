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
from enum import Enum
from typing import List, Tuple, Optional

from pep_tk.core.utilities import jsonfile
from pep_tk.core.parser import VIAMEDataset
from pep_tk.core.configuration import PipelineConfig
from pep_tk.core.configuration.configurations import PipelineOutputOptionGroup
from pep_tk.core.kwiver.pipeline_compiler import compile_pipeline


class JobInitException(Exception):
    pass


# get job directories / files using the job root dir
meta_dir = lambda root_dir: os.path.join(root_dir, 'meta')
pipelines_dir = lambda root_dir: os.path.join(root_dir, 'pipelines')
logs_dir = lambda root_dir: os.path.join(root_dir, 'logs')
completed_outputs_dir = lambda root_dir: os.path.join(root_dir, 'outputs_success')
error_outputs_dir = lambda root_dir: os.path.join(root_dir, 'outputs_error')
pending_outputs_dir = lambda root_dir: os.path.join(root_dir, 'outputs_pending')

job_state_json_fp = lambda root_dir: os.path.join(meta_dir(root_dir), 'job_state.json')
pipeline_meta_json_fp = lambda root_dir: os.path.join(meta_dir(root_dir), 'pipelines_meta.json')
pipeline_manifest_local = lambda root_dir: os.path.join(meta_dir(root_dir), 'pipelines_manifest.yaml')
datasets_meta_json_fp = lambda root_dir: os.path.join(meta_dir(root_dir), 'datasets_meta.json')


class JobMeta:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.logs_dir = logs_dir(root_dir)
        self.dataset_meta_dir = meta_dir(root_dir)

        self.completed_outputs_dir = completed_outputs_dir(root_dir)
        self.error_outputs_dir = error_outputs_dir(root_dir)
        self.pending_outputs_dir = pending_outputs_dir(root_dir)

        self.pipe_meta_fp = pipeline_meta_json_fp(root_dir)
        self.dataset_meta_fp = datasets_meta_json_fp(root_dir)
        self.compiled_pipelines_dir = pipelines_dir(root_dir)  # where the compiled pipelines go
        self._was_existing = os.path.isfile(self.dataset_meta_fp) and os.path.isfile(self.pipe_meta_fp)

        dump_kwargs = dict(ensure_ascii=False, indent="\t", sort_keys=True)
        self._pipe_store = jsonfile.jsonfile(self.pipe_meta_fp, default_data={}, autosave=True, dump_kwargs=dump_kwargs)
        self._ds_store = jsonfile.jsonfile(self.dataset_meta_fp, default_data={}, autosave=True,
                                           dump_kwargs=dump_kwargs)

    def _copy_pipeline_inputs(self, pipeline: PipelineConfig, dataset: VIAMEDataset) -> VIAMEDataset:
        '''
            Copies the pipeline inputs to the meta directory
            :return the new dataset pointing to the copied files
        '''
        new_dir = os.path.join(self.dataset_meta_dir, dataset.name)
        os.makedirs(new_dir, exist_ok=True)

        ports_to_copy = pipeline.dataset_ports.get_existing_ports(dataset)
        new_outputs = {}
        for p in ports_to_copy:
            fp = getattr(dataset, p)
            original_list_dir = os.path.dirname(fp)
            fp_new = os.path.join(new_dir, os.path.basename(fp))
            new_outputs[p] = fp_new

            if new_outputs[p] == fp:
                continue # already copied and probably this was called when a run is being resumed

            if p in ['thermal_image_list', 'color_image_list']:
                # if its an image list copy it over and ensure paths are absolute
                with open(fp, 'r') as f:
                    with open(fp_new, 'w') as f_new:
                        for line in f:
                            line = line.strip()
                            newline = line
                            if len(line) > 0 and not os.path.isabs(line):
                                newline = os.path.normpath(os.path.join(original_list_dir, newline))
                            f_new.write(newline + '\n')
            else:
                # otherwise just copy the file, right now this is only for the h5 file
                shutil.copy(fp, new_dir)

        self.dataset_meta_dir
        new_dataset = VIAMEDataset(name=dataset.name, **new_outputs)
        return new_dataset

    def create_meta(self, pipeline: PipelineConfig, datasets: List[VIAMEDataset]):
        self._pipe_store.data = pipeline.to_dict()
        for idx, _dataset in enumerate(datasets):
            dataset = self._copy_pipeline_inputs(pipeline, _dataset)
            self._copy_pipeline_inputs(pipeline, dataset)

            compiled_fp = os.path.join(self.compiled_pipelines_dir,
                                       f'{dataset.filename_friendly_name}-{pipeline.name}.pipe')

            # compile output ports first so we can cache output information
            output_config = pipeline.output_group.to_dict()
            for config_name, v in output_config.items():
                output_pattern = v['default'].replace('[DATASET]', dataset.filename_friendly_name)
                output_config[config_name]['_value'] = output_pattern
                output_config[config_name]['_locked'] = True

            # Copy pipeline inputs to meta directory
            # dataset_env = {}
            # for env_name, fp in pipeline.get_pipeline_dataset_environment(dataset).items():
            #     if fp[-4:] != ".txt":
            #         dataset_env[env_name] = fp
            #         continue
            #     fn = os.path.basename(fp)
            #     path = os.path.dirname(pipeline.get_pipeline_dataset_environment(dataset)['PIPE_ARG_THERMAL_INPUT'])
            #     self.dataset_meta_dir,


            # compile everything EXCEPT the new outputs
            env = {**pipeline.get_parameter_env_ports(),
                   **pipeline.get_pipeline_dataset_environment(dataset)}
            compiled_pipe = compile_pipeline(pipeline, env)
            with open(compiled_fp, 'w') as f:
                f.write(compiled_pipe)

            compiled_relpath = os.path.relpath(compiled_fp, self.root_dir)
            self._ds_store.data[dataset.name] = {'compiled_fp': compiled_relpath, 'dataset': dataset.asdict(),
                                                 'output_config': output_config}

    def keys(self):
        return list(self._ds_store.data.keys())

    def get(self, dataset_key) -> Optional[Tuple[str, VIAMEDataset, PipelineOutputOptionGroup]]:
        ds_meta = self._ds_store.data.get(dataset_key)
        if ds_meta is None:
            return None
        # pipeline_fp = os.path.join(self.root_dir, ds_meta['compiled_fp'])
        pipeline_fp = ds_meta['compiled_fp']
        ds_obj = VIAMEDataset(**ds_meta['dataset'].asdict())
        outputs = PipelineOutputOptionGroup(ds_meta)

        return pipeline_fp, ds_obj, outputs


TaskKey = str


class TaskStatus(Enum):
    INITIALIZED = -1
    ERROR = 0
    SUCCESS = 1
    RUNNING = 2
    CANCELLED = 3


class JobState:
    def __init__(self, root_dir, pipeline_keys=None, load_existing=False):
        self.state_fp = job_state_json_fp(root_dir)

        dump_kwargs = dict(ensure_ascii=False, indent="\t", sort_keys=True)
        self._store = jsonfile.jsonfile(self.state_fp, default_data={}, autosave=True, dump_kwargs=dump_kwargs)

        if load_existing:
            if not os.path.isfile(self.state_fp):
                msg = f'Unable to load job. {self.state_fp} does not exist.'
                raise JobInitException(msg)

            self._store = jsonfile.jsonfile(self.state_fp, default_data={}, autosave=True, dump_kwargs=dump_kwargs)
            if not self._store.data.get('initialized', False):
                msg = f'Possibly corrupt job file, please share the following file with Yuval. {self.state_fp}'
                raise JobInitException(msg)
        else:
            # build the job state cache in the provided directory
            if self._store.data.get('initialized', False):
                raise JobInitException('Job Already Exists, this is a check to make sure jobs cant be overriden.')

            if not pipeline_keys or len(pipeline_keys) < 1:
                raise JobInitException('No pipelines provided.')

            # initialize the new job
            self._store.data['tasks'] = sorted(pipeline_keys)
            self._store.data['task_status'] = {task_key: TaskStatus.INITIALIZED.value for task_key in pipeline_keys}
            self._store.data['total_tasks'] = len(pipeline_keys)
            self._store.data['task_outputs'] = {task_key: [] for task_key in pipeline_keys}
            self._store.data['initialized'] = True

        # reset any previous errored tasks to initialized
        for task_key in self._store.data['task_status']:
            if self.get_status(task_key) != TaskStatus.SUCCESS:
                self._store.data['task_status'][task_key] = TaskStatus.INITIALIZED.value

    def get_status(self, task_key: TaskKey):
        return TaskStatus(self._store.data['task_status'][task_key])

    @classmethod
    def load(cls, meta_directory):
        return cls(meta_directory, load_existing=True)

    def current_task(self) -> Optional[TaskKey]:
        for task_key in self.tasks():
            if self.is_task_complete(task_key):
                continue
            return task_key

        return None

    def is_task_complete(self, task_key: TaskKey) -> bool:
        task_status = self.get_status(task_key)
        is_complete = task_status in [TaskStatus.SUCCESS, TaskStatus.ERROR, TaskStatus.CANCELLED]
        return is_complete

    def set_task_status(self, task_key: TaskKey, status: TaskStatus):
        self._store.data['task_status'][task_key] = status.value

    def set_task_outputs(self, task_key: TaskKey, outputs: List[str]):
        self._store.data['task_outputs'][task_key] = outputs

    def get_task_outputs(self, task_key: TaskKey) -> Optional[List[str]]:
        if len(self._store.data['task_outputs'][task_key]) == 0:
            return None
        else:
            return list(self._store.data['task_outputs'][task_key])

    def is_job_complete(self) -> bool:
        return all([self.is_task_complete(task_key) for task_key in self.tasks()])

    def tasks(self, status: TaskStatus = None) -> List[TaskKey]:
        tasks = list(self._store.data['tasks'])
        if status is None:
            return tasks

        ret = []
        for task in tasks:
            if self.get_status(task_key=task) == status:
                ret.append(task)

        return ret

    def completed_tasks(self) -> List[TaskKey]:
        completed = []
        for task_key in self.tasks():
            if self.is_task_complete(task_key):
                completed.append(task_key)
        return completed


def load_job(directory: str) -> Tuple[JobState, JobMeta]:
    job_state = JobState.load(directory)
    job_meta = JobMeta(directory)
    return job_state, job_meta

def job_exists(job_path: str):
    try:
        job_state, job_meta = load_job(job_path)
    except:
        return False
    return True

def create_job(directory, pipeline: PipelineConfig, datasets: List[VIAMEDataset], force=False) -> str:
    if os.path.isdir(directory) or os.path.isfile(directory):
        if force:
            shutil.rmtree(directory, ignore_errors=True)
        else:
            raise Exception('Either directory already exists or is a file an not a directory')

    pipeline_directory = pipelines_dir(directory)
    meta_directory = meta_dir(directory)
    logs_directory = logs_dir(directory)
    error_outputs_directory = error_outputs_dir(directory)
    os.makedirs(directory, exist_ok=False)
    os.makedirs(pipeline_directory, exist_ok=False)
    os.makedirs(meta_directory, exist_ok=False)
    os.makedirs(logs_directory, exist_ok=False)
    os.makedirs(error_outputs_directory, exist_ok=False)
    os.makedirs(completed_outputs_dir(directory), exist_ok=False)
    os.makedirs(pending_outputs_dir(directory), exist_ok=False)
    try:
        # initialize state and meta
        # TODO make interface for initializing job state and meta the same
        job_meta = JobMeta(directory)
        job_meta.create_meta(pipeline=pipeline, datasets=datasets)
        job_state = JobState(directory, job_meta.keys())
    except Exception as e:
        # clean up if failed for some reason
        # important to make sure this is never reached without the initial directory exists check
        # because we don't wan't to delete a pre-existing job directory
        shutil.rmtree(directory)
        raise e
    return directory
