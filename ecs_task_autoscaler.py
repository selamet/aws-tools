"""
ECS Worker Autoscaler

Automatically scales ECS workers based on RabbitMQ queue size.
Originally designed as a Celery task, now converted to a standalone script
that can be integrated into any scheduling system (Celery Beat, cron, etc.).

Scaling Logic:
- Calculates needed workers: ceil(queue_size / TASKS_PER_WORKER)
- Scale up: Immediate (no delay)
- Scale down: Requires delay period (default 15 minutes) to prevent rapid scaling

Usage:
    # Standalone execution
    python ecs_task_autoscaler.py
    
    # Dry run mode
    python ecs_task_autoscaler.py --dry-run
    
    # Integration example (in your Celery Beat or cron job)
    from ecs_task_autoscaler import autoscale_ecs_workers
    result = autoscale_ecs_workers()
"""
import math
import time
import os
import requests
import boto3
import redis
import logging
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Scaling configuration
MIN_WORKERS = int(os.getenv('MIN_WORKERS', '1'))  # Minimum number of workers to maintain
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '20'))  # Maximum number of workers allowed
TASKS_PER_WORKER = int(os.getenv('TASKS_PER_WORKER', '200'))  # Tasks per worker for scaling calculation
SCALE_DOWN_DELAY = int(os.getenv('SCALE_DOWN_DELAY', '900'))  # Delay before scaling down (seconds, default 15 min)

# RabbitMQ configuration (for queue size monitoring)
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
RABBITMQ_MANAGEMENT_PORT = int(os.getenv('RABBITMQ_MANAGEMENT_PORT', '80'))
RABBITMQ_USER = os.getenv('RABBITMQ_DEFAULT_USER', 'guest')
RABBITMQ_PASS = os.getenv('RABBITMQ_DEFAULT_PASS', 'guest')
RABBITMQ_QUEUE_NAME = os.getenv('RABBITMQ_QUEUE_NAME', 'celery')  # Queue name to monitor
RABBITMQ_VHOST = os.getenv('RABBITMQ_VHOST', '%2F')  # Virtual host (default: /, URL encoded as %2F)

# ECS configuration
ECS_CLUSTER = os.getenv('ECS_CLUSTER_NAME', 'my-ecs-cluster')  # Change to your ECS cluster name
ECS_WORKER_SERVICE = os.getenv('ECS_WORKER_SERVICE', 'my-worker-service')  # Change to your ECS service name
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

# Redis configuration (optional, used for scale-down delay tracking)
# If Redis is unavailable, scale-down delay will not be enforced
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '1'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

# Dry run mode (for testing without actual scaling)
DRY_RUN = os.getenv('DRY_RUN', 'false').lower() == 'true'


def get_redis_client():
    """
    Create and return Redis client connection.
    
    Returns:
        redis.Redis: Redis client instance, or None if connection fails
        
    Note:
        Redis is optional. If unavailable, scale-down delay will not be enforced.
    """
    try:
        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True
        )
    except Exception as e:
        logger.error(f"Redis connection error: {e}")
        return None


def get_queue_size():
    """
    Get the number of pending tasks from RabbitMQ queue.
    
    Uses RabbitMQ Management API to query the queue size.
    
    Returns:
        int: Number of messages ready in the queue (0 on error)
    """
    try:
        # RabbitMQ Management API endpoint for queue info
        # VHOST is typically URL encoded: / becomes %2F
        url = f"http://{RABBITMQ_HOST}:{RABBITMQ_MANAGEMENT_PORT}/api/queues/{RABBITMQ_VHOST}/{RABBITMQ_QUEUE_NAME}"
        response = requests.get(url, auth=(RABBITMQ_USER, RABBITMQ_PASS), timeout=10)
        response.raise_for_status()
        return response.json().get('messages_ready', 0)
    except Exception as e:
        logger.error(f"RabbitMQ API error: {e}")
        return 0


def get_current_workers():
    """
    Get the current desired count of ECS workers.
    
    Returns:
        int: Current desired count of workers (returns MIN_WORKERS on error)
    """
    try:
        ecs = boto3.client('ecs', region_name=AWS_REGION)
        response = ecs.describe_services(cluster=ECS_CLUSTER, services=[ECS_WORKER_SERVICE])
        return response['services'][0]['desiredCount']
    except Exception as e:
        logger.error(f"ECS API error: {e}")
        return MIN_WORKERS


def scale_workers(count):
    """
    Scale ECS service to the specified number of workers.
    
    Args:
        count (int): Target number of workers
        
    Returns:
        bool: True if scaling succeeded (or dry run), False on error
        
    Note:
        In DRY_RUN mode, no actual scaling is performed, only logged.
    """
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would scale to {count} workers")
        return True

    try:
        ecs = boto3.client('ecs', region_name=AWS_REGION)
        ecs.update_service(cluster=ECS_CLUSTER, service=ECS_WORKER_SERVICE, desiredCount=count)
        logger.info(f"Scaled to {count} workers")
        return True
    except Exception as e:
        logger.error(f"ECS scaling failed: {e}")
        return False


