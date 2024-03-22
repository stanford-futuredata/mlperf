# Benchmark execution with MLCube

## Current implementation

We'll be updating this section as we merge MLCube PRs and make new MLCube releases.

### Project setup
```Python
# Create Python environment and install MLCube Docker runner 
virtualenv -p python3 ./env && source ./env/bin/activate && pip install mlcube-docker

# Fetch the Object Detection workload
git clone https://github.com/mlcommons/training && cd ./training
git fetch origin pull/501/head:feature/object_detection && git checkout feature/object_detection
cd ./object_detection/mlcube
```

### Dataset


The COCO dataset will be downloaded and extracted. Sizes of the dataset in each step:

| Dataset Step                   | MLCube Task       | Format         | Size     |
|--------------------------------|-------------------|----------------|----------|
| Download (Compressed dataset)  | download_data     | Tar/Zip files  | ~20.5 GB |
| Extract (Uncompressed dataset) | download_data     | Jpg/Json files | ~21.2 GB |
| Total                          | (After all tasks) | All            | ~41.7 GB |

### Tasks execution

Parameters are defined at these files:

* MLCube user parameters: mlcube/workspace/parameters.yaml
* Project user parameters: pytorch/configs/e2e_mask_rcnn_R_50_FPN_1x.yaml
* Project default parameters: pytorch/maskrcnn_benchmark/config/defaults.py

```

# Download COCO dataset. Default path = /workspace/data
python mlcube_cli.py run --task download_data --platform docker

# Run benchmark. Default paths = ./workspace/data
python mlcube_cli.py run --task train --platform docker
```

Parameters defined at **mculbe/mlcube.yaml** could be overridden using: `--param=input`

We are targeting pull-type installation, so MLCube images should be available on docker hub. If not, try this:

```bash
mlcube run ... -Pdocker.build_strategy=always
```