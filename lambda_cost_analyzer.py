import argparse
import boto3
from datetime import datetime, timedelta
from tabulate import tabulate
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# Lambda pricing by architecture (most regions, adjust if needed)
# x86_64 pricing
PRICE_PER_GB_SECOND_X86 = 0.0000166667
# arm64 pricing (20% cheaper)
PRICE_PER_GB_SECOND_ARM = 0.0000133334
PRICE_PER_REQUEST = 0.0000002  # Same for both architectures

def get_price_per_gb_second(architecture):
    """Get pricing based on architecture."""
    return PRICE_PER_GB_SECOND_ARM if architecture == 'arm64' else PRICE_PER_GB_SECOND_X86

def get_lambda_costs_from_cost_explorer(days):
    """Get actual Lambda costs from Cost Explorer grouped by Usage Type."""
    client = boto3.client('ce')
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    print(f"Fetching actual costs from Cost Explorer ({start_str} to {end_str})...")
    
    search_filter = {
        'Dimensions': {
            'Key': 'SERVICE',
            'Values': ['AWS Lambda']
        }
    }
    
    group_by = [
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
        print(f"Error fetching from Cost Explorer: {e}")
        return []
    
    return response.get('ResultsByTime', [])

def get_all_lambda_functions(lambda_client):
    """Get all Lambda functions with their config."""
    functions = []
    paginator = lambda_client.get_paginator('list_functions')
    
    for page in paginator.paginate():
        for func in page['Functions']:
            functions.append({
                'name': func['FunctionName'],
                'memory': func['MemorySize'],
                'architecture': func.get('Architectures', ['x86_64'])[0]
            })
    
    return functions

def get_function_metrics_for_day(cw_client, function_name, date):
    """Get Duration and Invocations metrics for a function on a specific day."""
    start_time = datetime.strptime(date, '%Y-%m-%d')
    end_time = start_time + timedelta(days=1)
    
    duration_ms = 0
    invocations = 0
    
    try:
        duration_res = cw_client.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='Duration',
            Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,
            Statistics=['Sum']
        )
        
        if duration_res.get('Datapoints'):
            duration_ms = duration_res['Datapoints'][0]['Sum']
    except Exception as e:
        # Silently continue if metrics not available
        pass
    
    try:
        invocations_res = cw_client.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='Invocations',
            Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,
            Statistics=['Sum']
        )
        
        if invocations_res.get('Datapoints'):
            invocations = invocations_res['Datapoints'][0]['Sum']
    except Exception as e:
        # Silently continue if metrics not available
        pass
    
    return duration_ms, invocations

def process_function_for_day(args):
    """Process a single function for a single day."""
    region, func, date = args
    
    # Create client per thread (boto3 clients are not thread-safe)
    cw_client = boto3.client('cloudwatch', region_name=region)
    
    try:
        duration_ms, invocations = get_function_metrics_for_day(cw_client, func['name'], date)
        
        if duration_ms > 0 or invocations > 0:
            # Convert memory from MB to GB, duration from ms to seconds
            gb_seconds = (duration_ms / 1000.0) * (func['memory'] / 1024.0)
            price_per_gb_sec = get_price_per_gb_second(func['architecture'])
            compute_cost = gb_seconds * price_per_gb_sec
            request_cost = invocations * PRICE_PER_REQUEST
            total_cost = compute_cost + request_cost
            
            if total_cost > 0.0001:
                return {
                    'date': date,
                    'function': func['name'],
                    'memory': func['memory'],
                    'architecture': func['architecture'],
                    'invocations': int(invocations),
                    'duration_sec': round(duration_ms / 1000.0, 2),
                    'compute_cost': compute_cost,
                    'request_cost': request_cost,
                    'total_cost': total_cost
                }
    except Exception as e:
        # Log error but don't crash
        print(f"  Warning: Error processing {func['name']} for {date}: {e}")
    
    return None

def process_cost_explorer_results(results):
    """Process Cost Explorer results into daily usage type breakdown."""
    daily_data = defaultdict(lambda: defaultdict(float))
    
    for day_result in results:
        date = day_result['TimePeriod']['Start']
        groups = day_result.get('Groups', [])
        
        for group in groups:
            usage_type = group['Keys'][0]
            amount = float(group['Metrics']['UnblendedCost']['Amount'])
            
            if amount > 0.0001:
                daily_data[date][usage_type] = amount
    
    return daily_data

