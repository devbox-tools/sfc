# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


class TestInfluxdb:
    def test_influxdb_service_running_and_enabled(self, host):
        service = host.service('influxdb')
        assert service.is_running
        assert service.is_enabled

    def test_service_listening(self, host):
        assert host.socket("tcp://8086").is_listening
        assert host.socket("tcp://127.0.0.1:8088").is_listening