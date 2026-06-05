import sys
import os
import ssl

# Path-patch the root directory so autodiscovery finds sibling modules cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faust
from datetime import timedelta
from common.config import settings

broker_url = settings.KAFKA_BOOTSTRAP_SERVERS

# 1. Determine if SSL is needed, but DO NOT change the broker scheme
is_ssl = "SSL" in settings.KAFKA_SECURITY_PROTOCOL.upper()

# Setup base application options
app_options = {
    'id': 'drift-processor',
    # ALWAYS use 'kafka://', Faust will handle SSL via the credentials object
    'broker': f"kafka://{broker_url}", 
    'store': 'rocksdb://',
    'datadir': '/app/rocksdb_data',
    'topic_partitions': 3,
    'autodiscover': ['processor.agents']
}

if settings.KAFKA_SASL_ENABLED:
    # 2. Build the kwargs for SASLCredentials
    sasl_kwargs = {
        'username': settings.KAFKA_SASL_USERNAME,
        'password': settings.KAFKA_SASL_PASSWORD,
        'mechanism': settings.KAFKA_SASL_MECHANISM
    }
    
    # 3. If SSL is required, create the context and attach it directly
    if is_ssl:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Inject SSL directly into SASLCredentials
        sasl_kwargs['ssl_context'] = context

    # Unpack the kwargs into the Faust credentials object
    app_options['broker_credentials'] = faust.SASLCredentials(**sasl_kwargs)

# Initialize the Faust App with our unified configuration bundle
app = faust.App(**app_options)

def main() -> None:
    app.main()

if __name__ == '__main__':
    main()
