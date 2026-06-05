import sys
import os
import ssl
# Path-patch the root directory so autodiscovery finds sibling modules cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faust
from datetime import timedelta
from common.config import settings

broker_url = settings.KAFKA_BOOTSTRAP_SERVERS
ssl_context = None

if settings.KAFKA_SASL_ENABLED:
    broker_credentials = faust.SASLCredentials(
        username=settings.KAFKA_SASL_USERNAME,
        password=settings.KAFKA_SASL_PASSWORD,
        mechanism=settings.KAFKA_SASL_MECHANISM
    )
    
    if "SSL" in settings.KAFKA_SECURITY_PROTOCOL:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
else:
    broker_credentials = None

app = faust.App(
    'drift-processor',
    broker=f"kafka://{broker_url}",
    broker_credentials=broker_credentials,
    ssl_context=ssl_context,  # Passed directly to App so SASL layer inherits encryption
    store='rocksdb://',
    datadir='/app/rocksdb_data',
    topic_partitions=3,
    autodiscover=['processor.agents']
)

def main() -> None:
    app.main()

if __name__ == '__main__':
    main()
