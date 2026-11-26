"""Kafka topic names. Each environment runs its own broker, so names carry no prefix."""

TOPIC_EDITS = "wiki.edits"  # key wiki:title, producer ingestor, consumers detector and api
TOPIC_REVERTS = "wiki.reverts"  # key wiki:title, producer detector, consumer api
TOPIC_ALERTS = "wiki.alerts"  # key alert id, producer detector, consumer api

ALL_TOPICS = {TOPIC_EDITS: 6, TOPIC_REVERTS: 3, TOPIC_ALERTS: 1}  # topic -> partitions
