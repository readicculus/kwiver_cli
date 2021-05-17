from prompt_toolkit import prompt, HTML
from prompt_toolkit.shortcuts import ProgressBar

from archive.cli import configure_pipeline
from archive.cli.dialogs import DatasetCompleter
from archive.cli.dialogs import rainbow_progress_bar
from pep_tk.config import pipeline_environment
from pep_tk.datasets import DatasetManifest, VIAMEDataset
from config.pipelines import PipelineManifest






class CLIFlow:
    def start(self):
        self.part1()

    def part1(self):
        datasets_filter = prompt('Select which dataset/s you want to use > ', completer=DatasetCompleter(parser))
        datasets = parser.get_datasets(datasets_filter)

        while len(datasets) == 0 or not self.part2(datasets):
            datasets_filter = prompt('Select which dataset/s you want to use > ', completer=DatasetCompleter(parser))
            datasets = parser.get_datasets(datasets_filter)

    def part2(self, selected_datasets):
        print("\nYou've selected the following %d datasets:" % len(selected_datasets))
        for i, ds in enumerate(selected_datasets):
            print('%d: %s' % (i+1, ds))

        confirm = False
        while not confirm:
            res = prompt('\nContinue? Y/N:')
            confirm = res == 'Y'
            if res == 'N':
                return False

        datasets = {dataset_name: VIAMEDataset(dataset_name, attributes) for dataset_name, attributes in
                        selected_datasets.items()}
        return self.part3(datasets)

    def part3(self, datasets):

            from pep_tk.kwiver.embedded_runner import EmbeddedPipelineWorker

            title = HTML('Running %s on <style bg="yellow" fg="black">%d datasets...</style>' %
                         (pipeline.name, len(datasets)))

            with ProgressBar(title=title, formatters=rainbow_progress_bar) as pb:
            # with ProgressBar(title=title) as pb:
                progress_bars = {}
                workers = []
                for name, dataset in datasets.items():
                    with pipeline_environment(pipeline, dataset):
                        worker = EmbeddedPipelineWorker(name,dataset, pipeline.path)
                        label = HTML('<ansired>%s</ansired>: ' % name)
                        progress_bars[name] = pb(range(worker.total), label=label)
                        worker.set_progress_counter(progress_bars[name])
                        workers.append(worker)

                for w in workers:
                    w.run()





if __name__ == "__main__":
    try:
        pipeline_manifest = 'conf/pipeline_manifest.yaml'
        pipeline_manifest = PipelineManifest(pipeline_manifest)
        # parser = DatasetsParser('conf/debug_datasets.yaml')
        # datasets = parser.get_dataset('debug:a')
        # dataset = datasets['debug:a']
        #
        pipeline = pipeline_manifest['JoBBS_seal_yolo_ir_eo_region_trigger']

        configure_pipeline(pipeline)

        parser = DatasetManifest('conf/debug_datasets.yaml')
        # parser = DatasetManifest('conf/debug_datasets.yaml')

        flow = CLIFlow()
        flow.start()
    except KeyboardInterrupt:
        pass
