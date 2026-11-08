"""Evaluation entrypoint. No dotenv loading, fixtures or production-mode bypass."""
import os
from evaluation_config import validate_evaluation_environment

validate_evaluation_environment(os.environ)
# Existing production session refusal still applies. A config label is not
# qualification of sessions, proxy controls, project isolation or release.
from app import app
