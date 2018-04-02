#!/bin/env python
import requests
import re
import pprint
import json
import irc.client
import itertools
import sys

from bs4 import BeautifulSoup
from datetime import datetime 
from launchpadlib.launchpad import Launchpad

infra_status_regexp = re.compile('^ *([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) *UTC *(.+)$')
failing_check_jobs = re.compile('^FAILING CHECK JOBS: .*')

infra_status_url = 'https://wiki.openstack.org/wiki/Infrastructure_Status'
upstream_zuul_url = 'http://zuul.openstack.org/status'

infra_status_utc_format = '%Y-%m-%d %H:%M:%S'

cachedir = "/home/ellorent/.launchpadlib/cache/"

def get_infra_issues():
    infra_status = requests.get(infra_status_url) 
    infra_status_soup = BeautifulSoup(infra_status.content, 'html.parser')
    raw_issues = infra_status_soup.find_all('li')
    issues = []
    for ts_and_issue in raw_issues:
        m = infra_status_regexp.match(ts_and_issue.get_text())
        if m:
            ts = datetime.strptime(m.group(1), infra_status_utc_format)
            issue = m.group(2)
            issues.append((ts, issue))
    return issues

def get_upstream_tripleo_gate():
    upstream_zuul = json.loads(requests.get(upstream_zuul_url).content) 
    # TODO: filter by 'gate'
    gate_queues = next(pipeline['change_queues'] for pipeline in upstream_zuul['pipelines'] if pipeline['name'] == 'gate')
    tripleo_queue = next(queue for queue in gate_queues if queue['name'] == 'tripleo')['heads'][0]
    return tripleo_queue

def get_upstream_tripleo_bugs(since):
    launchpad = Launchpad.login_anonymously('OOOQ Ruck Rover', 'production', cachedir, version='devel')
    project = launchpad.projects['tripleo']

    # We can filter by status too 
    bugs = project.searchTasks(created_since = since)
    
    return bugs
    #browsed_bugs = []
    #for bug in bugs:
    #    browser = launchpad._browser
    #    browsed_bugs.append(browser.get(bug.self_link))
    #return browsed_bugs

def get_irc_gate_status():
    client = irc.client.Reactor()
    server = client.server()
    failing_jobs = [""]

    def on_connect(connection, event):
        connection.join('#oooq')
    
    def on_join(connection, event):
        connection.privmsg('#oooq', '!gatestatus')

    def on_disconmnect(connection, event):
        raise SystemExit()
    
    def on_public_message(connection, event):
        message = event.arguments[0]
        # TODO: Check it's hubbot
        if failing_check_jobs.match(message):
            print("hubbot: {}".format(message))
            failing_jobs[0] = message
            connection.quit("Using irc.client.py")

    try:
        server.connect("chat.freenode.net", 6667, "ruck-rover-bot")
    except irc.client.ServerConnectionError:
        print(sys.exc_info()[1])
        raise SystemExit(1)
    
    client.add_global_handler("welcome", on_connect)
    client.add_global_handler("join", on_join)
    client.add_global_handler("disconnect", on_disconmnect)
    client.add_global_handler("pubmsg", on_public_message)

    try:
        client.process_forever()
    except SystemExit:
        print('END')

    return failing_jobs[0]

def filter_infra_issues_by_date(date):
    issues = get_infra_issues()
    search_result = [(ts, issue) for ts, issue in issues if ts > date]
    return search_result

def main():
    since_date=datetime(2018, 3, 13)
    status = {}
    #TODO: Check #tripleo for <ooolpbot> URGENT TRIPLEO TASKS NEED ATTENTION
    #TODO: http://www.rssmix.com/u/8262477/rss.xml
    status['infra-issues'] = filter_infra_issues_by_date(since_date)
    status['upstream-tripleo-gate'] = get_upstream_tripleo_gate()
    status['upstream-tripleo-bugs'] = get_upstream_tripleo_bugs(since=since_date)
    status['gate-status'] = get_irc_gate_status()
    print("Number of infra issues: {}".format(len(status['infra-issues'])))
    print("Size of tripleo gate queue: {}".format(len(status['upstream-tripleo-gate'])))
    print("Number of tripleo bugs: {}".format(len(status['upstream-tripleo-bugs'])))
    print("gate status: {}".format(status['gate-status']))

if __name__ == '__main__':
    main()
