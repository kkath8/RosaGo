"""Candidate Render configuration. Never records request query strings or bodies."""
import os
bind = '0.0.0.0:' + os.environ.get('PORT', '10000')
workers = 2
worker_class = 'sync'
threads = 1
timeout = 60
graceful_timeout = 30
keepalive = 2
preload_app = False
accesslog = '-'
access_log_format = '%(m)s %(U)s %(s)s %(L)s'
errorlog = '-'
capture_output = False
forwarded_allow_ips = ''
limit_request_line = 4094
limit_request_fields = 50
limit_request_field_size = 4094

