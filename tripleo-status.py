#!/bin/env python
import requests
import re
import pprint
import json

from bs4 import BeautifulSoup
from datetime import datetime 
from launchpadlib.launchpad import Launchpad

infra_status_regexp = re.compile('^ *([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) *UTC *(.+)$')
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
    bugs = project.searchTasks(created_since = since)
    return bugs
    #browsed_bugs = []
    #for bug in bugs:
    #    browser = launchpad._browser
    #    browsed_bugs.append(browser.get(bug.self_link))
    #return browsed_bugs

def filter_infra_issues_by_date(date):
    issues = get_infra_issues()
    search_result = [(ts, issue) for ts, issue in issues if ts > date]
    return search_result

def main():
    since_date=datetime(2018, 3, 13)
    status = {}
    status['infra-issues'] = filter_infra_issues_by_date(since_date)
    status['upstream-tripleo-gate'] = get_upstream_tripleo_gate()
    status['upstream-tripleo-bugs'] = get_upstream_tripleo_bugs(since=since_date)
    print("Number of infra issues: {}".format(len(status['infra-issues'])))
    print("Size of tripleo gate queue: {}".format(len(status['upstream-tripleo-gate'])))
    print("Number of tripleo bugs: {}".format(len(status['upstream-tripleo-bugs'])))

if __name__ == '__main__':
    main()
