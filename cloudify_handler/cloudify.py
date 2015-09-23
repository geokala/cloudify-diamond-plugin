#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

from diamond.handler.rabbitmq_topic import rmqHandler
from format import jsonify
import ssl
try:
    import pika
except ImportError:
    pika = None


class CloudifyHandler(rmqHandler):

    def _bind(self):
        """
           Create  socket and bind (we override the default implementation
           to set auto_delete=True)
        """
        credentials = pika.PlainCredentials(self.user, self.password)
        try:
            # If we're in an environment with celery we should have a
            # worker configuration, but we'll check for backwards
            # compatibility
            import worker_conf
            broker_cert_path = worker_conf.broker_cert_path
        except (ImportError, AttributeError):
            broker_cert_path = ''

        if broker_cert_path == '':
            # No SSL for rabbit
            broker_port = 5672
            ssl_enabled = False
            ssl_options = {}
        else:
            broker_port = 5671
            ssl_enabled = True
            ssl_options = {
                'ca_certs': broker_cert_path,
                'cert_reqs': ssl.CERT_REQUIRED,
            }
        params = pika.ConnectionParameters(credentials=credentials,
                                           host=self.server,
                                           virtual_host=self.vhost,
                                           port=broker_port,
                                           ssl=ssl_enabled,
                                           ssl_options=ssl_options)
        self.connection = pika.BlockingConnection(params)
        self.channel = self.connection.channel()
        self.channel.exchange_declare(exchange=self.topic_exchange,
                                      exchange_type="topic",
                                      auto_delete=True,
                                      durable=False,
                                      internal=False)

    def process(self, metric):
        if not pika:
            return

        try:
            self.channel.basic_publish(
                exchange=self.topic_exchange,
                routing_key=metric.getPathPrefix(),
                body=jsonify(metric))

        except Exception:  # Rough connection re-try logic.
            self.log.info(
                "Failed publishing to rabbitMQ. Attempting reconnect")
            self._bind()
