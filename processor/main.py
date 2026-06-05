import faust
from datetime import timedelta
from common.config import settings

# Wait: Faust SASL config can be tricky, but we can set broker credentials
broker_url = settings.KAFKA_BOOTSTRAP_SERVERS
if settings.KAFKA_SASL_ENABLED:
    # faust-streaming uses aiokafka underneath, broker format for SASL:
    # Not purely in URL. We pass it via broker_credentials.
    import ssl
    ssl_context = ssl.create_default_context()
    # For local dev we might not have actual SSL certs, so we'd disable verification if needed
    # but the prompt requires SCRAM-SHA-512.
    broker_credentials = faust.SASLCredentials(
        username=settings.KAFKA_SASL_USERNAME,
        password=settings.KAFKA_SASL_PASSWORD,
        mechanism=settings.KAFKA_SASL_MECHANISM,
        protocol=settings.KAFKA_SECURITY_PROTOCOL.lower() # e.g. "sasl_plaintext"
    )
else:
    broker_credentials = None

app = faust.App(
    'drift-processor',
    broker=f"kafka://{broker_url}",
    broker_credentials=broker_credentials,
    store='rocksdb://',
    topic_partitions=3,
    autodiscover=['processor.agents']
)

def main() -> None:
    app.main()

if __name__ == '__main__':
    main()
