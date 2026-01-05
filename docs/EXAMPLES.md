# Examples

Practical examples of using NebulaCompute for various use cases.

## Table of Contents

- [Basic Usage](#basic-usage)
- [Python Jobs](#python-jobs)
- [Machine Learning](#machine-learning)
- [Data Processing](#data-processing)
- [Docker Jobs](#docker-jobs)
- [GPU Computing](#gpu-computing)
- [Batch Processing](#batch-processing)
- [Advanced Patterns](#advanced-patterns)

## Basic Usage

### Hello World

```bash
# Simple command
nebula job submit "echo 'Hello from NebulaCompute!'"

# Check status
nebula job list
```

### With Resource Requirements

```bash
# Request 4 CPU cores and 8GB memory
nebula job submit --cpu 4 --memory 8192 "echo 'Running with resources'"
```

### With Priority

```bash
# High priority job
nebula job submit --priority high "echo 'Important task'"

# Low priority background task
nebula job submit --priority low "echo 'Background task'"
```

### With Timeout

```bash
# 1 hour timeout
nebula job submit --timeout 3600 "long_running_script.sh"
```

## Python Jobs

### Simple Script

```bash
nebula job submit "python -c 'print(sum(range(1000)))'"
```

### Script File

```bash
# script.py on worker filesystem
nebula job submit "python /shared/scripts/analysis.py"
```

### With Dependencies

```bash
# Install deps and run
nebula job submit "pip install pandas && python analyze.py"
```

### Using Virtual Environment

```bash
nebula job submit "source /venv/bin/activate && python train.py"
```

### With Arguments

```bash
nebula job submit "python train.py --epochs 100 --batch-size 32"
```

## Machine Learning

### Training a Model

```bash
# Simple training job
nebula job submit \
  --cpu 8 \
  --memory 16384 \
  --gpu 1 \
  "python train_model.py --data /data/train --output /results/model.pt"
```

### Hyperparameter Search

```bash
# Submit multiple training jobs with different parameters
for lr in 0.001 0.01 0.1; do
  for batch in 16 32 64; do
    nebula job submit \
      --gpu 1 \
      --tags experiment \
      --env LEARNING_RATE=$lr \
      --env BATCH_SIZE=$batch \
      "python train.py"
  done
done
```

### Distributed Training (PyTorch)

```python
# distributed_train.py
import os
import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel

def main():
    rank = int(os.environ['RANK'])
    world_size = int(os.environ['WORLD_SIZE'])

    dist.init_process_group(
        backend='nccl',
        init_method='env://',
        rank=rank,
        world_size=world_size
    )

    model = YourModel().cuda()
    model = DistributedDataParallel(model)

    # Training loop...

if __name__ == '__main__':
    main()
```

```bash
# Submit distributed job
nebula job submit \
  --gpu 4 \
  --replicas 4 \
  --env MASTER_ADDR=master \
  --env MASTER_PORT=29500 \
  "torchrun --nproc_per_node=1 distributed_train.py"
```

### Model Inference

```bash
# Batch inference
nebula job submit \
  --gpu 1 \
  --memory 8192 \
  "python inference.py --model /models/best.pt --input /data/test"
```

## Data Processing

### Pandas DataFrame Processing

```python
# process_data.py
import pandas as pd
import sys

input_file = sys.argv[1]
output_file = sys.argv[2]

df = pd.read_csv(input_file)
df['processed'] = df['value'] * 2
df.to_csv(output_file, index=False)
print(f"Processed {len(df)} rows")
```

```bash
nebula job submit \
  --cpu 4 \
  --memory 8192 \
  "python process_data.py /data/input.csv /data/output.csv"
```

### Parallel File Processing

```bash
# Process multiple files in parallel
for file in /data/*.csv; do
  nebula job submit \
    --cpu 2 \
    "python process.py $file"
done
```

### ETL Pipeline

```bash
# Extract
nebula job submit --name extract \
  "python extract.py --source db --output /tmp/raw.parquet"

# Transform (depends on extract)
nebula job submit --name transform --depends-on extract \
  "python transform.py --input /tmp/raw.parquet --output /tmp/clean.parquet"

# Load (depends on transform)
nebula job submit --name load --depends-on transform \
  "python load.py --input /tmp/clean.parquet --target warehouse"
```

## Docker Jobs

### Basic Docker Job

```bash
nebula job submit \
  --docker python:3.11 \
  "python -c 'import sys; print(sys.version)'"
```

### Custom Docker Image

```bash
nebula job submit \
  --docker my-registry.com/ml-image:latest \
  --cpu 4 \
  --gpu 1 \
  "python train.py"
```

### Docker with Volume Mounts

```bash
nebula job submit \
  --docker python:3.11 \
  --volume /host/data:/data:ro \
  --volume /host/results:/results \
  "python analyze.py /data/input.csv /results/output.csv"
```

### Docker with Environment

```bash
nebula job submit \
  --docker python:3.11 \
  --env DATABASE_URL=postgresql://... \
  --env API_KEY=secret \
  "python migrate.py"
```

## GPU Computing

### CUDA Job

```bash
nebula job submit \
  --gpu 1 \
  --docker nvidia/cuda:11.8-runtime \
  "nvidia-smi && python gpu_test.py"
```

### Multi-GPU Job

```bash
nebula job submit \
  --gpu 4 \
  "python train.py --gpus 4"
```

### GPU Memory Requirements

```bash
# Require GPU with at least 16GB memory
nebula job submit \
  --gpu 1 \
  --gpu-memory 16384 \
  "python large_model.py"
```

## Batch Processing

### Array Jobs

```bash
# Process items 0-99
for i in $(seq 0 99); do
  nebula job submit \
    --name "task-$i" \
    --env TASK_INDEX=$i \
    "python process_chunk.py --index $i"
done
```

### Workflow with Dependencies

```bash
# Job A (independent)
JOB_A=$(nebula job submit --name job-a "echo 'A'" --quiet)

# Job B (independent)
JOB_B=$(nebula job submit --name job-b "echo 'B'" --quiet)

# Job C (depends on A and B)
nebula job submit --name job-c \
  --depends-on $JOB_A,$JOB_B \
  "echo 'C - runs after A and B'"
```

### Scheduled Jobs

```bash
# Run every hour
nebula job schedule \
  --cron "0 * * * *" \
  --name hourly-report \
  "python generate_report.py"
```

## Advanced Patterns

### Retry on Failure

```bash
nebula job submit \
  --retries 3 \
  --retry-delay 60 \
  "python flaky_task.py"
```

### Resource Cleanup

```python
# cleanup_job.py
import atexit
import os

def cleanup():
    os.remove('/tmp/temp_file')
    print("Cleaned up")

atexit.register(cleanup)

# Main work...
```

### Progress Reporting

```python
# progress_job.py
import sys

for i in range(100):
    # Do work...
    print(f"PROGRESS: {i+1}%", file=sys.stderr, flush=True)
```

### Output Artifacts

```python
# artifact_job.py
import json
import os

# Do computation
result = {"accuracy": 0.95, "loss": 0.05}

# Write to artifacts directory
artifacts_dir = os.environ.get('NEBULA_ARTIFACTS_DIR', '/tmp')
with open(f"{artifacts_dir}/results.json", 'w') as f:
    json.dump(result, f)
```

```bash
# Submit and retrieve artifacts
JOB_ID=$(nebula job submit --quiet "python artifact_job.py")
nebula job wait $JOB_ID
nebula job artifacts $JOB_ID --output ./results/
```

### Using Configuration Files

```yaml
# job.yaml
name: training-job
command: python train.py
resources:
  cpu: 8
  memory: 16384
  gpu: 1
environment:
  LEARNING_RATE: "0.001"
  EPOCHS: "100"
tags:
  - ml
  - training
```

```bash
nebula job submit --from-file job.yaml
```

### Python SDK Usage

```python
from nebulacompute import Client

# Connect to cluster
client = Client("http://localhost:8000")

# Submit job
job = client.submit_job(
    command="python train.py",
    resources={"cpu": 4, "memory": 8192, "gpu": 1},
    environment={"EPOCHS": "100"},
    tags=["ml"],
)

# Wait for completion
result = job.wait()
print(f"Job {job.id} completed with status: {result.status}")
print(f"Output: {result.output}")
```

### Monitoring Job Progress

```python
from nebulacompute import Client
import time

client = Client("http://localhost:8000")
job = client.submit_job("python long_task.py")

while not job.is_finished():
    status = job.status()
    print(f"Status: {status.state}, Progress: {status.progress}%")
    time.sleep(5)

print(f"Final status: {job.status().state}")
```

## See Also

- [CLI Reference](CLI_REFERENCE.md)
- [API Reference](API_REFERENCE.md)
- [Configuration Guide](CONFIGURATION.md)
