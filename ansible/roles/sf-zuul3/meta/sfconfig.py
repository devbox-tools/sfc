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

import copy

from sfconfig.components import Component
from sfconfig.utils import get_default
from sfconfig.utils import fail


EXT_GERRIT = "openstack#review.openstack.org#29418#" \
             "https://review.openstack.org/r/#username"


KNOWN_GERRITS = {
    "openstack.org": ["openstack", "review.openstack.org", "29418"],
    "wikimedia.org": ["wikimedia", "gerrit.wikimedia.org", "29418"],
}


class Zuul3Scheduler(Component):
    role = "zuul3-scheduler"
    require_role = ["nodepool3", "zookeeper"]

    def usage(self, parser):
        parser.add_argument("--zuul3-ssh-key", metavar="KEY_PATH",
                            help="Use existing ssh key for zuulV3")
        parser.add_argument("--zuul3-upstream-zuul-jobs", action="store_true",
                            help="Use openstack-infra/zuul-jobs")
        parser.add_argument("--zuul3-external-gerrit",
                            metavar="name#hostname#port#puburl#username",
                            help="Enable a remote gerrit, "
                            "e.g.: --zuul3-external-gerrit %s" % EXT_GERRIT)

    def argparse(self, args):
        if args.zuul3_ssh_key:
            self.import_ssh_key(args, "zuul_rsa", args.zuul3_ssh_key)

        if args.zuul3_upstream_zuul_jobs is not None:
            if args.sfconfig["zuul3"]["upstream_zuul_jobs"] != \
               args.zuul3_upstream_zuul_jobs:
                # Update sfconfig.yaml value
                args.sfconfig["zuul3"][
                    "upstream_zuul_jobs"] = args.zuul3_upstream_zuul_jobs
                args.save_sfconfig = True

        if args.zuul3_external_gerrit:
            values = args.zuul3_external_gerrit.split('#')
            try:
                if len(values) == 2:
                    # Resolve shortcuts
                    name, hostname, port = KNOWN_GERRITS.get(values[0])
                    if name is None:
                        raise RuntimeError("%s: unknown gerrit" % values[0])
                    username = values[1]
                else:
                    name, hostname, port, puburl, username = values
                    port = int(port)
            except ValueError:
                fail("Invalid zuul3-external-gerrit argument, it needs to be "
                     "in this format: %s" % EXT_GERRIT)
            if name == "gerrit":
                fail("Can't use 'gerrit' name for external connections")
            # Update gerrit_connection if necessary
            args.updated = False
            for connection in args.sfconfig.get("zuul3", {}).get(
                    "gerrit_connections", []):
                def update_value(key, value):
                    print("%s: updating %s to %s" % (name, key, value))
                    connection[key] = value
                    args.updated = True
                    args.save_sfconfig = True
                if connection["name"] == name:
                    if connection.get("hostname") != hostname:
                        update_value("hostname", hostname)
                    if connection.get("port") and \
                       int(connection["port"]) != port:
                        update_value("port", port)
                    if connection.get("puburl") != puburl:
                        update_value("puburl", puburl)
                    if connection.get("username") != username:
                        update_value("username", username)
                    break
            if not args.updated:
                # Else insert a new connection
                args.sfconfig.setdefault("zuul3", {}).setdefault(
                    "gerrit_connections", []).append({
                        'name': name,
                        'hostname': hostname,
                        'port': port,
                        'puburl': puburl,
                        'username': username
                    })
                args.save_sfconfig = True

    def prepare(self, args):
        super(Zuul3Scheduler, self).prepare(args)
        self.openstack_connection_name = None
        if args.sfconfig["zuul3"]["upstream_zuul_jobs"]:
            # Check review.openstack.org is configured
            for connection in args.sfconfig.get("zuul3", {}).get(
                    "gerrit_connections", []):
                if connection["hostname"] == "review.openstack.org":
                    self.openstack_connection_name = connection["name"]
                    break
            if not self.openstack_connection_name:
                fail("To use upstream zuul_jobs, review.openstack.org needs to"
                     " be configured, e.g.: --zuul3-external-gerrit %s" %
                     EXT_GERRIT)

    def configure(self, args, host):
        args.glue["zuul3_host"] = args.glue["zuul3_scheduler_host"]
        self.add_mysql_database(args, "zuul3")
        self.get_or_generate_ssh_key(args, "zuul_rsa")
        self.get_or_generate_ssh_key(args, "zuul_logserver_rsa")
        self.get_or_generate_ssh_key(args, "zuul_gatewayserver_rsa")
        self.get_or_generate_ssh_key(args, "zuul_worker_rsa")
        args.glue["zuul3_pub_url"] = "%s/zuul3/" % args.glue["gateway_url"]
        args.glue["zuul3_internal_url"] = "http://%s:%s/" % (
            args.glue["zuul3_host"], args.defaults["zuul3_port"])
        args.glue["zuul3_webapp_url"] = "http://%s:%s" % (
            args.glue["zuul3_scheduler_host"],
            args.defaults["zuul3_webapp_port"])
        args.glue["zuul3_mysql_host"] = args.glue["mysql_host"]
        args.glue["loguser_authorized_keys"].append(
            args.glue["zuul_logserver_rsa_pub"])
        args.glue["pagesuser_authorized_keys"].append(
            args.glue["zuul_gatewayserver_rsa_pub"])
        args.glue["openstack_connection_name"] = self.openstack_connection_name

        args.glue["zuul3_periodic_pipeline_mail_rcpt"] = args.sfconfig[
            "zuul3"]["periodic_pipeline_mail_rcpt"]

        # Extra settings
        zuul3_config = args.sfconfig.get("zuul3", {})
        args.glue["zuul3_upstream_zuul_jobs"] = zuul3_config[
            "upstream_zuul_jobs"]
        args.glue["zuul3_gerrit_connections"] = copy.copy(zuul3_config.get(
            "gerrit_connections", []))
        args.glue["zuul3_success_log_url"] = get_default(
            zuul3_config, "success_log_url",
            "%s/logs/{build.uuid}/" % args.glue["gateway_url"]
        )
        args.glue["zuul3_failure_log_url"] = get_default(
            zuul3_config, "failure_log_url",
            "%s/logs/{build.uuid}/" % args.glue["gateway_url"]
        )
        args.glue["zuul3_ssh_known_hosts"] = []
        args.glue["zuul3_github_connections"] = []

        # Add local gerrit if available
        if "gerrit" in args.glue["roles"]:
            args.glue.setdefault("zuul3_gerrit_connections", []).append({
                'name': 'gerrit',
                'port': 29418,
                'hostname': args.glue["gerrit_host"],
                'puburl': args.glue["gerrit_pub_url"],
                'username': 'zuul'
            })

        for extra_gerrit in args.glue.get("zuul3_gerrit_connections", []):
            if extra_gerrit.get("port", 29418) == 22:
                host_packed = extra_gerrit["hostname"]
            else:
                host_packed = "[%s]:%s" % (extra_gerrit["hostname"],
                                           extra_gerrit.get("port", 29418))
            args.glue["zuul3_ssh_known_hosts"].append({
                "host_packed": host_packed,
                "host": extra_gerrit["hostname"],
                "port": extra_gerrit.get("port", 29418)
            })
        if "logserver" in args.glue["roles"]:
            args.glue["zuul3_ssh_known_hosts"].append({
                "host_packed": args.glue["logserver_host"],
                "host": args.glue["logserver_host"],
                "port": 22
            })
        for github_connection in zuul3_config.get("github_connections", []):
            if github_connection.get("port", 22) == 22:
                host_packed = github_connection.get("hostname", "github.com")
            else:
                host_packed = "[%s]:%s" % (github_connection["hostname"],
                                           github_connection["port"])
            args.glue["zuul3_ssh_known_hosts"].append({
                "host_packed": host_packed,
                "host": github_connection.get("hostname", "github.com"),
                "port": github_connection.get("port", 22)
            })
            args.glue["zuul3_github_connections"].append(github_connection)


class Zuul3Web(Component):
    role = "zuul3-web"
    require_role = ["zuul3-scheduler"]

    def configure(self, args, host):
        args.glue["zuul3_web_url"] = "%s:%s" % (
            args.glue["zuul3_web_host"], args.defaults["zuul3_web_port"])
