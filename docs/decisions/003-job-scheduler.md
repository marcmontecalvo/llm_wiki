# ADR 003: Job Scheduler Implementation

**Status**: Accepted
**Date**: 2026-04-13
**Deciders**: Implementation Team

## Context

The wiki daemon needs to execute recurring maintenance tasks reliably:
- Poll inbox for new files
- Update the search index
- Run cleanup/archival jobs
- Perform health checks
- Generate reports

Requirements:
- Interval-based scheduling (run every N seconds)
- Graceful error handling (job failures shouldn't crash daemon)
- Configurable intervals via daemon.yaml
- Support for enabling/disabling jobs
- Clean startup and shutdown
- No distributed coordination needed (single-node operation)

## Decision

We will use **APScheduler (Advanced Python Scheduler)** with a `BackgroundScheduler` for job execution.

### Architecture

**JobScheduler class** wraps APScheduler and provides:
- `add_job()`: Register a job with interval and enable/disable flag
- `remove_job()`: Unregister a job
- `start()`: Start the scheduler
- `shutdown()`: Stop scheduler (with option to wait for running jobs)
- `get_jobs()`: List registered jobs
- `get_job_info()`: Get details about a job

### Key Design Choices

**BackgroundScheduler**:
- Runs in a background thread (not blocking main thread)
- Simple threading model for single-node daemon
- No need for AsyncIO or multiprocessing complexity

**IntervalTrigger**:
- Simple "run every N seconds" model
- Matches our configuration (all intervals in daemon.yaml are seconds-based)
- More predictable than cron syntax for maintenance tasks

**Job Safety Features**:
- `misfire_grace_time=60`: Allow 60s grace if execution is delayed
- `coalesce=True`: Combine multiple missed executions into one (prevents backlog)
- `max_instances=1`: Prevent concurrent executions of same job (avoid race conditions)

**Error Isolation**:
- Job exceptions are caught by APScheduler
- Logged but don't crash the scheduler
- Scheduler continues running other jobs

### Configuration Integration

Jobs load their intervals from `daemon.yaml`:
```yaml
daemon:
  inbox_poll_seconds: 30
  index_update_seconds: 300
```

The scheduler is initialized with DaemonConfig and jobs register themselves with their configured intervals.

## Rationale

### Why APScheduler?

**Mature and stable**:
- 10+ years of development
- Wide adoption in Python ecosystem
- Well-documented and maintained

**Feature-rich**:
- Multiple trigger types (interval, cron, date)
- Job persistence (for future use)
- Graceful shutdown support
- Misfire handling

**Simple API**:
- Easy to use and test
- Minimal boilerplate
- Good error messages

**No external dependencies**:
- Pure Python (no Redis, RabbitMQ, database required)
- Suitable for single-node operation
- Low operational complexity

### Why Not Other Approaches?

**Celery**:
- ❌ Too heavy (requires message broker like Redis/RabbitMQ)
- ❌ Designed for distributed task queues (overkill)
- ❌ More complex setup and configuration
- ✅ Would enable distributed workers (future consideration)

**Built-in threading.Timer**:
- ❌ No graceful shutdown
- ❌ No misfire handling
- ❌ Must manually implement scheduling logic
- ❌ No job persistence

**Asyncio event loop**:
- ❌ Requires async/await everywhere
- ❌ More complex error handling
- ❌ Harder to integrate with synchronous code
- ✅ Better for I/O-bound tasks (but our tasks are mostly CPU/I/O mix)

**Cron + subprocess**:
- ❌ External dependency (system cron)
- ❌ Harder to test
- ❌ No programmatic control
- ❌ Requires system permissions

### Design Choices

**BackgroundScheduler vs AsyncIOScheduler**:
- BackgroundScheduler is simpler (no async/await)
- Our jobs are mostly I/O (file operations, API calls)
- Thread-based is sufficient for our scale
- Future: Could migrate to AsyncIOScheduler if needed

**Interval-based vs Cron**:
- Intervals are simpler and more predictable
- Our config uses seconds (inbox_poll_seconds, etc.)
- Cron syntax adds complexity without clear benefit
- Future: Could add cron support if user-facing scheduling needed

**Single instance per job**:
- Prevents race conditions (e.g., two inbox polls running simultaneously)
- Simplifies job logic (no need for locks)
- If a job is slow, next execution waits
- Trade-off: Long-running jobs could delay next execution

**Misfire handling**:
- `coalesce=True` prevents backlog buildup
- If daemon is paused, don't run 100 missed executions
- Run once and continue with normal schedule
- Trade-off: May miss some work, but prevents thundering herd

## Consequences

### Positive
- ✅ Reliable job scheduling with battle-tested library
- ✅ Graceful error handling (job failures don't crash daemon)
- ✅ Easy to test (can add jobs with short intervals)
- ✅ Clean shutdown (wait for jobs to complete)
- ✅ Low operational complexity (no external services)

### Negative
- ❌ Thread-based may have GIL contention (acceptable for our workload)
- ❌ No built-in distributed scheduling (fine for single-node)
- ❌ Job state not persisted (jobs lost on restart - acceptable for now)

### Neutral
- ⚠️ Adds dependency on APScheduler (well-maintained, stable)
- ⚠️ Threading model (could migrate to async later if needed)

## Implementation Notes

### Job Registration Pattern

```python
scheduler = JobScheduler(daemon_config)

# Add job with parameters
scheduler.add_job(
    func=poll_inbox,
    job_name="inbox_poll",
    interval_seconds=config.inbox_poll_seconds,
    enabled=True,  # Can disable via config
)

# Start scheduler
scheduler.start()

# Shutdown gracefully
scheduler.shutdown(wait=True)
```

### Error Handling

Jobs should handle their own errors and log them. The scheduler will catch uncaught exceptions and log them, but jobs should clean up their own resources:

```python
def my_job():
    try:
        # Do work
        process_inbox()
    except Exception as e:
        logger.error(f"Job failed: {e}")
        # Clean up resources
        # Don't re-raise (scheduler will log)
```

### Testing Strategy

- Unit tests use very short intervals (0.1s) to test execution
- Mock time for testing scheduling logic
- Use `wait=True` on shutdown to ensure clean test teardown
- Test error scenarios (job failures, duplicate registration)

## Future Enhancements

### Job Persistence
APScheduler supports job stores (database, Redis) to persist job state across restarts. This would allow:
- Resume jobs after daemon restart
- Track job execution history
- Implement retry logic

### Async Migration
If we move to AsyncIO for better I/O performance:
- Replace `BackgroundScheduler` with `AsyncIOScheduler`
- Convert jobs to async functions
- Use `aiofiles` for file I/O

### Distributed Scheduling
If we need multi-node coordination:
- Migrate to Celery + Redis/RabbitMQ
- Or use APScheduler + Redis job store with leader election

### Monitoring
- Expose job metrics (execution count, failures, duration)
- Integrate with Prometheus or similar
- Add health check endpoint

## References

- APScheduler documentation: https://apscheduler.readthedocs.io/
- APScheduler GitHub: https://github.com/agronholm/apscheduler
- Python threading documentation: https://docs.python.org/3/library/threading.html
