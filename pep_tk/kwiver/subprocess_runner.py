import os
import subprocess

from config.pipelines import PipelineManifest


class KwiverRunner:
    '''
        Runner for running non-embedded pipelines that have no input output ports.
        Uses subprocess to call kwiver_runner
    '''
    def __init__(self):
        pass

    def __get_pipeline_cmd(self, debug=False):
        # return ['kwiver', 'pipe-to-dot', '--setup','-p']
        if os.name == 'nt':
            if debug:
                return ['kwiver.exe', 'runner']
            else:
                return ['kwiver.exe', 'runner']
        else:
            if debug:
                return ['gdb', '--args', 'kwiver', 'runner']
            else:
                return ['kwiver', 'runner']

    def __execute_command(self, cmd, stdout=None, stderr=None ):
        if os.name == 'nt' and stdout is None:
            fnull = open( os.devnull, "w" )
            return subprocess.call( cmd, stdout=fnull, stderr=subprocess.STDOUT )

        return subprocess.Popen( cmd, stdout=stdout, stderr=stderr )


    def run(self, pipeline_fp):
        cmd = self.__get_pipeline_cmd() + [pipeline_fp]
        x = self.__execute_command(cmd)
        return x

class KwiverRunnerMonitor:
    '''
        Progress monitor that monitors a KwiverRunners progress by periodically checking the output image list
        and updating progress bars in the cli accordingly.
    '''
    def __init__(self, pipeline: PipelineManifest):
        self.pipeline = pipeline


    def update(self, count):
        pass