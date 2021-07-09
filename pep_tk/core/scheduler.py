import abc
import os
import shutil
import signal
import subprocess
import threading
import time
from time import sleep
from datetime import datetime

try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty  # python 3.x

from pep_tk.core.job import JobState, JobMeta, TaskStatus, TaskKey
from pep_tk.core.kwiver.pipeline_compiler import compile_output_filenames
from pep_tk.core.kwiver.subprocess_runner import KwiverRunner


class SchedulerEventManager(metaclass=abc.ABCMeta):
    def __init__(self):
        self.task_start_time = {}
        self.task_end_time = {}
        self.task_status = {}
        self.task_messages = {}
        self.stdout = {}  # TODO probably issue with storing stdout and stderr for all tasks in memory
        self.stderr = {}
        self.task_count = {}
        self.task_max_count = {}
        self.initialized_tasks = []

    def initialize_task(self, task_key: TaskKey, count: int, max_count: int, status: TaskStatus):
        self.task_count[task_key] = count
        self.task_max_count[task_key] = max_count
        self.task_status[task_key] = status
        self.initialized_tasks.append(task_key)
        self._initialize_task(task_key, count, max_count, status)

    def start_task(self, task_key: TaskKey):
        self.task_status[task_key] = TaskStatus.RUNNING
        self.task_start_time[task_key] = time.time()
        return self._start_task(task_key)

    def end_task(self, task_key: TaskKey, status: TaskStatus):
        self.task_end_time[task_key] = time.time()
        self.task_status[task_key] = status
        return self._end_task(task_key, status)

    def check_cancelled(self, task_key: TaskKey) -> bool:
        return self._check_cancelled(task_key)

    def update_task_progress(self, task_key: TaskKey, current_count: int):
        self.task_count[task_key] = current_count
        return self._update_task_progress(task_key, current_count, self.task_max_count[task_key])

    def update_task_stdout(self, task_key: TaskKey, line: str):
        if task_key not in self.stdout:
            self.stdout[task_key] = ""
        self.stdout[task_key] += line
        self._update_task_stdout(task_key, line)

    def update_task_stderr(self, task_key: TaskKey, line: str):
        if task_key not in self.stderr:
            self.stderr[task_key] = ""
        self.stderr[task_key] += line
        self._update_task_stdout(task_key, line)

    def elapsed_time(self, task_key: TaskKey) -> float:
        if task_key not in self.task_start_time:
            return 0.
        if task_key not in self.task_end_time:
            return time.time() - self.task_start_time[task_key]
        return self.task_end_time[task_key] - self.task_start_time[task_key]

    @abc.abstractmethod
    def _initialize_task(self, task_key: TaskKey, count: int, max_count: int, status: TaskStatus):
        pass

    @abc.abstractmethod
    def _start_task(self, task_key: TaskKey):
        pass

    @abc.abstractmethod
    def _end_task(self, task_key: TaskKey, status: TaskStatus):
        pass

    @abc.abstractmethod
    def _update_task_progress(self, task_key: TaskKey, current_count: int, max_count: int):
        pass

    @abc.abstractmethod
    def _update_task_stdout(self, task_key: TaskKey, line: str):
        pass

    @abc.abstractmethod
    def _update_task_stderr(self, task_key: TaskKey, line: str):
        pass

    @abc.abstractmethod
    def _check_cancelled(self, task_key: TaskKey) -> bool:
        pass


# Scheduler helpers
def poll_image_list(fp: str):
    if not os.path.exists(fp):
        return 0
    with open(fp) as f:
        count = sum(1 for _ in f)
    return count


def monitor_outputs(stop_event: threading.Event, task_key: TaskKey, manager: SchedulerEventManager,
                    output_file: str, poll_freq: int):
    while not stop_event.wait(poll_freq):
        count = poll_image_list(output_file)
        manager.update_task_progress(task_key, count)


def enqueue_output(out, queue, evt: threading.Event):
    # don't want it to stop on an emty byte(b'') because we need to detect
    # if an empty byte has come through and we can't do it asynchronously
    for line in iter(out.readline, b'foobar'):
        if evt.is_set():
            break
        queue.put(line)


def move_output_files(output_fps, destination_dir):
    for current_loc in output_fps:
        new_loc = os.path.join(destination_dir, os.path.basename(current_loc))
        shutil.move(current_loc, new_loc)


