import sys
import os
import ssl

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faust
from common.config import settings

broker_url = settings.KAFKA_BOOTSTRAP_SERVERS

# 1. Build the SSL context with the bypass hacks
ctx = None
if settings.KAFKA_SASL_ENABLED and "SSL" in settings.KAFKA_SECURITY_PROTOCOL.upper():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

# 2. Build SASL Credentials with injected SSL context
broker_credentials = None
if settings.KAFKA_SASL_ENABLED:
    broker_credentials = faust.SASLCredentials(
        username=settings.KAFKA_SASL_USERNAME,
        password=settings.KAFKA_SASL_PASSWORD,
        mechanism=settings.KAFKA_SASL_MECHANISM or "PLAIN",
        ssl_context=ctx
    )

# 3. Initialize the Faust App
app = faust.App(
    'drift-processor',
    broker=f"kafka://{broker_url}",
    broker_credentials=broker_credentials,
    datadir='/app/rocksdb_data',
    topic_allow_declare=False,         # Crucial: prevents Aiven admin firewall drops
    topic_partitions=3,
    autodiscover=['processor.agents']
)

# 4. Final configuration overrides
app.conf.leader_election = False

def main() -> None:
    app.main()

if __name__ == '__main__':
    main()
