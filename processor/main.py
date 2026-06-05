import sys
import os
import ssl
# Path-patch the root directory so autodiscovery finds sibling modules cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faust
from datetime import timedelta
from common.config import settings

broker_url = settings.KAFKA_BOOTSTRAP_SERVERS

# Setup base application options
app_options = {
    'id': 'drift-processor',
    'broker': f"kafka://{broker_url}",
    'store': 'rocksdb://',
    'datadir': '/app/rocksdb_data',
    'topic_partitions': 3,
    'autodiscover': ['processor.agents']
}

if settings.KAFKA_SASL_ENABLED:
    broker_credentials = faust.SASLCredentials(
        username=settings.KAFKA_SASL_USERNAME,
        password=settings.KAFKA_SASL_PASSWORD,
        mechanism=settings.KAFKA_SASL_MECHANISM
    )
    app_options['broker_credentials'] = broker_credentials
    
    if "SSL" in settings.KAFKA_SECURITY_PROTOCOL:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # This is the secret sauce: explicitly override both consumer and producer parameters
        # inside Faust's underlying mapping parameters to lock SSL active.
        app_options['broker_client_with_ssl'] = {
            'ssl_context': context
        }

# Initialize the Faust App with our unified configuration bundle
app = faust.App(**app_options)

def main() -> None:
    app.main()

if __name__ == '__main__':
    main()
