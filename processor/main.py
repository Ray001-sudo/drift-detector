import sys
import os
import ssl
import asyncio
from aiokafka.admin import AIOKafkaAdminClient, NewTopic

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


async def pre_create_leader_topic():
    """Create the Faust leader topic if it doesn't exist, to avoid connection errors."""
    config = {
        "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "request_timeout_ms": 10000,
    }
    if settings.KAFKA_SASL_ENABLED:
        config.update({
            "security_protocol": settings.KAFKA_SECURITY_PROTOCOL,
            "sasl_mechanism": settings.KAFKA_SASL_MECHANISM,
            "sasl_plain_username": settings.KAFKA_SASL_USERNAME,
            "sasl_plain_password": settings.KAFKA_SASL_PASSWORD,
        })
        if is_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            config["ssl_context"] = ctx

    admin = AIOKafkaAdminClient(**config)
    await admin.start()
    try:
        topic = NewTopic(
            name="drift-processor-__assignor-__leader",
            num_partitions=1,
            replication_factor=3,          # adjust to your Aiven cluster setting
        )
        await admin.create_topics([topic])
        print("Pre-created leader topic successfully.")
    except Exception as e:
        # Topic may already exist; that's fine
        print(f"Leader topic creation note: {e}")
    finally:
        await admin.close()


def main() -> None:
    asyncio.run(pre_create_leader_topic())
    app.main()


if __name__ == '__main__':
    main()
