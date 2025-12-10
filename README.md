# AWS Tools

Practical AWS scripts built for task automation, debugging, and cloud resource management.

## Scripts Overview

| Script | Description | What It Does |
|--------|-------------|--------------|
| `ecs_cost_analyzer.py` | ECS Cost Analyzer | Analyzes ECS service costs by day, grouped by service name and usage type. Shows daily cost breakdowns and totals. |
| `ec2_cost_analyzer.py` | EC2 Cost Analyzer | Analyzes EC2 costs (Compute & Other) by day, grouped by Tag (default: Name) and usage type. Shows daily cost breakdowns. |
| `lambda_cost_analyzer.py` | Lambda Cost Analyzer | Analyzes Lambda function costs in two ways: actual costs from Cost Explorer and estimated costs per function from CloudWatch metrics. Shows real usage data (invocations, duration). |
| `ecs_task_autoscaler.py` | ECS Task Autoscaler | Automatically scales ECS workers based on RabbitMQ queue size. Scales up immediately, scales down with delay to prevent flapping. Can be integrated into any scheduling system. |

## Requirements

- Python 3.6+
- AWS credentials configured
- AWS Cost Explorer API enabled

## Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## AWS Configuration

Configure AWS credentials:
```bash
aws configure
```

Required IAM permissions:
```json
{
    "Effect": "Allow",
    "Action": [
        "ce:GetCostAndUsage",
        "lambda:ListFunctions",
        "lambda:GetFunction",
        "lambda:ListTags",
        "cloudwatch:GetMetricStatistics"
    ],
    "Resource": "*"
}
```

**Note:** Enable Cost Explorer in AWS Console if not already active.

## Script: ecs_cost_analyzer.py

Analyzes ECS costs by service and usage type. Groups costs by `aws:ecs:serviceName` tag and displays daily totals.

### Usage

```bash
# Last 7 days (default)
python ecs_cost_analyzer.py

# Last 30 days
python ecs_cost_analyzer.py --days 30

# Filter by cluster
python ecs_cost_analyzer.py --cluster my-cluster

# Combine options
python ecs_cost_analyzer.py --days 14 --cluster production
```

### Parameters

- `--days`: Number of days to analyze (default: 7)
- `--cluster`: Filter by ECS cluster name (requires `aws:ecs:clusterName` tag)

### Output

<img width="629" height="402" alt="Screenshot 2025-12-07 at 17 38 18" src="https://github.com/user-attachments/assets/2b3d0821-128c-4df2-b45e-29f2383f249c" />

## Script: ec2_cost_analyzer.py

Analyzes EC2 costs for "Amazon Elastic Compute Cloud - Compute" and "EC2 - Other" services. Groups costs by a specified tag (default: `Name`) and displays daily totals.

### Usage

```bash
# Last 7 days (default) - grouped by Name tag
python ec2_cost_analyzer.py

# Last 30 days
python ec2_cost_analyzer.py --days 30

# Group by a different tag (e.g., Environment)
python ec2_cost_analyzer.py --tag Environment
```

### Parameters

- `--days`: Number of days to analyze (default: 7)
- `--tag`: Cost Allocation Tag to group by (default: 'Name')

### Output

Detailed table showing:
- Date
- Tag Value (e.g., Instance Name)
- Usage Type (e.g., BoxUsage:t3.medium)
- Cost


## Script: lambda_cost_analyzer.py

Analyzes AWS Lambda costs in two ways: **actual costs** from Cost Explorer and **estimated compute costs** per function from CloudWatch metrics.

### Usage

```bash
# Last 7 days (default)
python lambda_cost_analyzer.py

# Last 30 days
python lambda_cost_analyzer.py --days 30

# Specific region
python lambda_cost_analyzer.py --region us-east-1
```

### Parameters

- `--days`: Number of days to analyze (default: 7)
- `--region`: AWS region (default: uses default region)

### Output - Two Parts

**PART 1: Actual Costs (Cost Explorer)**
- Real billing data grouped by usage type (compute, requests, etc.)
- Daily breakdown of actual Lambda costs
- **This is the real cost from AWS billing**

**PART 2: Per-Function Estimate (CloudWatch) ⚠️ ESTIMATE ONLY**
- **Estimated** compute costs for each Lambda function
- Based on CloudWatch metrics: invocations, duration, memory
- Shows real metrics: invocation count, duration (seconds), memory
- **Note: This is an ESTIMATE** - does not include:
  - Provisioned Concurrency costs
  - Data Transfer costs
  - Other AWS charges

 <img width="725" height="381" alt="Screenshot 2025-12-07 at 18 02 21" src="https://github.com/user-attachments/assets/ae2b091d-98c6-429a-a058-f4197dfc8ed2" />

<img width="842" height="307" alt="Screenshot 2025-12-07 at 18 02 40" src="https://github.com/user-attachments/assets/c3f4b7d4-3f48-40fd-ade0-2e3757612ed8" />



### How It Works

1. **Part 1** fetches actual costs from Cost Explorer API (real billing data)
2. **Part 2** calculates estimated costs per function using:
   - CloudWatch `Invocations` metric (real invocation count)
   - CloudWatch `Duration` metric (real execution time in milliseconds)
   - Function memory configuration
   - Pricing: $0.0000166667 per GB-second (x86) or $0.0000133334 (ARM)
   - Request cost: $0.20 per 1M requests

### Important Notes

- **Part 2 costs are ESTIMATES** based on CloudWatch metrics
- Actual billing may differ due to Provisioned Concurrency, data transfer, etc.
- The difference between Part 1 and Part 2 shows unaccounted costs
- Metrics show real usage data (invocations, duration) even if cost is estimated

