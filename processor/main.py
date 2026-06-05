import sys
import os
import ssl

# Path-patch the root directory so autodiscovery finds sibling modules cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faust
from datetime import timedelta
from common.config import settings

broker_url = settings.KAFKA_BOOTSTRAP_SERVERS

# Determine if SSL is needed based on the security protocol
is_ssl = "SSL" in settings.KAFKA_SECURITY_PROTOCOL.upper()

# Build the broker URL with the correct scheme:
#   kafka://   -> plaintext
#   kafka+ssl:// -> encrypted (SASL_SSL / SSL)
app_options = {
    'id': 'drift-processor',
    'broker': f"kafka+ssl://{broker_url}" if is_ssl else f"kafka://{broker_url}",
    'store': 'rocksdb://',
    'datadir': '/app/rocksdb_data',
    'topic_partitions': 3,
    'autodiscover': ['processor.agents']
}

if settings.KAFKA_SASL_ENABLED:
    # Prepare SASL credentials
    sasl_kwargs = {
        'username': settings.KAFKA_SASL_USERNAME,
        'password': settings.KAFKA_SASL_PASSWORD,
        'mechanism': settings.KAFKA_SASL_MECHANISM
    }
    
    # When SSL is required, attach the SSL context directly to the credentials
    if is_ssl:
        context = ssl.create_default_context()
        context.check_hostname = False   # Disable hostname verification (adjust for production)
        context.verify_mode = ssl.CERT_NONE   # Disable certificate verification (adjust for production)
        sasl_kwargs['ssl_context'] = context

    app_options['broker_credentials'] = faust.SASLCredentials(**sasl_kwargs)

# Initialize the Faust App with the unified configuration
app = faust.App(**app_options)

def main() -> None:
    app.main()

if __name__ == '__main__':
    main()
