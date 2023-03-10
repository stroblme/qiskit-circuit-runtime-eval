from kedro.extras.datasets.pandas import CSVDataSet
from kedro.extras.datasets.plotly import JSONDataSet
from kedro.io import Version
from kedro.framework.hooks import hook_impl

from typing import Any, Dict

import glob
from pathlib import Path

import os
import logging
from kedro.io import DataCatalog


class ProjectHooks:
    @hook_impl
    def before_pipeline_run(self, run_params: Dict[str, Any], pipeline, catalog):
        """A hook implementation to add a catalog entry
        based on the filename passed to the command line, e.g.:
            kedro run --params=input:iris_1.csv
            kedro run --params=input:iris_2.csv
            kedro run --params=input:iris_3.csv
        """

        # ----------------------------------------------------------------
        # If we are running a new experiment setup (e.g. executing the "pre" pipeline), we want to cleanup all the files that are **not** versioned but were used as results in previous runs
        # ----------------------------------------------------------------

        if run_params["pipeline_name"] == "pre":
            tempFiles = glob.glob("data/02_intermediate/*.csv")
            for f in tempFiles:
                os.remove(f)

            tempFiles = glob.glob("data/04_execution_result/*.csv")
            for f in tempFiles:
                os.remove(f)

            tempFiles = glob.glob("data/05_execution_durations/*.csv")
            for f in tempFiles:
                os.remove(f)

            tempFiles = glob.glob("data/07_reporting/*.tmp")
            for f in tempFiles:
                os.remove(f)


class DataCatalogHooks:
    @property
    def _logger(self):
        return logging.getLogger(self.__class__.__name__)

    @hook_impl
    def after_catalog_created(self, catalog: DataCatalog) -> None:
        # ----------------------------------------------------------------
        # This section creates csv datasets based on the partitioned dataset stored in the intermediate directory
        # Also based on those partitions, it creates further csv datasets for the evaluation durations and the evaluation results
        # ----------------------------------------------------------------

        # get all the partitions created by the "pre" pipeline
        partitions = glob.glob("data/02_intermediate/*.csv")

        for partition in partitions:
            # ------------------------------------------------------------------
            # Create csv dataset from partitioned dataset for partitions
            # ------------------------------------------------------------------

            # partition loader
            evaluation_partitions_name = (
                f"data_generation.evaluation_partition_{Path(partition).stem}"
            )
            input_dataset = CSVDataSet(filepath=partition)
            catalog.add(evaluation_partitions_name, input_dataset)

            # ------------------------------------------------------------------
            # Create csv dataset from partitioned dataset for evaluation durations
            # ------------------------------------------------------------------

            # evaluation durations
            execution_duration = partition.replace(
                "02_intermediate", "05_execution_durations"
            )
            execution_duration_name = (
                f"data_science.execution_duration_{Path(execution_duration).stem}"
            )
            input_dataset = CSVDataSet(filepath=execution_duration)
            catalog.add(execution_duration_name, input_dataset)

            # ------------------------------------------------------------------
            # Create csv dataset from partitioned dataset for evaluation results
            # ------------------------------------------------------------------

            # evaluation results
            execution_result = partition.replace(
                "02_intermediate", "04_execution_result"
            )
            execution_result_name = (
                f"data_science.execution_result_{Path(execution_result).stem}"
            )
            input_dataset = CSVDataSet(filepath=execution_result)
            catalog.add(execution_result_name, input_dataset)

        # ----------------------------------------------------------------
        # This section ensures that the reporting dictionary always contains the proper output data catalogs so that kedro-viz is happy
        # ----------------------------------------------------------------

        # get the evaluation matrix where information about all the possible combinations is stored
        evaluation_matrix = catalog.datasets.data_generation__evaluation_matrix.load()

        # generate a list of names that will be used as plots later in the visualization pipeline
        # If you add new visualization outputs, you must also create the file names here
        names = []
        for f in evaluation_matrix["frameworks"]:
            for q in evaluation_matrix["qubits"]:
                names.append(f"framework_{f}_qubits_{q}")
            for d in evaluation_matrix["depths"]:
                names.append(f"framework_{f}_depth_{d}")

        for d in evaluation_matrix["depths"]:
            for s in evaluation_matrix["shots"]:
                names.append(f"shots_{s}_depth_{d}")

        for d in evaluation_matrix["depths"]:
            for q in evaluation_matrix["qubits"]:
                names.append(f"qubits_{q}_depth_{d}")

        for s in evaluation_matrix["shots"]:
            for q in evaluation_matrix["qubits"]:
                names.append(f"shots_{s}_qubits_{q}")


        # use the dummy dataset to get the version of the current kedro run, so that it matches the ones from the versioned datasets
        version = Version(None, catalog.datasets.dummy_versioned_dataset._version.save)

        # iterate all the names and create a JSONDataSet (plotly) for each one
        for name in names:
            filepath = os.path.join("data/07_reporting/", f"{name}.json")

            dataset_template = JSONDataSet(filepath=filepath, version=version)
            catalog.add(name, dataset_template)

            # create a dictionary if necessary (versioned datasets need dictionaries)
            try:
                os.mkdir(filepath)
            except FileExistsError:
                # directory already exists
                pass

            # create a .tmp file which we will use later in the pipeline_registry to create node outputs dynamically
            with open(os.path.join("data/07_reporting/", f"{name}.tmp"), "w") as f:
                f.write("")
