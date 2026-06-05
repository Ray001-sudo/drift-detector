import sys
import os
import ssl
# Path-patch the root directory so autodiscovery finds sibling modules cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faust
from datetime import timedelta
from common.config import settings

broker_url = settings.KAFKA_BOOTSTRAP_SERVERS
extra_broker_params = {}

if settings.KAFKA_SASL_ENABLED:
    broker_credentials = faust.SASLCredentials(
        username=settings.KAFKA_SASL_USERNAME,
        password=settings.KAFKA_SASL_PASSWORD,
        mechanism=settings.KAFKA_SASL_MECHANISM
    )
    
    # Secure the context exactly how we did for aiokafka to bypass self-signed CA restrictions
    if "SSL" in settings.KAFKA_SECURITY_PROTOCOL:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Pass this context straight to Faust's underlying aiokafka producer/consumer drivers
        extra_broker_params["ssl_context"] = context
else:
    broker_credentials = None

app = faust.App(
    'drift-processor',
    broker=f"kafka://{broker_url}",  # Kept as standard kafka:// so transport scheme maps correctly
    broker_credentials=broker_credentials,
    broker_client_with_ssl=extra_broker_params,  # Injects our customized SSL context map
    store='rocksdb://',
    datadir='/app/rocksdb_data',  # Overrides default data directory to prevent Permission Errors
    topic_partitions=3,
    autodiscover=['processor.agents']
)

def main() -> None:
    app.main()

if __name__ == '__main__':
    main()