def autoscale_ecs_workers():
    """
    Main autoscaling function. Scales ECS workers based on RabbitMQ queue size.
    
    Originally designed as a Celery task, now converted to a standalone function
    that can be called from any scheduling system (Celery Beat, cron, etc.).
    
    Scaling Logic:
    1. Get queue size from RabbitMQ
    2. Calculate needed workers: ceil(queue_size / TASKS_PER_WORKER)
    3. Special case: If queue >= 100, ensure at least 2 workers
    4. Scale up: Immediate (no delay)
    5. Scale down: Requires SCALE_DOWN_DELAY seconds to prevent rapid scaling
    
    Returns:
        dict: Dictionary containing:
            - action: 'no_change' | 'scale_up' | 'scale_down' | 'scale_down_delayed' | 
                     'scale_down_waiting' | 'scale_down_timer_reset'
            - workers: Current worker count
            - queue: Current queue size
            - Additional fields depending on action (from, to, target, remaining, etc.)
    """
    redis_client = get_redis_client()
    scale_down_key = "ecs_autoscaler:scale_down_time"

    # Get current state
    queue_size = get_queue_size()
    current = get_current_workers()

    # Calculate needed workers based on queue size
    # Special case: if queue has 100+ tasks, ensure at least 2 workers
    if queue_size >= 100:
        needed = max(2, min(math.ceil(queue_size / TASKS_PER_WORKER), MAX_WORKERS))
    else:
        needed = max(MIN_WORKERS, min(math.ceil(queue_size / TASKS_PER_WORKER), MAX_WORKERS))

    logger.info(f"Autoscaling: queue={queue_size}, current={current}, needed={needed}, min={MIN_WORKERS}, max={MAX_WORKERS}")

    # Case 1: No scaling needed
    if needed == current:
        # Clear any pending scale-down timer
        if redis_client:
            redis_client.delete(scale_down_key)
        result = {'action': 'no_change', 'workers': current, 'queue': queue_size}
        logger.info(f"No scaling needed: {result}")
        return result

    # Case 2: Scale up (immediate)
    elif needed > current:
        # Clear scale-down timer (we're scaling up)
        if redis_client:
            redis_client.delete(scale_down_key)
        scale_workers(needed)
        result = {'action': 'scale_up', 'from': current, 'to': needed, 'queue': queue_size}
        logger.info(f"Scaled up: {result}")
        return result

    # Case 3: Scale down (requires delay to prevent flapping)
    else:
        # If Redis is not available, scale down immediately (no delay)
        if not redis_client:
            logger.warning("Redis not available, scale-down delay not enforced")
            scale_workers(needed)
            return {'action': 'scale_down', 'from': current, 'to': needed, 'queue': queue_size, 'note': 'redis_unavailable'}

        # Check if scale-down timer is already set
        scale_down_time_str = redis_client.get(scale_down_key)

        # No timer set - start the delay period
        if not scale_down_time_str:
            current_time = time.time()
            redis_client.set(scale_down_key, str(current_time))
            logger.info(
                f"Scale-down timer started. Will scale down from {current} to {needed} after {SCALE_DOWN_DELAY}s if queue remains low.")
            return {'action': 'scale_down_delayed', 'workers': current, 'target': needed, 'queue': queue_size}

        # Timer exists - check if delay period has elapsed
        try:
            scale_down_time = float(scale_down_time_str)
            elapsed = time.time() - scale_down_time
        except (ValueError, TypeError) as e:
            # Invalid timer value - reset it
            logger.error(f"Invalid scale_down_time value: {scale_down_time_str}, error: {e}")
            current_time = time.time()
            redis_client.set(scale_down_key, str(current_time))
            return {'action': 'scale_down_timer_reset', 'workers': current, 'queue': queue_size}

        # Delay period has elapsed - execute scale down
        if elapsed >= SCALE_DOWN_DELAY:
            redis_client.delete(scale_down_key)
            scale_workers(needed)
            logger.info(f"Scale-down executed: {current} -> {needed} after {elapsed:.0f}s delay")
            return {'action': 'scale_down', 'from': current, 'to': needed, 'queue': queue_size}

        # Delay period not yet elapsed - keep waiting
        remaining = SCALE_DOWN_DELAY - elapsed
        logger.info(
            f"Scale-down waiting: {remaining:.0f}s remaining (elapsed: {elapsed:.0f}s). Target: {current} -> {needed}")

        return {
            'action': 'scale_down_waiting',
            'remaining': remaining,
            'from': current,
            'to': needed,
            'queue': queue_size
        }


def main():
    """
    Main entry point for standalone script execution.
    
    This function allows the autoscaler to be run directly from command line.
    For integration into scheduling systems, call autoscale_ecs_workers() directly.
    """
    parser = argparse.ArgumentParser(
        description='ECS Task Autoscaler - Scale ECS workers based on RabbitMQ queue size',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Normal execution
  python ecs_task_autoscaler.py
  
  # Dry run (no actual scaling)
  python ecs_task_autoscaler.py --dry-run
  
  # Integration example (in Celery Beat schedule)
  from ecs_task_autoscaler import autoscale_ecs_workers
  
  @app.task
  def run_autoscaler():
      return autoscale_ecs_workers()
        """
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode - shows what would be done without actually scaling'
    )
    args = parser.parse_args()
    
    global DRY_RUN
    if args.dry_run:
        DRY_RUN = True
        logger.info("Running in DRY RUN mode")
    
    # Execute autoscaling
    result = autoscale_ecs_workers()
    print(f"Result: {result}")


if __name__ == '__main__':
    main()
