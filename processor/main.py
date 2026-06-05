import sys
import os
import ssl

# Path-patch the root directory so autodiscovery finds sibling modules cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faust
from datetime import timedelta
from common.config import settings

broker_url = settings.KAFKA_BOOTSTRAP_SERVERS

# 1. Initialize the Faust App cleanly without complex kwargs
app = faust.App(
    'drift-processor',
    broker=f"kafka://{broker_url}",
    store='rocksdb://',
    datadir='/app/rocksdb_data',
    topic_partitions=3,
    autodiscover=['processor.agents']
)

# 2. Directly mutate the configuration state to force SASL_SSL
if settings.KAFKA_SASL_ENABLED:
    app.conf.broker_credentials = faust.SASLCredentials(
        username=settings.KAFKA_SASL_USERNAME,
        password=settings.KAFKA_SASL_PASSWORD,
        mechanism=settings.KAFKA_SASL_MECHANISM
    )
    
    if "SSL" in settings.KAFKA_SECURITY_PROTOCOL:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # CRITICAL: Forcing the SSL context directly into the config state guarantees 
        # the underlying aiokafka driver reads it and applies the TLS wrapper.
        app.conf.ssl_context = ctx

def main() -> None:
    app.main()

if __name__ == '__main__':
    main()
