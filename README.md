# MLPerf Reference Implementations

This is a repository of reference implementations for the MLPerf benchmarks. These implementations are valid as starting points for benchmark implementations but are not fully optimized and are not intended to be used for "real" performance measurements of software frameworks or hardware. 

These reference implementations are still very much "alpha" or "beta" quality. They could be improved in many ways. Please file issues or pull requests to help us improve quality.

# Contents

We provide reference implementations for benchmarks in the MLPerf suite, as well as several benchmarks under development. 

Each reference implementation provides the following:
 
* Code that implements the model in at least one framework.
* A Dockerfile which can be used to run the benchmark in a container.
* A script which downloads the appropriate dataset.
* A script which runs and times training the model.
* Documentation on the dataset, model, and machine setup.

# Running Benchmarks

These benchmarks have been tested on the following machine configuration:

* 16 CPUs, one Nvidia P100.
* Ubuntu 16.04, including docker with nvidia support.
* 600GB of disk (though many benchmarks do require less disk).
* Either CPython 2 or CPython 3, depending on benchmark (see Dockerfiles for details).

Generally, a benchmark can be run with the following steps:

1. Setup docker & dependencies. There is a shared script (install_cuda_docker.sh) to do this. Some benchmarks will have additional setup, mentioned in their READMEs.
2. Download the dataset using `./download_dataset.sh`. This should be run outside of docker, on your host machine. This should be run from the directory it is in (it may make assumptions about CWD).
3. Optionally, run `verify_dataset.sh` to ensure the was successfully downloaded.
4. Build and run the docker image, the command to do this is included with each Benchmark. 

Each benchmark will run until the target quality is reached and then stop, printing timing results. 

Some these benchmarks are rather slow or take a long time to run on the reference hardware (i.e. 16 CPUs and one P100). We expect to see significant performance improvements with more hardware and optimized implementations. 

## Running with Popper

[Popper](https://github.com/systemslab/popper) is a tool for defining and executing container-native workflows either locally or on CI services. Some workflows in this repository contain a `wf.yml` file that defines a Popper workflow for automatically downloading and verifying data, running the benchmark and generating a report. The execution and report generation both comply with the [MLPerf training rules](https://github.com/mlperf/training_policies/blob/master/training_rules.adoc). More details about Popper can be found [here](https://popper.readthedocs.io/).


### Instructions:

1. Clone the repository.
```
git clone https://github.com/mlperf/training
```

2. Install docker, cuda-runtime and nvidia-docker on the machine.
```
./training/install_cuda_docker.sh
```

3. Install the `popper` tool.
```
pip install popper
```
We recommend to use a [virtualenv](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/#creating-a-virtual-environment) for installing Popper.

4. Run the workflow. As an example, for single stage detector workflow,
```
cd single_stage_detector/
popper run -f wf.yml -c settings.py
```
Here, the `settings.py` file contains necessary configuration that needs to be passed to the container engine in order to use the nvidia drivers. For more information about customizing container engine parameters, see [here](https://popper.readthedocs.io/en/latest/sections/cli_features.html#customizing-container-engine-behavior).

# Suggestions