class Scheduler:
    def __init__(self,
                 job_state: JobState,
                 job_meta: JobMeta,
                 manager: SchedulerEventManager,
                 kwiver_setup_path: str,
                 progress_poll_freq: int = 5):
        """
        Initialize a Scheduler for proccessing task queue synchronously.

        :param job_state: the job state
        :param job_meta: the job metadata
        :param manager: manager for dispatching events, updating progress, etc..
        :param kwiver_setup_path: setup_viame.sh/bat path
        :param progress_poll_freq: frequency to poll progress (reads output file and counts progress)
        """
        self.job_state = job_state
        self.job_meta = job_meta
        self.manager = manager
        self.kwiver_setup_path = kwiver_setup_path
        self.progress_poll_freq = progress_poll_freq

    def run(self):
        # if resuming mark already completed tasks as completed
        for task_key in self.job_state.tasks(status=TaskStatus.SUCCESS):
            pipeline_fp, dataset, outputs = self.job_meta.get(task_key)
            max_image_count = max(dataset.thermal_image_count, dataset.color_image_count)
            self.manager.initialize_task(task_key, max_image_count, max_image_count, TaskStatus.SUCCESS)

        for task_key in self.job_state.tasks():
            status = self.job_state.get_status(task_key)
            if status != TaskStatus.SUCCESS:
                pipeline_fp, dataset, outputs = self.job_meta.get(task_key)
                max_image_count = max(dataset.thermal_image_count, dataset.color_image_count)
                self.manager.initialize_task(task_key, 0, max_image_count, TaskStatus.INITIALIZED)

        while not self.job_state.is_job_complete():
            current_task_key = self.job_state.current_task()
            print(current_task_key)
            pipeline_fp, dataset, outputs = self.job_meta.get(current_task_key)

            max_image_count = max(dataset.thermal_image_count, dataset.color_image_count)

            # Create the environment variables needed for running
            #  - output ports (image list and viame detection csv file names)
            #  - the kwiver environment required for running kwiver runner
            t = datetime.now()
            csv_ports_raw = outputs.get_det_csv_env_ports()
            image_list_raw = outputs.get_image_list_env_ports()

            pipeline_output_csv_env = compile_output_filenames(csv_ports_raw, path=self.job_meta.root_dir, t=t)
            pipeline_output_image_list_env = compile_output_filenames(image_list_raw, path=self.job_meta.root_dir, t=t)

            env = {**pipeline_output_csv_env, **pipeline_output_image_list_env}

            # Setup error log
            error_log_fp = os.path.join(self.job_meta.logs_dir,
                                        f'stderr-{current_task_key.replace(":", "_")}.log')
            error_log = open(error_log_fp, 'w+b')

            # Update Task Started
            self.manager.start_task(current_task_key)
            self.job_state.set_task_status(current_task_key, TaskStatus.RUNNING)

            # create the progress polling thread and start it
            image_list_monitor = list(pipeline_output_image_list_env.values())[0]  # Image list to monitor
            prog_stop_evt = threading.Event()
            thread_args = (prog_stop_evt, current_task_key, self.manager, image_list_monitor, self.progress_poll_freq)
            progress_thread = threading.Thread(target=monitor_outputs,
                                               args=thread_args,
                                               daemon=True)
            progress_thread.start()

            # Create the kwiver runner and run it
            kwr = KwiverRunner(pipeline_fp,
                               cwd=self.job_meta.root_dir,
                               env=env,
                               kwiver_setup_path=self.kwiver_setup_path)

            process = kwr.run(stdout=subprocess.PIPE, stderr=error_log)

            keep_stdout = True
            stdout = ""

            if process.stdout is None:
                raise RuntimeError("Stdout must not be none")

            # Stdout Thread
            q = Queue()
            t = threading.Thread(target=enqueue_output, args=(process.stdout, q, prog_stop_evt))
            t.daemon = True  # thread dies with the program
            t.start()
            cancelled = False
            while True:  # read line without blocking
                sleep(.2)
                try:
                    line = q.get_nowait()
                    if line == b'': break  # job is complete if empty byte received
                except Empty:
                    # check if user cancelled task, if cancelled kill kwiver process and stop output reading loop
                    cancelled = self.manager.check_cancelled(current_task_key)
                    if cancelled:
                        cancelled = True
                        break

            # stop polling for progress and stop polling for stdout
            prog_stop_evt.set()

            outputs_to_move = list(pipeline_output_csv_env.values()) + list(pipeline_output_image_list_env.values())

            # if user cancells task
            if cancelled:
                process.send_signal(signal.SIGTERM)
                process.send_signal(signal.SIGKILL)
                print(f'Cancelled {current_task_key}')

                count = poll_image_list(image_list_monitor)
                self.manager.update_task_progress(current_task_key, count)
                self.job_state.set_task_status(current_task_key, TaskStatus.CANCELLED)
                self.manager.end_task(current_task_key, TaskStatus.CANCELLED)

                # Move outputs to error folder
                move_output_files(outputs_to_move, self.job_meta.error_outputs_dir)
                continue

            # Wait for exit up to 30 seconds after kill
            code = process.wait(30)

            if code > 0:  # ERROR
                error_log.seek(0)
                stderr_log = error_log.read().decode()
                error_log.close()

                # Update Task Ended with error
                count = poll_image_list(image_list_monitor)
                self.manager.update_task_progress(current_task_key, count)
                self.job_state.set_task_status(current_task_key, TaskStatus.ERROR)
                self.manager.update_task_stderr(current_task_key, stderr_log)
                self.manager.end_task(current_task_key, TaskStatus.ERROR)

                # Move output files to error dir
                outputs_to_move = list(pipeline_output_csv_env.values()) + list(pipeline_output_image_list_env.values())
                for current_loc in outputs_to_move:
                    new_loc = os.path.join(self.job_meta.error_outputs_dir, os.path.basename(current_loc))
                    shutil.move(current_loc, new_loc)
                # TODO show error in UI, and save in log somewhere
            else:  # SUCCESS
                # Update Task final count, has to be done before moving file
                count = poll_image_list(image_list_monitor)
                self.manager.update_task_progress(current_task_key, count)

                # Move outputs to completed folder
                move_output_files(outputs_to_move, self.job_meta.completed_outputs_dir)

                # Update Task Ended with success
                self.job_state.set_task_status(current_task_key, TaskStatus.SUCCESS)
                self.manager.end_task(current_task_key, TaskStatus.SUCCESS)

            error_log.close()
