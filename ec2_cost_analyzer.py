import argparse
import boto3
from datetime import datetime, timedelta
from tabulate import tabulate

def get_cost_and_usage(days, tag_key='Name'):
    """
    Fetch cost and usage data for EC2 services.
    Filters for specific EC2 services and groups by a Tag (default: Name) and Usage Type.
    """
    client = boto3.client('ce')
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Format dates as YYYY-MM-DD
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    print(f"Fetching EC2 cost data from {start_str} to {end_str}...")
    print(f"Grouping by Tag: '{tag_key}' and Usage Type")

    # Define the filter for EC2 services
    # We include 'Amazon Elastic Compute Cloud - Compute' and 'EC2 - Other'
    search_filter = {
        'Dimensions': {
            'Key': 'SERVICE',
            'Values': [
                'Amazon Elastic Compute Cloud - Compute',
                'EC2 - Other'
            ]
        }
    }

    # Group by the specified Tag and Usage Type
    # Note: Cost Explorer allows max 2 grouping dimensions.
    group_by = [
        {'Type': 'TAG', 'Key': tag_key},
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

def process_results(results, tag_key='Name'):
    """
    Process Cost Explorer results into a flat list of rows.
    Row format: [Date, Tag Value, Usage Type, Cost]
    """
    processed_rows = []
    
    for day_result in results:
        date = day_result['TimePeriod']['Start']
        groups = day_result.get('Groups', [])
        
        for group in groups:
            keys = group['Keys']
            # Keys are [TagValue, UsageType] because of our GroupBy order
            tag_value_raw = keys[0]
            usage_type = keys[1]
            
            # Handle missing tags or empty values
            # The tag key in the response might be 'tag_key$' (empty) if missing
            if tag_value_raw.startswith(f"{tag_key}$"):
                tag_value = tag_value_raw.split('$')[1]
                if not tag_value:
                    tag_value = f"No {tag_key} Tag"
            else:
                tag_value = tag_value_raw

            amount = float(group['Metrics']['UnblendedCost']['Amount'])
            
            # Filter out effectively zero costs
            if amount > 0.0001:
                processed_rows.append([date, tag_value, usage_type, amount])

    return processed_rows

def main():
    parser = argparse.ArgumentParser(description='EC2 Cost Analyzer')
    parser.add_argument('--days', type=int, default=7, help='Number of days to look back (default: 7)')
    # Allow user to specify a different tag if they use something other than Name for grouping
    parser.add_argument('--tag', type=str, default='Name', help="Cost Allocation Tag to group by (default: 'Name')")
    
    args = parser.parse_args()
    
    results = get_cost_and_usage(args.days, args.tag)
    
    if not results:
        print("No data found or error occurred.")
        return

    table_data = process_results(results, args.tag)
    
    if not table_data:
        print("No cost data found > $0.0001 for the specified period.")
        return

    # Sort by Date (descending), then Tag Value, then Cost (descending)
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
            # Format: Date, Tag Value, Usage Type, Cost
            flushed.append([r[0], r[1], r[2], f"${r[3]:.4f}"])
        # Add daily total
        flushed.append([date, "DAILY TOTAL", "", f"${total:.4f}"])
        return flushed

    for row in table_data:
        # row is [Date, TagValue, UsageType, Cost]
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
    
    print(f"\nEC2 Cost Report for last {args.days} days")
    print(f"Services: 'Amazon Elastic Compute Cloud - Compute', 'EC2 - Other'")
    print(f"Grouping by Tag: {args.tag}")
    print("-" * 80)
    
    headers = ['Date', f'Tag: {args.tag}', 'Usage Type', 'Cost']
    print(tabulate(formatted_table, headers=headers, tablefmt='grid'))
    print(f"\nTotal Cost (All Days): ${total_cost:.4f}")
    print("-" * 80)
    print(f"Note: 'No {args.tag} Tag' means costs were incurred but the '{args.tag}' tag was missing.")

if __name__ == '__main__':
    main()
