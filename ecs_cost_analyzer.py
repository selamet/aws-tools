import argparse
import boto3
from datetime import datetime, timedelta
from tabulate import tabulate
from collections import defaultdict

def get_cost_and_usage(days, cluster_name=None):
    client = boto3.client('ce')
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Format dates as YYYY-MM-DD
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    print(f"Fetching cost data from {start_str} to {end_str}...")

    # Define the filter
    # We want to capture costs related to ECS. 
    # A good starting point is to filter by the existence of the ECS Service Name tag.
    # If a cluster name is provided, we add that to the filter.
    
    filter_args = {
        'Tags': {
            'Key': 'aws:ecs:serviceName',
            'Values': [] # Empty list means "tag exists" (match anything) - wait, CE API requires specific values or "Key" existence check is different.
                         # Actually, 'Tags' filter usually requires Key and Values. 
                         # To match "Tag exists", we might need a different approach or just filter by Service 'Amazon Elastic Container Service' + others.
                         # However, the most accurate way for "ECS Service Cost" is the tag.
                         # Let's try to filter by the Service dimension first to be safe, then group by tags.
        }
    }
    
    # Better approach: Filter by Dimensions -> Service: ECS, EC2, Data Transfer
    # AND (Optional) Tag: aws:ecs:clusterName = <cluster_name>
    
    # We define the base filter for services we care about
    base_filter = {'Dimensions': {'Key': 'SERVICE', 'Values': ['Amazon Elastic Container Service', 'Amazon Elastic Compute Cloud - Compute', 'AWS Data Transfer']}}
    
    search_filter = base_filter

    if cluster_name:
        # If cluster is specified, we MUST filter by it.
        # Note: This assumes 'aws:ecs:clusterName' tag is active and populated.
        search_filter = {
            'And': [
                search_filter,
                {'Tags': {'Key': 'aws:ecs:clusterName', 'Values': [cluster_name]}}
            ]
        }

    # We want to group by Service Name (Tag) and Usage Type.
    # Cost Explorer allows max 2 grouping dimensions.
    group_by = [
        {'Type': 'TAG', 'Key': 'aws:ecs:serviceName'},
        {'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'}
    ]

    try:
        response = client.get_cost_and_usage(
            TimePeriod={'Start': start_str, 'End': end_str},
            Granularity='DAILY',
            Filter=search_filter,
            Metrics=['UnblendedCost'],
            GroupBy=group_by
        )
    except Exception as e:
        print(f"Error fetching data: {e}")
        return []

    return response.get('ResultsByTime', [])

def process_results(results):
    # List to hold rows: [Date, Service Name, Usage Type, Cost]
    processed_rows = []
    
    for day_result in results:
        date = day_result['TimePeriod']['Start']
        groups = day_result.get('Groups', [])
        
        for group in groups:
            keys = group['Keys']
            # Keys are [TagValue, UsageType] because of our GroupBy order
            service_tag = keys[0]
            usage_type = keys[1]
            
            # The tag value might be 'aws:ecs:serviceName$' (empty) if the tag is missing
            if service_tag.startswith('aws:ecs:serviceName$'):
                service_name = service_tag.split('$')[1]
                if not service_name:
                    service_name = "No Service Tag"
            else:
                service_name = service_tag

            amount = float(group['Metrics']['UnblendedCost']['Amount'])
            
            # Filter out effectively zero costs
            if amount > 0.0001:
                processed_rows.append([date, service_name, usage_type, amount])

    return processed_rows

def main():
    parser = argparse.ArgumentParser(description='ECS Cost Analyzer')
    parser.add_argument('--days', type=int, default=7, help='Number of days to look back (default: 7)')
    parser.add_argument('--cluster', type=str, help='Filter by ECS Cluster Name (requires aws:ecs:clusterName tag)')
    
    args = parser.parse_args()
    
    results = get_cost_and_usage(args.days, args.cluster)
    
    if not results:
        print("No data found or error occurred.")
        return

    table_data = process_results(results)
    
    # Sort by Date (descending), then Service Name, then Cost (descending)
    table_data.sort(key=lambda x: (x[0], x[1], x[3]), reverse=True)
    
    # Format cost for display and add daily totals
    formatted_table = []
    total_cost = 0.0
    
    # Group by Date to calculate daily totals
    current_date = None
    daily_total = 0.0
    daily_rows = []

    # Helper to flush daily rows
    def flush_day(date, rows, total):
        if not rows:
            return []
        # Add rows for the day
        flushed = []
        for r in rows:
            flushed.append([r[0], r[1], r[2], f"${r[3]:.4f}"])
        # Add daily total
        flushed.append([date, "DAILY TOTAL", "", f"${total:.4f}"])
        # Add separator row (empty) if needed, but tabulate handles grid well.
        # Maybe just a visual separator in the list isn't needed with 'grid' fmt, 
        # but the Total row itself acts as a separator.
        return flushed

    for row in table_data:
        # row is [Date, Service, UsageType, Cost]
        date = row[0]
        cost = row[3]
        
        if current_date is not None and date != current_date:
            # New day, flush previous day
            formatted_table.extend(flush_day(current_date, daily_rows, daily_total))
            daily_rows = []
            daily_total = 0.0
        
        current_date = date
        daily_rows.append(row)
        daily_total += cost
        total_cost += cost
    
    # Flush last day
    if current_date:
        formatted_table.extend(flush_day(current_date, daily_rows, daily_total))
    
    print(f"\nDaily Cost Report for last {args.days} days")
    if args.cluster:
        print(f"Cluster: {args.cluster}")
    print("-" * 80)
    
    print(tabulate(formatted_table, headers=['Date', 'Service Name', 'Usage Type', 'Cost'], tablefmt='grid'))
    print(f"\nTotal Cost (All Days): ${total_cost:.4f}")
    print("-" * 80)
    print("Note: 'No Service Tag' means costs were found but the 'aws:ecs:serviceName' tag was missing.")

if __name__ == '__main__':
    main()
