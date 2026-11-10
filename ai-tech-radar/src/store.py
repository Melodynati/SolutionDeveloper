"""DynamoDB single-table access.

Item types (pk / sk):
  SEEN#<item id>      / SEEN              dedupe marker, TTL 30 days
  TECH#<tech name>    / H#YYYY-MM-DDTHH   hourly signal bucket (ADD), TTL 60 days
  REGISTRY            / <tech name>       known technologies + category + first_seen
"""
import os
import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

TABLE = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
DAY = 86400


def mark_seen(item_id):
    """True if the item is new (first time we see it)."""
    try:
        TABLE.put_item(
            Item={"pk": f"SEEN#{item_id}", "sk": "SEEN", "expires": int(time.time()) + 30 * DAY},
            ConditionExpression="attribute_not_exists(pk)",
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def add_signal(tech, hour_key, signal, source):
    TABLE.update_item(
        Key={"pk": f"TECH#{tech}", "sk": f"H#{hour_key}"},
        UpdateExpression="ADD #s :s, #c :one, #src :src SET expires = :exp",
        ExpressionAttributeNames={"#s": "signal", "#c": "mentions", "#src": "sources"},
        ExpressionAttributeValues={
            ":s": Decimal(str(round(signal, 4))), ":one": 1, ":src": {source},
            ":exp": int(time.time()) + 60 * DAY,
        },
    )


def register(tech, category, is_new):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    TABLE.update_item(
        Key={"pk": "REGISTRY", "sk": tech},
        UpdateExpression="SET category = if_not_exists(category, :c), is_new = if_not_exists(is_new, :n), "
                         "first_seen = if_not_exists(first_seen, :t), last_seen = :t",
        ExpressionAttributeValues={":c": category, ":n": is_new, ":t": now},
    )


def registry():
    out, kwargs = {}, {"KeyConditionExpression": Key("pk").eq("REGISTRY")}
    while True:
        r = TABLE.query(**kwargs)
        for it in r["Items"]:
            out[it["sk"]] = {"category": it.get("category"), "is_new": bool(it.get("is_new")),
                             "first_seen": it.get("first_seen")}
        if "LastEvaluatedKey" not in r:
            return out
        kwargs["ExclusiveStartKey"] = r["LastEvaluatedKey"]


def hourly(tech, since_hour_key):
    items, kwargs = [], {"KeyConditionExpression": Key("pk").eq(f"TECH#{tech}") & Key("sk").gte(f"H#{since_hour_key}")}
    while True:
        r = TABLE.query(**kwargs)
        items.extend(r["Items"])
        if "LastEvaluatedKey" not in r:
            return items
        kwargs["ExclusiveStartKey"] = r["LastEvaluatedKey"]
