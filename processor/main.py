import sys
import os
import ssl

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faust
from datetime import timedelta
from common.config import settings

broker_url = settings.KAFKA_BOOTSTRAP_SERVERS

# Determine if SSL is needed (but do NOT change the broker scheme)
is_ssl = "SSL" in settings.KAFKA_SECURITY_PROTOCOL.upper()

app_options = {
    'id': 'drift-processor',
    # ALWAYS use 'kafka://' – Faust will handle SSL via the credentials object
    'broker': f"kafka://{broker_url}",
    'store': 'rocksdb://',
    'datadir': '/app/rocksdb_data',
    'topic_partitions': 3,
    'autodiscover': ['processor.agents']
}

if settings.KAFKA_SASL_ENABLED:
    sasl_kwargs = {
        'username': settings.KAFKA_SASL_USERNAME,
        'password': settings.KAFKA_SASL_PASSWORD,
        'mechanism': settings.KAFKA_SASL_MECHANISM
    }
    
    # Attach SSL context directly to SASLCredentials when SSL is required
    if is_ssl:
        context = ssl.create_default_context()
        context.check_hostname = False   # adjust for production
        context.verify_mode = ssl.CERT_NONE
        sasl_kwargs['ssl_context'] = context

    app_options['broker_credentials'] = faust.SASLCredentials(**sasl_kwargs)

app = faust.App(**app_options)

def main() -> None:
    app.main()

if __name__ == '__main__':
    main()