def main():
    parser = argparse.ArgumentParser(description='Lambda Cost Analyzer (Comprehensive)')
    parser.add_argument('--days', type=int, default=7, help='Number of days to look back (default: 7)')
    parser.add_argument('--region', type=str, default=None, help='AWS Region')
    
    args = parser.parse_args()
    
    # ===== PART 1: Cost Explorer - Actual Costs by Usage Type =====
    ce_results = get_lambda_costs_from_cost_explorer(args.days)
    daily_costs = process_cost_explorer_results(ce_results)
    
    if daily_costs:
        print("\n" + "=" * 100)
        print("PART 1: ACTUAL COSTS BY USAGE TYPE (from Cost Explorer)")
        print("=" * 100)
        
        usage_table = []
        grand_total = 0.0
        
        for date in sorted(daily_costs.keys(), reverse=True):
            daily_total = 0.0
            for usage_type, cost in sorted(daily_costs[date].items(), key=lambda x: -x[1]):
                usage_table.append([date, usage_type, f"${cost:.4f}"])
                daily_total += cost
            usage_table.append([date, "DAILY TOTAL", f"${daily_total:.4f}"])
            grand_total += daily_total
        
        print(tabulate(usage_table, headers=['Date', 'Usage Type', 'Cost'], tablefmt='grid'))
        print(f"\nTotal Lambda Cost: ${grand_total:.4f}")
    
    # ===== PART 2: CloudWatch - Per-Function Estimate =====
    print("\n" + "=" * 100)
    print("PART 2: PER-FUNCTION COMPUTE ESTIMATE (from CloudWatch)")
    print("=" * 100)
    print("Note: This estimates compute costs only. Provisioned Concurrency, Data Transfer, etc. are NOT per-function trackable.")
    
    if not args.region:
        # Try to get default region
        try:
            session = boto3.Session()
            args.region = session.region_name
            if not args.region:
                print("Error: No region specified and no default region found. Please use --region flag.")
                return
            print(f"Using default region: {args.region}")
        except Exception as e:
            print(f"Error: Could not determine region: {e}")
            return
    
    try:
        lambda_client = boto3.client('lambda', region_name=args.region)
    except Exception as e:
        print(f"Error creating Lambda client: {e}")
        return
    
    print(f"\nFetching Lambda functions from region: {args.region}...")
    try:
        functions = get_all_lambda_functions(lambda_client)
    except Exception as e:
        print(f"Error fetching Lambda functions: {e}")
        return
    
    if not functions:
        print("No Lambda functions found in this region.")
        return
    
    print(f"Found {len(functions)} Lambda functions.")
    
    # Generate date range (including today)
    end_date = datetime.now()
    dates = [(end_date - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(args.days)]
    dates.reverse()  # Oldest first
    
    print(f"Fetching CloudWatch metrics for {len(dates)} days...")
    
    # Pass region instead of client (will create per-thread)
    work_items = [(args.region, func, date) for func in functions for date in dates]
    
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_item = {executor.submit(process_function_for_day, item): item for item in work_items}
        for future in as_completed(future_to_item):
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                # Handle exceptions from thread execution
                print(f"  Warning: Thread execution error: {e}")
                continue
    
    if results:
        results.sort(key=lambda x: (x['date'], -x['total_cost']))
        
        formatted_table = []
        total_est = 0.0
        current_date = None
        daily_total = 0.0
        daily_rows = []
        
        def flush_day(date, rows, total):
            if not rows:
                return []
            flushed = []
            for r in rows:
                flushed.append([
                    r['date'], r['function'], f"{r['memory']} MB",
                    f"{r['invocations']:,}", f"{r['duration_sec']:,.2f}s",
                    f"${r['total_cost']:.4f}"
                ])
            flushed.append([date, "DAILY TOTAL", "", "", "", f"${total:.4f}"])
            return flushed
        
        for row in results:
            date = row['date']
            cost = row['total_cost']
            
            if current_date is not None and date != current_date:
                formatted_table.extend(flush_day(current_date, daily_rows, daily_total))
                daily_rows = []
                daily_total = 0.0
            
            current_date = date
            daily_rows.append(row)
            daily_total += cost
            total_est += cost
        
        if current_date:
            formatted_table.extend(flush_day(current_date, daily_rows, daily_total))
        
        headers = ['Date', 'Function', 'Memory', 'Invocations', 'Duration', 'Est. Cost']
        print(tabulate(formatted_table, headers=headers, tablefmt='grid'))
        print(f"\nTotal Estimated Compute Cost: ${total_est:.4f}")
    else:
        print("No CloudWatch metrics data found.")
    
    # Calculate totals for summary
    grand_total = 0.0
    if daily_costs:
        grand_total = sum(sum(costs.values()) for costs in daily_costs.values())
    
    total_est = sum(r['total_cost'] for r in results) if results else 0.0
    
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    
    if daily_costs:
        print(f"Actual Total Lambda Cost (Cost Explorer): ${grand_total:.4f}")
    
    if results:
        print(f"Estimated Compute Cost (CloudWatch):      ${total_est:.4f}")
        if daily_costs and grand_total > 0:
            diff = grand_total - total_est
            print(f"Difference (Provisioned, Transfer, etc.): ${diff:.4f}")
    
    if not daily_costs and not results:
        print("No cost data available from either source.")

if __name__ == '__main__':
    main()
