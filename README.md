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
    "Action": ["ce:GetCostAndUsage"],
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


## Troubleshooting

- **"Error fetching data"**: Check AWS credentials and IAM permissions
- **"No data found"**: Verify tags are active in Cost Explorer preferences
- Tags may take a few hours to appear after enabling in Cost Explorer

