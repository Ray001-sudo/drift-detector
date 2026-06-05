import sys
import os
# Explicitly path-patch the root directory so autodiscovery finds sibling modules cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faust
from datetime import timedelta
from common.config import settings

broker_url = settings.KAFKA_BOOTSTRAP_SERVERS

if settings.KAFKA_SASL_ENABLED:
    # Use the correct SASL layout without the unexpected 'protocol' field
    broker_credentials = faust.SASLCredentials(
        username=settings.KAFKA_SASL_USERNAME,
        password=settings.KAFKA_SASL_PASSWORD,
        mechanism=settings.KAFKA_SASL_MECHANISM
    )
    # Changed from "kafka+ssl://" to "ssl://" so Faust maps to its native SSL transport driver
    broker_scheme = "ssl://"
else:
    broker_credentials = None
    broker_scheme = "kafka://"

app = faust.App(
    'drift-processor',
    broker=f"{broker_scheme}{broker_url}",
    broker_credentials=broker_credentials,
    store='rocksdb://',
    topic_partitions=3,
    autodiscover=['processor.agents']
)

def main() -> None:
    app.main()

if __name__ == '__main__':
    main()
