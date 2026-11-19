"""Single separate scheduler worker started by Docker Compose.

The API is unaffected by HTTP stalls. Database state survives worker restarts.
Schedules are disabled until explicitly configured in the UI.
"""
import logging
import time
from .scheduling import tick

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)


def main():
    LOG.info("DataBridge worker starting; waiting for enabled scheduled jobs")
    while True:
        try:
            tick()
        except Exception:
            LOG.exception("Worker loop failed. Retrying poll in 5 seconds.")
        time.sleep(5)


if __name__ == "__main__":
    main()