## Script: ecs_task_autoscaler.py

Automatically scales ECS tasks based on RabbitMQ queue size. Designed to be integrated into your own system (Celery, cron, etc.).

### Usage

```bash
# Run once (standalone)
python ecs_task_autoscaler.py

# Dry run mode (no actual scaling)
python ecs_task_autoscaler.py --dry-run
```

### Integration

You can integrate this into your own system by calling the `autoscale_ecs_workers()` function:

```python
from ecs_task_autoscaler import autoscale_ecs_workers

# Call in your scheduler (Celery Beat, cron, etc.)
result = autoscale_ecs_workers()
print(result)
```

### Environment Variables

- `MIN_WORKERS`: Minimum number of workers (default: 1)
- `MAX_WORKERS`: Maximum number of workers (default: 20)
- `TASKS_PER_WORKER`: Tasks per worker for scaling calculation (default: 200)
- `SCALE_DOWN_DELAY`: Delay before scaling down in seconds (default: 900 = 15 min)
- `RABBITMQ_HOST`: RabbitMQ host (default: rabbitmq)
- `RABBITMQ_MANAGEMENT_PORT`: RabbitMQ management port (default: 80)
- `RABBITMQ_DEFAULT_USER`: RabbitMQ username (default: guest)
- `RABBITMQ_DEFAULT_PASS`: RabbitMQ password (default: guest)
- `RABBITMQ_QUEUE_NAME`: Queue name to monitor (default: celery)
- `RABBITMQ_VHOST`: Virtual host, URL encoded (default: %2F which is /)
- `ECS_CLUSTER_NAME`: ECS cluster name (default: my-ecs-cluster) **REQUIRED**
- `ECS_WORKER_SERVICE`: ECS service name to scale (default: my-worker-service) **REQUIRED**
- `AWS_REGION`: AWS region (default: us-east-1)
- `REDIS_HOST`: Redis host for scale-down delay tracking (default: localhost)
- `REDIS_PORT`: Redis port (default: 6379)
- `REDIS_DB`: Redis database number (default: 1)
- `REDIS_PASSWORD`: Redis password (optional)
- `DRY_RUN`: Set to 'true' for dry run mode (default: false)

### How It Works

1. Checks RabbitMQ queue size (`messages_ready`)
2. Calculates needed workers: `ceil(queue_size / TASKS_PER_WORKER)`
3. **Scale Up**: Immediate scaling when queue size increases
4. **Scale Down**: Delays scaling down by `SCALE_DOWN_DELAY` seconds (prevents flapping)
5. Uses Redis to track scale-down timer state
6. Updates ECS service `desiredCount`

### Scaling Logic

- **Calculation**: `workers = ceil(queue_size / TASKS_PER_WORKER)`
- **Special case**: If queue >= 100 tasks, scale to at least 2 workers
- **Scale up**: Immediate (no delay)
- **Scale down**: Requires delay period (default 15 minutes) to prevent rapid scaling

### Scaling Examples

Based on default values (MIN_WORKERS=1, MAX_WORKERS=20, TASKS_PER_WORKER=200):

| Queue Size | Workers | Notes |
|------------|---------|-------|
| 0-99 | 1 | Minimum workers |
| 100-199 | 2 | Special case: min 2 workers when queue >= 100 |
| 200-399 | 2 | 200 tasks per worker |
| 400-599 | 3 | ceil(400/200) = 2, ceil(599/200) = 3 |
| 600-799 | 3-4 | Based on exact queue size |
| 800-999 | 4-5 | Based on exact queue size |
| 2000+ | 10+ | Up to MAX_WORKERS (20) |

**Examples:**
- Queue size 150 → 2 workers (special case)
- Queue size 350 → 2 workers (ceil(350/200) = 2)
- Queue size 450 → 3 workers (ceil(450/200) = 3)
- Queue size 5000 → 20 workers (MAX_WORKERS limit)

### Return Value

Returns a dictionary with action taken:
```python
{
    'action': 'scale_up' | 'scale_down' | 'no_change' | 'scale_down_delayed' | 'scale_down_waiting',
    'workers': int,  # Current worker count
    'queue': int,    # Queue size
    # ... other fields depending on action
}
```

## Troubleshooting

### ECS Cost Analyzer
- **"Error fetching data"**: Check AWS credentials and IAM permissions
- **"No data found"**: Verify tags are active in Cost Explorer preferences
- Tags may take a few hours to appear after enabling in Cost Explorer

### EC2 Cost Analyzer
- **"No Name Tag"**: The script looks for the 'Name' tag by default. Ensure your instances are tagged and 'Name' is enabled as a Cost Allocation Tag in billing console.
- **"No data found"**: Check permissions or credentials. Note that this script filters for EC2 services specifically.

### Lambda Cost Analyzer
- **"No Lambda functions found"**: Check region setting or AWS credentials
- **CloudWatch metrics not available**: Ensure functions have been invoked in the selected period
- **Zero costs shown**: Functions might not have been used, or costs are below $0.0001 threshold
- **Region errors**: Specify `--region` if functions are in multiple regions

### ECS Task Autoscaler
- **"RabbitMQ API error"**: Check RabbitMQ host, port, and credentials
- **"ECS API error"**: Verify AWS credentials, region, cluster, and service names
- **"Redis connection error"**: Redis is optional (only for scale-down delay), check connection if needed
- **No scaling happening**: Check MIN_WORKERS and MAX_WORKERS limits
- **Scale-down not working**: Verify Redis connection and SCALE_DOWN_DELAY setting

