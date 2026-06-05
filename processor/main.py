import sys
import os
import ssl

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faust
from common.config import settings

broker_url = settings.KAFKA_BOOTSTRAP_SERVERS

is_ssl = "SSL" in settings.KAFKA_SECURITY_PROTOCOL.upper()

app_options = {
    'id': 'drift-processor',
    'broker': f"kafka://{broker_url}",
    'store': 'rocksdb://',
    'datadir': '/app/rocksdb_data',
    'topic_partitions': 3,
    'autodiscover': ['processor.agents'],
}

if settings.KAFKA_SASL_ENABLED:
    sasl_kwargs = {
        'username': settings.KAFKA_SASL_USERNAME,
        'password': settings.KAFKA_SASL_PASSWORD,
        'mechanism': settings.KAFKA_SASL_MECHANISM
    }
    if is_ssl:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        sasl_kwargs['ssl_context'] = context

    app_options['broker_credentials'] = faust.SASLCredentials(**sasl_kwargs)

app = faust.App(**app_options)

# Force leader election off – this must be set directly on the config object
app.conf.leader_election = False

def main() -> None:
    app.main()

if __name__ == '__main__':
    main()
