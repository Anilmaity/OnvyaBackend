"""Smoke test the login mutation through the GraphQL schema."""
import os, sys, django, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from graphene.test import Client
from config.schema import schema


class Req:
    META = {"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "verify"}
    user = None
    current_agency = None


q = """
mutation {
  login(email: "admin@demo.test", password: "demo1234") {
    __typename
    ... on AuthPayload { user { email } accessToken }
    ... on ValidationError { fieldErrors { field message } }
  }
}
"""
result = Client(schema).execute(q, context=Req())
print(json.dumps(result, indent=2, default=str))

q2 = """
mutation {
  login(email: "driver@demo.test", password: "demo1234") {
    __typename
    ... on AuthPayload { user { email } accessToken }
    ... on ValidationError { fieldErrors { field message } }
  }
}
"""
result2 = Client(schema).execute(q2, context=Req())
print(json.dumps(result2, indent=2, default=str))
