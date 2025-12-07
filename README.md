# AWS Tools

Practical AWS scripts built for task automation, debugging, and cloud resource management.

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

## Troubleshooting

### ECS Cost Analyzer
- **"Error fetching data"**: Check AWS credentials and IAM permissions
- **"No data found"**: Verify tags are active in Cost Explorer preferences
- Tags may take a few hours to appear after enabling in Cost Explorer

### Lambda Cost Analyzer
- **"No Lambda functions found"**: Check region setting or AWS credentials
- **CloudWatch metrics not available**: Ensure functions have been invoked in the selected period
- **Zero costs shown**: Functions might not have been used, or costs are below $0.0001 threshold
- **Region errors**: Specify `--region` if functions are in multiple regions

